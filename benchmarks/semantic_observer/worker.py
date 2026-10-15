"""Run unchanged reviewed upstream tests with optional independent observation.

运行原样上游测试，可选独立运行时观测。This is a resource-limited execution
adapter for reviewed code, not an OS security sandbox. Raw logs stay private.
本适配器不是操作系统安全沙箱；原始日志留在仓库外。
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import resource
import sys
import threading
import time
import _thread

from benchmarks.known_task_execution.worker import (
    error_class, network_guard, process_guard, production_modules,
    restore_network, validate_tree, reviewed_plugins,
)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_relative(name):
    if (type(name) is not str or not name or '\\' in name or ':' in name
            or '\x00' in name or name.startswith('/')
            or any(x in {'', '.', '..'} for x in name.split('/'))):
        raise ValueError('invalid relative input / 非法相对路径')
    return name


def reviewed_pytest_args(config):
    """Restore explicitly reviewed dependency options / 仅恢复已审依赖选项。"""
    plugins = config.get('pytest_plugins', [])
    filters = config.get('pytest_warning_filters', [])
    if (type(plugins) is not list or len(plugins) != len(set(plugins))
            or any(p != 'pytest_mock.plugin' for p in plugins)):
        raise ValueError('unreviewed pytest dependency plugin')
    if plugins and 'pytest-mock' not in config['dependency_versions']:
        raise ValueError('explicit plugin requires a version pin')
    if filters not in ([], ['error']):
        raise ValueError('unreviewed pytest warning policy')
    return [part for p in plugins for part in ('-p', p)] + (
        ['-W', 'error'] if filters else [])


class ThreadGuard:
    """Reject reviewed Python thread entry points / 拒绝Python线程启动入口。

    Native extensions or deliberately bypassed guards remain outside the claim.
    原生扩展或主动绕过不在此Python约束的保证范围内。
    """

    def __init__(self):
        self.denied = 0

    def __enter__(self):
        if threading.active_count() != 1:
            raise ValueError('worker must start with one Python thread')
        self.old_start = threading.Thread.start
        self.old_low = _thread.start_new_thread

        def reject(*args, **kwargs):
            self.denied += 1
            raise RuntimeError('thread launch outside the single-thread protocol')

        threading.Thread.start = reject
        _thread.start_new_thread = reject
        return self

    def __exit__(self, *args):
        threading.Thread.start = self.old_start
        _thread.start_new_thread = self.old_low


def execute(config):
    """Execute one source role; test failures remain results / 执行一个源码角色，保留失败。"""
    if platform.python_implementation() != 'CPython' or sys.version_info[:2] != (3, 12):
        raise ValueError('this observer protocol requires CPython 3.12')
    if config.get('schema_version') != 1 or type(config.get('observe')) is not bool:
        raise ValueError('invalid execution configuration')
    if os.environ.get('PYTEST_DISABLE_PLUGIN_AUTOLOAD') != '1':
        raise ValueError('pytest plugin autoload must be explicitly disabled')
    root = Path(config['source_root']).resolve(strict=True)
    expected = validate_tree(root, config['source_files'])
    if not config['production_paths'] or not config['test_files']:
        raise ValueError('production paths and original test files are required')
    for name in [*config['production_paths'], *config['test_files']]:
        safe_relative(name)
        if name not in expected or not name.endswith('.py'):
            raise ValueError('source selection is not in the pinned source tree')
    if set(config['production_paths']) & set(config['test_files']):
        raise ValueError('production/test overlap is not an admissible observation scope')
    for name in config['import_roots']:
        if name != '.':
            safe_relative(name)
    selectors = config.get('selectors')
    if selectors is not None and (not isinstance(selectors, list) or not selectors
                                  or len(set(selectors)) != len(selectors)
                                  or not all(type(s) is str for s in selectors)):
        raise ValueError('selectors must retain a nonempty distinct fixed panel')
    installed = {name: metadata.version(name) for name in config['dependency_versions']}
    if installed != config['dependency_versions']:
        raise ValueError('test-runtime dependency versions differ')
    pytest_options = reviewed_pytest_args(config)
    source_pins = {p: expected[p]['sha256'] for p in config['production_paths']}
    from benchmarks.semantic_observer.observer import GlobalReadObserver

    manager = (GlobalReadObserver(source_root=root, source_pins=source_pins,
                                 max_observations=config['max_observations'])
               if config['observe'] else nullcontext(None))
    reports, selected, collection_errors, network_denials = [], [], [], []
    progress = Path(config['progress_path']) if config.get('progress_path') else None
    if progress:
        if progress.resolve().is_relative_to(root):
            raise ValueError('progress output must be outside source tree')
        with progress.open('x', encoding='utf-8'):
            pass

    # Load the reviewed dependency before upstream import roots can shadow it.
    # 先按实际安装目录核验依赖插件，避免上游同名模块遮蔽。
    import pytest
    reviewed_plugins(config.get('pytest_plugins', []), installed)
    old_path, old_bytecode, old_cwd = list(sys.path), sys.dont_write_bytecode, Path.cwd()
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(root / name) for name in config['import_roots']]
    os.chdir(root)
    process_denials = []
    previous_network = None
    process_state = {'value': False}
    start = time.perf_counter()
    thread_guard = ThreadGuard()

    def emit(event, row):
        if progress:
            with progress.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps({'event': event, 'payload': row}, ensure_ascii=False) + '\n')

    try:
        previous_network = network_guard('deny', network_denials)
        process_state = process_guard(True, process_denials)
        if any(name == package or name.startswith(package + '.')
               for name in sys.modules for package in config['production_packages']):
            raise ValueError('production module imported before observation boundary')

        class Recorder:
            @pytest.hookimpl(trylast=True)
            def pytest_collection_modifyitems(self, session, config, items):
                if selectors is not None:
                    keep = [item for item in items if item.nodeid in selectors]
                    drop = [item for item in items if item.nodeid not in selectors]
                    items[:] = keep
                    if drop:
                        config.hook.pytest_deselected(items=drop)

            def pytest_collection_finish(self, session):
                selected.extend(item.nodeid for item in session.items)

            def pytest_collectreport(self, report):
                if report.failed:
                    collection_errors.append({'nodeid': report.nodeid,
                                              'error_type': error_class(report)})

            def pytest_runtest_logreport(self, report):
                row = {'nodeid': report.nodeid, 'phase': report.when,
                       'outcome': report.outcome, 'wasxfail': hasattr(report, 'wasxfail'),
                       'error_type': error_class(report) if report.failed else None,
                       'seconds': report.duration}
                reports.append(row)
                emit('phase', row)

        with thread_guard, manager as observer:
            code = int(pytest.main(['-c', '/dev/null', '--rootdir=' + str(root),
                                   '--confcutdir=' + str(root), '--import-mode=importlib',
                                   '-p', 'no:cacheprovider', '-q',
                                   *pytest_options,
                                   *[str(root / f) for f in config['test_files']]],
                                  plugins=[Recorder()]))
        observation = observer.report() if observer is not None else None
        loaded = production_modules(root, expected, config['production_packages'])
        validate_tree(root, config['source_files'])
    finally:
        process_state['value'] = False
        if previous_network is not None:
            restore_network(previous_network)
        sys.path[:] = old_path
        sys.dont_write_bytecode = old_bytecode
        os.chdir(old_cwd)
    return {'schema_version': 1, 'task_id': config['task_id'], 'role': config['role'],
            'observe': config['observe'], 'config_sha256': digest(canonical(config)),
            'source_tree_sha256': digest(canonical(config['source_files'])),
            'dependency_versions': installed, 'python': platform.python_version(),
            'implementation': platform.python_implementation(),
            'status': 'completed', 'pytest_exit_code': code, 'selected': selected,
            'missing_selectors': sorted(set(selectors or []) - set(selected)),
            'phase_reports': reports, 'collection_errors': collection_errors,
            'loaded_source_modules': loaded, 'source_before_after_verified': True,
            'network_denials': network_denials, 'process_denials': process_denials,
            'thread_denials': thread_guard.denied, 'observation': observation,
            'elapsed_seconds': time.perf_counter() - start,
            'CPU_seconds': resource.getrusage(resource.RUSAGE_SELF).ru_utime +
                           resource.getrusage(resource.RUSAGE_SELF).ru_stime,
            'peak_rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss /
                            (1024 * 1024 if sys.platform == 'darwin' else 1024),
            'scope': 'finite unchanged-test execution and pre-op global observations; '
                     'not full semantics, necessary context or generated repair'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True, help='Reviewed role config / 已审角色配置')
    parser.add_argument('--output', type=Path, required=True, help='New private result / 新私人结果')
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        parser.error('refuse existing output / 拒绝覆盖已有结果')
    config = json.loads(args.config.read_bytes())
    resource.setrlimit(resource.RLIMIT_CPU, (config['cpu_seconds'], config['cpu_seconds']))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024**2, 64 * 1024**2))
    result = execute(config)
    with args.output.open('xb') as stream:
        stream.write(canonical(result) + b'\n')
    return result['pytest_exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
