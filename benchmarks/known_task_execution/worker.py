"""Run reviewed unchanged tests against an exact source role.

执行经过审查、未修改断言的测试，并核验实际导入源码。This is an adapter,
not the official container harness or a security sandbox. Logs stay private.
本程序是执行适配器，不是官方容器，也不构成安全沙箱；原始日志保留在私有目录。
The standalone worker supports Python 3.7 with a locked metadata backport.
"""
import hashlib
import importlib
import ipaddress
import json
import os
from pathlib import Path
import random
import resource
import shlex
import socket
import sys
import time

if sys.version_info >= (3, 8):
    from importlib import metadata
else:
    import importlib_metadata as metadata


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def relative(path, root):
    """Reject escaped source identities. / 拒绝越界源码身份。"""
    return path.resolve().relative_to(root.resolve()).as_posix()


def reviewed_source_logs(files, request):
    """Permit two bounded runtime logs with an exact reviewed source proof.

    只允许固定源码声明的两个限额日志；不能隐藏任何原有源码文件。
    """
    if request is None:
        return None
    expected = {row['path']: row for row in files}
    proof = expected.get('autogpt/logs.py')
    policy = {'source_path': 'autogpt/logs.py', 'source_sha256': proof['sha256'] if proof else None,
              'files': ['logs/activity.log', 'logs/error.log'], 'max_total_bytes': 1048576}
    if isinstance(request, dict) and 'cycle_source_proofs' in request:
        # Source-supported OVERWRITE_DEBUG makes the original cycle paths exact.
        # 源码支持的目录选项只固定日志路径，不改变摘要逻辑或测试断言。
        paths = ['autogpt/log_cycle/log_cycle.py', 'autogpt/memory/message_history.py',
                 'tests/unit/test_message_history.py']
        if any(path not in expected for path in paths):
            raise ValueError('unreviewed cycle log source proof')
        policy['cycle_source_proofs'] = [
            {'path': path, 'sha256': expected[path]['sha256']} for path in paths]
        policy['overwrite_debug'] = '1'
        policy['files'] += [
            'logs/DEBUG/auto_gpt/000/0_prompt_summary.json',
            'logs/DEBUG/auto_gpt/000/1_summary.txt',
            'logs/DEBUG/auto_gpt/000/2_prompt_summary.json',
            'logs/DEBUG/auto_gpt/000/3_summary.txt']
    if (proof is None or json.dumps(request, sort_keys=True) != json.dumps(policy, sort_keys=True)
            or any(name in expected for name in policy['files'])):
        raise ValueError('unreviewed source log policy or source file overlap')
    return policy


def source_log_records(root, policy):
    """Hash private runtime outputs without publishing their text. / 只记录日志摘要。"""
    records = []
    if policy is None:
        return records
    total = 0
    for name in policy['files']:
        path = root / name
        if not path.exists() and not path.is_symlink():
            continue
        if (path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1
                or relative(path, root) != name):
            raise ValueError('source log must be a distinct regular file')
        total += path.stat().st_size
        if total > policy['max_total_bytes']:
            raise ValueError('source logs exceeded fixed byte cap')
        records.append({'path': name, 'bytes': path.stat().st_size, 'sha256': sha(path.read_bytes())})
    return records


def validate_tree(root, files, allowed_logs=None):
    """Check every source byte, with optional separately hashed runtime logs.

    核验全部源码字节；仅经显式审查的运行日志独立计数与摘要，不计入源码。
    """
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
        if allowed_logs is not None and name in allowed_logs['files']:
            continue
        raw = path.read_bytes()
        found[name] = {'sha256': sha(raw), 'bytes': len(raw)}
    if set(found) != set(expected):
        raise ValueError('source file set changed')
    for name, row in found.items():
        if row != {key: expected[name][key] for key in ('sha256', 'bytes')}:
            raise ValueError('source bytes changed')
    if allowed_logs is not None:
        reviewed_source_logs(files, allowed_logs)
        source_log_records(root, allowed_logs)
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


def reviewed_plugins(names, versions):
    """Load only locked test plugins from their distributions. / 只加载已锁定测试插件。"""
    allowed = {'pytest_asyncio.plugin': 'pytest-asyncio', 'pytest_mock.plugin': 'pytest-mock'}
    if (not isinstance(names, list) or not all(isinstance(name, str) for name in names)
            or len(names) != len(set(names))):
        raise ValueError('plugin names must be a distinct reviewed list')
    modules = []
    for name in names:
        if name not in allowed or allowed[name] not in versions:
            raise ValueError('unreviewed or unlocked test plugin')
        distribution = metadata.distribution(allowed[name])
        path = Path(distribution.locate_file(name.replace('.', '/') + '.py')).resolve()
        module = importlib.import_module(name)
        if Path(module.__file__).resolve() != path:
            raise ValueError('test plugin import escaped its locked distribution')
        if Path(module.__spec__.origin).resolve() != path:
            raise ValueError('test plugin import spec differs')
        modules.append(module)
    return modules


def reviewed_pytest_options(root, expected, config):
    """Restore a source-bound async mode without broad config execution.

    仅恢复经源码字节核验的异步模式，不执行整份外来配置或改写原测试。
    """
    mode = config.get('asyncio_mode')
    strict = config.get('strict_upstream_pytest')
    if mode is None and strict is None:
        return []
    if mode is not None and (mode not in {'auto', 'strict'} or
                            'pytest_asyncio.plugin' not in config.get('pytest_plugins', [])):
        raise ValueError('async mode requires the explicit locked plugin')
    if strict is not None and strict is not True:
        raise ValueError('strict upstream pytest request must be true')
    proof = config.get('upstream_pytest_config', {})
    key = proof.get('path')
    if key not in expected or proof.get('sha256') != expected[key]['sha256']:
        raise ValueError('upstream pytest config identity differs')
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    parsed = tomllib.loads((root / key).read_text(encoding='utf-8'))
    ini = parsed.get('tool', {}).get('pytest', {}).get('ini_options', {})
    if mode is not None and ini.get('asyncio_mode') != mode:
        raise ValueError('requested async mode differs from fixed upstream config')
    options = ['--asyncio-mode=' + mode] if mode is not None else []
    if strict is True:
        raw = ini.get('addopts')
        addopts = shlex.split(raw) if isinstance(raw, str) else raw
        required = ['--strict-markers', '--strict-config', '--durations=5']
        if not isinstance(addopts, list) or not all(isinstance(x, str) for x in addopts):
            raise ValueError('upstream addopts must be a string or string list')
        if any(flag not in addopts for flag in required):
            raise ValueError('strict flags differ from fixed upstream config')
        markers = ini.get('markers', [])
        if not isinstance(markers, list) or not all(isinstance(x, str) and '\0' not in x for x in markers):
            raise ValueError('upstream markers must be a string list')
        options.extend([*required, '-o', 'markers=' + '\n'.join(markers)])
    return options


NUMERICAL_STATE = {
    'seed': 1337, 'python_hashseed': '0', 'preload_first': 'torch',
    'torch_threads': 1, 'torch_interop_threads': 1,
    'per_node_reset': ['python', 'numpy', 'torch', 'loaded_tensorflow'],
    'backend': 'tensorflow', 'preserve_jax_explicit_rng': True,
}


def numerical_runtime_flags():
    """Prove -s accepts the allowlisted env; -I/-E would ignore its hash seed.

    用运行时标志验证 -s 接受白名单环境；仅检查环境变量不足以证明哈希种子。
    """
    return {key: getattr(sys.flags, key) for key in
            ('ignore_environment', 'isolated', 'no_user_site', 'hash_randomization')}


def dependency_module(name, versions):
    """Import only the locked numerical dependency. / 仅导入锁定的数值依赖。"""
    if name not in {'torch', 'numpy'} or name not in versions:
        raise ValueError('unlocked numerical dependency')
    distribution = metadata.distribution(name)
    if distribution.version != versions[name]:
        raise ValueError('numerical distribution version differs')
    expected = Path(distribution.locate_file(name + '/__init__.py')).resolve()
    module = importlib.import_module(name)
    if (Path(module.__file__).resolve() != expected or
            Path(module.__spec__.origin).resolve() != expected):
        raise ValueError('numerical import escaped locked distribution')
    return module


class NumericalState:
    """Fixed prospective eager seed condition; not universal determinism.

    固定前瞻实验的种子边界位于 pytest setup hook，早于原 unittest setUp；
    不改写原 setUp，不重置 JAX PRNGKey，也不声称覆盖所有图/本地随机流。
    """
    def __init__(self, config, versions, emit):
        self.versions, self.emit, self.events = versions, emit, []
        self.torch, self.numpy = None, None
        self.enabled = config is not None
        if self.enabled and json.dumps(config, sort_keys=True) != json.dumps(NUMERICAL_STATE, sort_keys=True):
            raise ValueError('unreviewed numerical state configuration')
        if self.enabled and os.environ.get('PYTHONHASHSEED') != '0':
            raise ValueError('numerical hash seed environment differs')
        if self.enabled and numerical_runtime_flags() != {
                'ignore_environment': 0, 'isolated': 0, 'no_user_site': 1, 'hash_randomization': 0}:
            raise ValueError('numerical runtime must accept fixed hash seed with user site disabled')

    def reset(self, nodeid, phase):
        if not self.enabled:
            return
        random.seed(1337)
        self.numpy.random.seed(1337)
        # torch.manual_seed also touches accelerator RNGs; use its CPU generator.
        self.torch.random.default_generator.manual_seed(1337)
        apis = ['random.seed', 'numpy.random.seed',
                'torch.random.default_generator.manual_seed']
        tensorflow = sys.modules.get('tensorflow')
        if tensorflow is not None:
            if (self.versions.get('tensorflow') != '2.16.2' or
                    getattr(tensorflow, '__version__', None) != self.versions['tensorflow']):
                raise ValueError('loaded TensorFlow version differs')
            tensorflow.random.set_seed(1337)
            apis.append('loaded_tensorflow.random.set_seed')
        event = {'nodeid': nodeid, 'phase': phase, 'seed': 1337, 'called_apis': apis,
                 'tensorflow_already_loaded': tensorflow is not None,
                 'boundary': 'before original unittest setUp; original explicit seeds preserved',
                 'JAX_rng_reset': False}
        self.events.append(event)
        self.emit('numerical_seed', event)

    def bootstrap(self):
        if not self.enabled:
            return
        if any(name in sys.modules for name in ('tensorflow', 'keras')):
            raise ValueError('TensorFlow or Keras loaded before Torch-first bootstrap')
        if self.versions.get('torch') != '2.2.2' or self.versions.get('numpy') != '1.26.4':
            raise ValueError('unreviewed numerical dependency versions')
        self.torch = dependency_module('torch', self.versions)
        if any(name in sys.modules for name in ('tensorflow', 'keras')):
            raise ValueError('Torch bootstrap unexpectedly imported TensorFlow or Keras')
        self.torch.set_num_threads(1)
        self.torch.set_num_interop_threads(1)
        self.numpy = dependency_module('numpy', self.versions)
        self.reset(None, 'before_collection')

    def gate(self):
        if not self.enabled:
            return None
        module = sys.modules.get('keras.src.backend.config') or sys.modules.get('keras.backend.config')
        if module is None or module.backend() != 'tensorflow':
            raise ValueError('actual Keras backend differs from prospective configuration')
        tf = sys.modules.get('tensorflow')
        if tf is None:
            raise ValueError('selected TensorFlow backend was not actually imported')
        if tf.config.list_physical_devices('GPU'):
            raise ValueError('GPU visible in CPU-only numerical run')
        record = {'backend': 'tensorflow', 'torch_first': True,
                  'runtime_flags': numerical_runtime_flags(),
                  'python_hashseed_env': os.environ.get('PYTHONHASHSEED'),
                  'torch_cpu_threads': self.torch.get_num_threads(),
                  'torch_interop_threads': self.torch.get_num_interop_threads(),
                  'tensorflow_thread_env': {key: os.environ.get(key) for key in
                                             ('TF_NUM_INTRAOP_THREADS', 'TF_NUM_INTEROP_THREADS')},
                  'tensorflow_thread_API_values': {
                      'intra': tf.config.threading.get_intra_op_parallelism_threads(),
                      'inter': tf.config.threading.get_inter_op_parallelism_threads()},
                  'tensorflow_visible_GPU_count': 0,
                  'seed_boundary': 'pytest setup hook before original unittest setUp',
                  'all_RNG_or_graph_determinism_claimed': False}
        if (record['torch_cpu_threads'] != 1 or record['torch_interop_threads'] != 1 or
                any(v != '1' for v in record['tensorflow_thread_env'].values())):
            raise ValueError('CPU numerical thread controls differ')
        self.emit('numerical_backend_gate', record)
        return record


def production_modules(root, expected, packages, cache=None):
    """Audit file/spec and namespace search paths. / 核对文件与命名空间路径。"""
    cache = {} if cache is None else cache
    loaded = {}

    def directory(value):
        path = Path(value)
        key = ('directory', str(path))
        if key not in cache:
            name = relative(path, root)
            if path.is_symlink() or not path.is_dir():
                raise ValueError('production namespace is not a source directory')
            if name != '.' and not any(p.startswith(name + '/') for p in expected):
                raise ValueError('production namespace has no source inventory')
            cache[key] = name
        return cache[key]

    for name, module in list(sys.modules.items()):
        if not any(name == p or name.startswith(p + '.') for p in packages):
            continue
        paths = [directory(p) for p in getattr(module, '__path__', [])]
        spec = getattr(module, '__spec__', None)
        spec_paths = [directory(p) for p in (getattr(spec, 'submodule_search_locations', None) or [])]
        file = getattr(module, '__file__', None)
        if file is None:
            if not paths or getattr(spec, 'origin', None) is not None:
                raise ValueError('production pathless module lacks reviewed namespace identity')
            loaded[name] = {'path': None, 'sha256': None, 'namespace_paths': paths,
                            'spec_search_paths': spec_paths}
            continue
        path = Path(file)
        key = ('file', str(path))
        if key not in cache:
            source = relative(path, root)
            if path.is_symlink() or source not in expected or sha(path.read_bytes()) != expected[source]['sha256']:
                raise ValueError('production import identity differs')
            cache[key] = source
        source = cache[key]
        origin = getattr(spec, 'origin', file)
        if origin is None or Path(origin).resolve() != path.resolve():
            raise ValueError('production import spec differs')
        loaded[name] = {'path': source, 'sha256': expected[source]['sha256'],
                        'namespace_paths': paths, 'spec_search_paths': spec_paths}
    if not loaded:
        raise ValueError('no actual upstream production module imported')
    return loaded


def process_guard(enabled, denied):
    """Reject Python-audited process launches; not native/OS sandboxing.

    拒绝 Python 审计可见的进程启动，不声称阻断全部原生库系统调用。
    """
    if enabled is not None and enabled is not True:
        raise ValueError('process guard must be an explicit true request')
    if enabled is True and not hasattr(sys, 'addaudithook'):
        raise ValueError('Python process audit requires Python 3.8 or newer')
    active = {'value': enabled is True}

    def audit(event, args):
        if active['value'] and (event in {'subprocess.Popen', 'os.system', 'os.fork',
                                         'os.forkpty', 'os.posix_spawn'} or
                                event.startswith(('os.exec', 'os.spawn'))):
            denied.append({'event': event, 'reason': 'unreviewed_external_process'})
            raise PermissionError('unreviewed external process')
    if enabled:
        sys.addaudithook(audit)
    return active


def execute(config):
    root = Path(config['execution_root']).resolve()
    source_logs = reviewed_source_logs(config['source_files'], config.get('allowed_source_logs'))
    if (source_logs is not None and 'cycle_source_proofs' in source_logs
            and os.environ.get('OVERWRITE_DEBUG') != source_logs['overwrite_debug']):
        raise ValueError('source-supported cycle log directory option differs')
    expected = validate_tree(root, config['source_files'], source_logs)
    aliases = config.get('pathless_aliases', {})
    aliases_hash = sha(json.dumps(aliases, sort_keys=True, ensure_ascii=False,
                                 separators=(',', ':'), allow_nan=False).encode())
    for alias in aliases.values():
        if alias['source_path'] not in expected or expected[alias['source_path']]['sha256'] != alias['source_sha256']:
            raise ValueError('pathless alias source identity differs')
    if tuple(sys.version_info[:2]) != tuple(config['python_minor']):
        raise ValueError('reference interpreter minor mismatch')
    if sys.version_info < (3, 8) and not any(
            name.lower().replace('_', '-') == 'importlib-metadata'
            for name in config['dependency_versions']):
        raise ValueError('Python 3.7 requires an explicit locked metadata backport')
    installed = {name: metadata.version(name)
                 for name in config['dependency_versions']}
    if installed != config['dependency_versions']:
        raise ValueError('dependency lock mismatch')
    sys.dont_write_bytecode = True
    # Source imports, including test helpers, must come from the prepared role.
    sys.path[:0] = [str(root / value) for value in config['import_roots']]
    collected, selected, deselected, reports, collection_errors, denied = [], [], [], [], [], []
    wanted = set(config['selectors'])
    started = time.perf_counter()
    progress = config.get('progress_path')
    if progress is not None:
        progress = Path(progress).resolve()
        try:
            progress.relative_to(root)
        except ValueError:
            pass
        else:
            raise ValueError('progress output must remain outside upstream source')
        with progress.open('x') as stream:
            stream.write('')

    def emit(kind, payload):
        if progress is not None:
            event = {'event': kind, 'elapsed_seconds': time.perf_counter() - started,
                     'payload': payload}
            with progress.open('a') as stream:
                stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + '\n')

    numerical = NumericalState(config.get('numerical_state'), installed, emit)
    observed, identity_cache, backend_gates = {}, {}, []

    def audit_imports():
        current = production_modules(root, expected, config['production_packages'], identity_cache)
        observed.update(current)
        return current

    previous = network_guard(config['network_mode'], denied)
    process_denials = []
    try:
        numerical.bootstrap()
        import pytest
    except BaseException:
        restore_network(previous)
        raise

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
            emit('collection', {'collected_all': collected, 'selected': selected,
                                'deselected': deselected, 'missing': sorted(wanted - set(selected)),
                                'collection_errors': collection_errors})
            if numerical.enabled and not collection_errors:
                audit_imports()
                gate = numerical.gate()
                backend_gates.append(gate)

        @pytest.hookimpl(tryfirst=True)
        def pytest_runtest_setup(self, item):
            if numerical.enabled:
                audit_imports()
                numerical.reset(item.nodeid, 'pytest_setup_hook')

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
            emit('phase_report', reports[-1])
            if numerical.enabled and report.when == 'teardown':
                audit_imports()

    process_state = process_guard(config.get('deny_external_processes'), process_denials)
    try:
        plugins = reviewed_plugins(config.get('pytest_plugins', []), installed)
        options = reviewed_pytest_options(root, expected, config)
        code = int(pytest.main(['-c', '/dev/null', '--rootdir=' + str(root),
                               '--confcutdir=' + str(root), '--import-mode=importlib',
                               '-p', 'no:cacheprovider', '-q',
                               *options,
                               *[str(root / value) for value in config['test_files']]],
                              plugins=[Recorder(), *plugins]))
    finally:
        process_state['value'] = False
        restore_network(previous)
    validate_tree(root, config['source_files'], source_logs)
    # Recheck bytes without the during-run hash cache after the complete source audit.
    observed.update(production_modules(root, expected, config['production_packages']))
    loaded = observed
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
            'process_denials': process_denials,
            'source_before_after_verified': True, 'dependency_versions': installed,
            'allowed_source_logs': source_logs,
            'runtime_log_artifacts': source_log_records(root, source_logs),
            'explicit_test_plugins': config.get('pytest_plugins', []),
            'restored_upstream_pytest_options': options,
            'numerical_state_config': config.get('numerical_state'),
            'numerical_seed_events': numerical.events,
            'numerical_backend_gates': backend_gates,
            'progress_events_written': progress is not None,
            'python_version': sys.version, 'elapsed_seconds': time.perf_counter() - started,
            'peak_rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss /
                            (1024 * 1024 if sys.platform == 'darwin' else 1024),
            'worker_CPU_seconds': resource.getrusage(resource.RUSAGE_SELF).ru_utime +
                                  resource.getrusage(resource.RUSAGE_SELF).ru_stime,
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
