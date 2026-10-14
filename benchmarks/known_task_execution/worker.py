"""Run reviewed unchanged tests against an exact source role.

执行经过审查、未修改断言的测试，并核验实际导入源码。This is an adapter,
not the official container harness or a security sandbox. Logs stay private.
本程序是执行适配器，不是官方容器，也不构成安全沙箱；原始日志保留在私有目录。
The worker uses Python 3.8-compatible syntax for historical source tests.
"""
import hashlib
import importlib.metadata
import ipaddress
import json
from pathlib import Path
import resource
import socket
import sys
import time


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def relative(path, root):
    """Reject escaped source identities. / 拒绝越界源码身份。"""
    return path.resolve().relative_to(root.resolve()).as_posix()


def validate_tree(root, files):
    """Check all bytes and the complete file set. / 检查全部字节和文件集合。"""
    expected = {row['path']: row for row in files}
    if len(expected) != len(files):
        raise ValueError('duplicate source file identity')
    found = {}
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError('source symlink not permitted')
        if path.name == '__pycache__' or path.suffix in {'.pyc', '.pyo'}:
            raise ValueError('foreign source bytecode not permitted')
        if not path.is_file():
            continue
        name = relative(path, root)
        raw = path.read_bytes()
        found[name] = {'sha256': sha(raw), 'bytes': len(raw)}
    if set(found) != set(expected):
        raise ValueError('source file set changed')
    for name, row in found.items():
        if row != {key: expected[name][key] for key in ('sha256', 'bytes')}:
            raise ValueError('source bytes changed')
    return expected


def network_guard(mode, denied):
    """Limit reviewed socket paths; not an OS sandbox. / 限制已审查的套接字路径。"""
    if mode not in {'deny', 'loopback'}:
        raise ValueError('unreviewed network mode')
    previous = {name: getattr(socket, name) for name in ('getaddrinfo',)}
    previous.update({name: getattr(socket.socket, name)
                     for name in ('connect', 'connect_ex', 'sendto')})

    def allow(host):
        if mode == 'loopback' and host == 'localhost':
            return
        try:
            ok = mode == 'loopback' and ipaddress.ip_address(host).is_loopback
        except (ValueError, TypeError):
            ok = False
        if not ok:
            denied.append({'host': str(host), 'reason': 'unreviewed_network_destination'})
            raise PermissionError('unreviewed network destination')

    def getaddrinfo(host, *args, **kwargs):
        # None is used by passive local server binding, not an outbound destination.
        if host is not None:
            allow(host)
        return previous['getaddrinfo'](host, *args, **kwargs)

    def connect(sock, address):
        allow(address[0])
        return previous['connect'](sock, address)

    def connect_ex(sock, address):
        allow(address[0])
        return previous['connect_ex'](sock, address)

    def sendto(sock, data, *args):
        allow(args[-1][0])
        return previous['sendto'](sock, data, *args)

    socket.getaddrinfo = getaddrinfo
    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.socket.sendto = sendto
    return previous


def restore_network(previous):
    socket.getaddrinfo = previous['getaddrinfo']
    for name in ('connect', 'connect_ex', 'sendto'):
        setattr(socket.socket, name, previous[name])


def error_class(report):
    """Store categories without private stack paths. / 仅保存异常类别。"""
    crash = getattr(report.longrepr, 'reprcrash', None)
    message = getattr(crash, 'message', '')
    value = message.split(':', 1)[0].rsplit('.', 1)[-1]
    return value if value.isidentifier() else 'upstream_test_failure'


def execute(config):
    root = Path(config['execution_root']).resolve()
    expected = validate_tree(root, config['source_files'])
    aliases = config.get('pathless_aliases', {})
    aliases_hash = sha(json.dumps(aliases, sort_keys=True, ensure_ascii=False,
                                 separators=(',', ':'), allow_nan=False).encode())
    for alias in aliases.values():
        if alias['source_path'] not in expected or expected[alias['source_path']]['sha256'] != alias['source_sha256']:
            raise ValueError('pathless alias source identity differs')
    if tuple(sys.version_info[:2]) != tuple(config['python_minor']):
        raise ValueError('reference interpreter minor mismatch')
    installed = {name: importlib.metadata.version(name)
                 for name in config['dependency_versions']}
    if installed != config['dependency_versions']:
        raise ValueError('dependency lock mismatch')
    sys.dont_write_bytecode = True
    # Source imports, including test helpers, must come from the prepared role.
    sys.path[:0] = [str(root / value) for value in config['import_roots']]
    collected, selected, deselected, reports, collection_errors, denied = [], [], [], [], [], []
    wanted = set(config['selectors'])
    started = time.perf_counter()
    import pytest

    class Recorder:
        def pytest_itemcollected(self, item):
            collected.append(item.nodeid)

        @pytest.hookimpl(trylast=True)
        def pytest_collection_modifyitems(self, session, config, items):
            keep, drop = [], []
            for item in items:
                (keep if item.nodeid in wanted else drop).append(item)
            selected.extend(item.nodeid for item in keep)
            deselected.extend(node for node in collected if node not in selected)
            items[:] = keep
            if drop:
                config.hook.pytest_deselected(items=drop)

        @pytest.hookimpl(trylast=True)
        def pytest_collection_finish(self, session):
            final = [item.nodeid for item in session.items]
            if final != selected or any(node not in wanted for node in final):
                raise ValueError('final selected tests differ from reviewed selection')

        def pytest_collectreport(self, report):
            if report.failed:
                collection_errors.append({'nodeid': report.nodeid, 'error_type': error_class(report)})

        def pytest_runtest_logreport(self, report):
            category = error_class(report) if report.failed else None
            wasxfail = hasattr(report, 'wasxfail')
            strict_xpass = report.failed and str(report.longrepr).startswith('[XPASS(strict)]')
            state = ('xpassed' if strict_xpass or wasxfail and report.passed else
                     'xfailed' if wasxfail and report.skipped else report.outcome)
            kind = ('network' if denied else 'resource' if category == 'MemoryError' else
                    'dependency' if category in {'ModuleNotFoundError', 'ImportError'} else
                    'unknown' if category in {'FileNotFoundError', 'PermissionError'} else 'framework' if
                    report.when != 'call' and report.failed else 'behavior')
            reports.append({'nodeid': report.nodeid, 'phase': report.when,
                            'state': state, 'raw_outcome': report.outcome,
                            'wasxfail': wasxfail, 'strict_xpass': strict_xpass, 'kind': kind,
                            'error_type': category, 'seconds': report.duration})

    previous = network_guard(config['network_mode'], denied)
    try:
        code = int(pytest.main(['-c', '/dev/null', '--rootdir=' + str(root),
                               '--confcutdir=' + str(root), '--import-mode=importlib',
                               '-p', 'no:cacheprovider', '-q',
                               *[str(root / value) for value in config['test_files']]],
                              plugins=[Recorder()]))
    finally:
        restore_network(previous)
    validate_tree(root, config['source_files'])
    loaded = {}
    for name, module in list(sys.modules.items()):
        if not any(name == package or name.startswith(package + '.')
                   for package in config['production_packages']):
            continue
        file = getattr(module, '__file__', None)
        if file is None:
            continue
        path = Path(file)
        key = relative(path, root)
        if path.is_symlink() or key not in expected or sha(path.read_bytes()) != expected[key]['sha256']:
            raise ValueError('production import identity differs')
        origin = getattr(getattr(module, '__spec__', None), 'origin', file)
        if origin is not None and Path(origin).resolve() != path.resolve():
            raise ValueError('production import spec differs')
        loaded[name] = {'path': key, 'sha256': expected[key]['sha256']}
    if not loaded:
        raise ValueError('no actual upstream production module imported')
    outcomes = []
    for nodeid in selected:
        rows = [row for row in reports if row['nodeid'] == nodeid]
        failures = [row for row in rows if row['state'] == 'failed']
        skipped = [row for row in rows if row['state'] == 'skipped']
        xstates = [row for row in rows if row['state'] in {'xfailed', 'xpassed'}]
        calls = [row for row in rows if row['phase'] == 'call']
        phase_errors = [row for row in failures if row['phase'] != 'call']
        row = (phase_errors or failures or xstates or skipped or calls or
               [{'nodeid': nodeid, 'phase': 'not_run', 'state': 'not_run', 'kind': 'unknown'}])[0].copy()
        if row['state'] == 'failed' and row['phase'] != 'call':
            row['state'] = 'error'
        outcomes.append(row)
    return {'schema_version': 1, 'instance_id': config['instance_id'], 'role': config['role'],
            'base_commit': config['base_commit'],
            'test_patch_sha256': config['test_patch_sha256'],
            'code_patch_sha256': config['code_patch_sha256'],
            'environment_sha256': config['environment_sha256'],
            'pathless_aliases_sha256': aliases_hash,
            'source_files_index_sha256': config['source_files_index_sha256'],
            'collection_status': 'error' if collection_errors or code in {2, 3, 4} else 'complete',
            'runner_status': 'completed', 'process_exit_code': code,
            'collected': selected, 'collected_all': collected,
            'selected': selected, 'deselected': deselected,
            'results': outcomes, 'phase_reports': reports, 'collection_errors': collection_errors,
            'network_denials': denied, 'loaded_source_modules': loaded,
            'source_before_after_verified': True, 'dependency_versions': installed,
            'python_version': sys.version, 'elapsed_seconds': time.perf_counter() - started,
            'peak_rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss /
                            (1024 * 1024 if sys.platform == 'darwin' else 1024),
            'classification': 'known_development_task_native_regression_execution',
            'limits': 'Finite upstream regression tests; not generated repair success, official '
                      'container reproduction, necessary context, or general semantic equivalence.'}


def main():
    config = json.loads(Path(sys.argv[1]).read_bytes())
    resource.setrlimit(resource.RLIMIT_CPU, (config['cpu_seconds'], config['cpu_seconds']))
    result = execute(config)
    with Path(config['output_path']).open('x') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    return result['process_exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
