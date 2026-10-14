"""Isolated upstream assertion worker. / 隔离的上游断言执行程序。

Input files are trusted pinned metadata produced by run.py. No graphs are built.
输入为 run.py 生成的固定元数据；本程序不构建图。
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import resource
import sys
import time


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def failure_detail(value: object) -> str:
    """Retain error category, never local stack/path. / 保留错误类别，不保留本地堆栈。"""
    lines = [x.strip()[2:].strip() for x in str(value).splitlines() if x.strip().startswith('E ')]
    if not lines:
        return 'upstream_assertion_failure'
    message = lines[-1]
    category = message.split(':', 1)[0]
    if category.isidentifier() and category.endswith(('Error', 'Exception')):
        return category
    return 'AssertionError' if message.startswith('assert ') else 'upstream_assertion_failure'



def validate_imported_identity(root: Path, package_path: str, modules: dict,
                               expected: dict) -> dict:
    """Bind actual imports to source bytes. / 将实际导入绑定到源码字节。"""
    package_root = (root / package_path).resolve()
    rows = {}
    for name, module in modules.items():
        file = getattr(module, '__file__', None)
        if file is None:
            continue
        original = Path(file)
        path = original.resolve()
        if not path.is_relative_to(package_root) or original.is_symlink():
            raise ValueError('imported production module escaped selected role')
        relative = path.relative_to(root).as_posix()
        source_hash = digest(path.read_bytes())
        if relative not in expected or source_hash != expected[relative]['sha256']:
            raise ValueError('imported production source identity mismatch')
        origin = getattr(getattr(module, '__spec__', None), 'origin', file)
        if origin and Path(origin).resolve() != path:
            raise ValueError('module file/spec origin disagreement')
        rows[name] = {'relative_path': relative, 'sha256': source_hash}
    if not rows:
        raise ValueError('no production modules imported')
    return rows



def reject_cached_bytecode(root: Path) -> None:
    """Source hashes cannot certify a foreign bytecode cache. / 源码哈希不能认证外来字节码。"""
    if any(path.name == '__pycache__' or path.suffix in {'.pyc', '.pyo'}
           for path in root.rglob('*')):
        raise ValueError('cached bytecode is not a pinned source input')


def execute(config: dict, *, enforce_framework: bool = True) -> dict:
    root = Path(config['execution_root']).resolve()
    package_root = (root / config['package_path']).resolve()
    dependency_root = Path(config['dependency_root']).resolve()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from scripts.prepare_global_execution_sources import validate_files
    validate_files(root, config['hybrid_files'])
    validate_files(dependency_root, config['dependency_files'])
    reject_cached_bytecode(root)
    reject_cached_bytecode(dependency_root)
    previous_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(dependency_root), str(root / 'src'), str(root),
                    str(root / 'tests'), str(root / 'docs/advanced')]
    if enforce_framework:
        for name, version in config['framework_versions'].items():
            if importlib.metadata.version(name) != version:
                raise ValueError('locked test-framework version mismatch')
    reports = []
    collection = []
    trace = {}
    observations = []
    current = ['__import__']
    started = time.perf_counter()

    def tracer(frame, event, arg):
        filename = frame.f_code.co_filename
        if filename.startswith(str(package_root) + os.sep):
            relative = Path(filename).relative_to(root).as_posix()
            if event == 'line':
                trace.setdefault(current[0], {}).setdefault(relative, set()).add(frame.f_lineno)
            if event in {'call', 'return'}:
                for watch in config.get('global_watch', []):
                    if relative == watch['path'] and frame.f_code.co_name == watch['function']:
                        state = {}
                        for name in watch['names']:
                            value = frame.f_globals.get(name)
                            state[name] = {'type': type(value).__name__, 'is_none': value is None,
                                           'tuple_length': len(value) if isinstance(value, tuple)
                                           else None}
                        observations.append({'nodeid': current[0], 'event': event,
                                             'source_line': frame.f_lineno, 'state': state})
        return tracer

    class Recorder:
        def pytest_collection_modifyitems(self, session, config, items):
            collection.extend(item.nodeid for item in items)

        def pytest_runtest_protocol(self, item, nextitem):
            current[0] = item.nodeid

        def pytest_runtest_logreport(self, report):
            row = {'nodeid': report.nodeid, 'when': report.when, 'outcome': report.outcome,
                   'duration': report.duration}
            if report.failed or report.skipped:
                row['failure_detail'] = failure_detail(report.longrepr)
            reports.append(row)

    previous_trace = sys.gettrace()
    sys.settrace(tracer)
    try:
        importlib.import_module(config['package'])
        import pytest
        if enforce_framework:
            if not Path(pytest.__file__).resolve().is_relative_to(dependency_root):
                raise ValueError('pytest import escaped verified dependency runtime')
        code = int(pytest.main(['-c', '/dev/null', '--rootdir=' + str(root),
                               '--import-mode=importlib', '--confcutdir=' + str(root), '-q',
                               *[str(root / node) for node in config['tests']]], plugins=[Recorder()]))
    finally:
        sys.settrace(previous_trace)
        sys.dont_write_bytecode = previous_bytecode
    modules = {name: module for name, module in list(sys.modules.items())
               if name.split('.')[0] == config['package']}
    loaded = validate_imported_identity(root, config['package_path'], modules,
                                       config['production_files'])
    validate_files(root, config['hybrid_files'])
    validate_files(dependency_root, config['dependency_files'])
    reject_cached_bytecode(root)
    reject_cached_bytecode(dependency_root)
    return {'schema_version': 1, 'repository': config['repository'],
            'source_sha': config['source_sha'], 'role': config['role'],
            'label_source_sha': config['label_source_sha'], 'exit_code': code,
            'collected_cases': collection, 'reports': reports,
            'loaded_source_modules': loaded, 'production_hashes_verified': True,
            'execution_trace': {node: {path: sorted(lines) for path, lines in paths.items()}
                                for node, paths in trace.items()},
            'global_observations': observations,
            'trace_limits': 'Input-specific Python line observations; not necessary-context gold '
                            'or complete semantic/dependency proof.',
            'classification': 'development_resource_and_execution_preflight',
            'elapsed_seconds': time.perf_counter() - started,
            'peak_rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss /
                            (1024 * 1024 if sys.platform == 'darwin' else 1024),
            'python_version': sys.version, 'pytest_version': pytest.__version__}


def main() -> int:
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    config = json.loads(Path(sys.argv[1]).read_text())
    if sys.version_info[:2] != (3, 12):
        raise ValueError('reference reproduction requires Python 3.12')
    row = execute(config)
    Path(config['output_path']).write_text(json.dumps(row, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
