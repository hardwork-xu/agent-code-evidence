"""Owned adapter fixtures; numerical stubs here are not backend/SUT evidence."""
import copy
import hashlib
import importlib.metadata
import json
import subprocess
import sys
import types

import pytest

from benchmarks.known_task_execution import worker


def inventory(root):
    return [{'path': p.relative_to(root).as_posix(),
             'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size}
            for p in sorted(root.rglob('*')) if p.is_file()]


@pytest.mark.parametrize('change', ['seed', 'extra', 'missing', 'bool', 'order'])
def test_numerical_configuration_is_fixed_and_typed(monkeypatch, change):
    monkeypatch.setenv('PYTHONHASHSEED', '0')
    config = copy.deepcopy(worker.NUMERICAL_STATE)
    if change == 'seed':
        config['seed'] = 1
    elif change == 'extra':
        config['extra'] = True
    elif change == 'missing':
        del config['backend']
    elif change == 'bool':
        config['torch_threads'] = True
    else:
        config['per_node_reset'].reverse()
    with pytest.raises(ValueError, match='unreviewed numerical'):
        worker.NumericalState(config, {}, lambda *_: None)


def test_numerical_hash_seed_is_checked(monkeypatch):
    monkeypatch.delenv('PYTHONHASHSEED', raising=False)
    with pytest.raises(ValueError, match='hash seed'):
        worker.NumericalState(worker.NUMERICAL_STATE, {}, lambda *_: None)


def test_owned_spies_verify_torch_first_cpu_seeds_and_late_tensorflow(monkeypatch):
    # These spies verify adapter API calls/order, not numerical correctness.
    monkeypatch.setenv('PYTHONHASHSEED', '0')
    monkeypatch.setattr(worker, 'numerical_runtime_flags', lambda: {
        'ignore_environment': 0, 'isolated': 0, 'no_user_site': 1, 'hash_randomization': 0})
    for name in ['torch', 'numpy', 'tensorflow', 'keras']:
        monkeypatch.delitem(sys.modules, name, raising=False)
    calls, events = [], []
    torch = types.SimpleNamespace(
        random=types.SimpleNamespace(default_generator=types.SimpleNamespace(
            manual_seed=lambda seed: calls.append(('torch_cpu_seed', seed)))),
        set_num_threads=lambda n: calls.append(('torch_threads', n)),
        set_num_interop_threads=lambda n: calls.append(('torch_interop', n)))
    numpy = types.SimpleNamespace(random=types.SimpleNamespace(
        seed=lambda seed: calls.append(('numpy_seed', seed))))

    def dependency(name, versions):
        calls.append(('import', name))
        return {'torch': torch, 'numpy': numpy}[name]

    monkeypatch.setattr(worker, 'dependency_module', dependency)
    versions = {'torch': '2.2.2', 'numpy': '1.26.4', 'tensorflow': '2.16.2'}
    state = worker.NumericalState(worker.NUMERICAL_STATE, versions,
                                  lambda kind, event: events.append((kind, event)))
    state.bootstrap()
    assert calls[:4] == [('import', 'torch'), ('torch_threads', 1),
                         ('torch_interop', 1), ('import', 'numpy')]
    assert 'tensorflow' not in sys.modules and 'keras' not in sys.modules
    assert not state.events[0]['tensorflow_already_loaded']
    tensorflow = types.SimpleNamespace(__version__='2.16.2', random=types.SimpleNamespace(
        set_seed=lambda seed: calls.append(('loaded_tf_seed', seed))))
    monkeypatch.setitem(sys.modules, 'tensorflow', tensorflow)
    state.reset('test_owned.py::test_one', 'pytest_setup_hook')
    assert calls[-3:] == [('numpy_seed', 1337), ('torch_cpu_seed', 1337),
                          ('loaded_tf_seed', 1337)]
    assert state.events[-1]['nodeid'] == 'test_owned.py::test_one'
    assert state.events[-1]['called_apis'][-1] == 'loaded_tensorflow.random.set_seed'
    assert not state.events[-1]['JAX_rng_reset']
    assert 'before original unittest setUp' in state.events[-1]['boundary']
    assert len(events) == 2


def test_torch_bootstrap_rejects_preloaded_sut(monkeypatch):
    monkeypatch.setenv('PYTHONHASHSEED', '0')
    monkeypatch.setattr(worker, 'numerical_runtime_flags', lambda: {
        'ignore_environment': 0, 'isolated': 0, 'no_user_site': 1, 'hash_randomization': 0})
    monkeypatch.setitem(sys.modules, 'keras', types.ModuleType('keras'))
    state = worker.NumericalState(worker.NUMERICAL_STATE, {}, lambda *_: None)
    with pytest.raises(ValueError, match='before Torch-first'):
        state.bootstrap()


@pytest.mark.parametrize('flag,value', [('ignore_environment', 1), ('isolated', 1),
                                        ('no_user_site', 0), ('hash_randomization', 1)])
def test_env_string_does_not_prove_actual_hashseed_or_isolation(monkeypatch, flag, value):
    monkeypatch.setenv('PYTHONHASHSEED', '0')
    flags = {'ignore_environment': 0, 'isolated': 0, 'no_user_site': 1, 'hash_randomization': 0}
    flags[flag] = value
    monkeypatch.setattr(worker, 'numerical_runtime_flags', lambda: flags)
    with pytest.raises(ValueError, match='runtime must accept fixed hash seed'):
        worker.NumericalState(worker.NUMERICAL_STATE, {}, lambda *_: None)


@pytest.mark.parametrize('mutation', ['outside_path', 'outside_spec', 'pathless', 'changed_bytes'])
def test_production_module_and_namespace_paths_cannot_escape(tmp_path, monkeypatch, mutation):
    root = tmp_path / 'source'
    root.mkdir()
    module_path = root / '__init__.py'
    module_path.write_text('value = 1\n')
    expected = {row['path']: row for row in inventory(root)}
    module = types.ModuleType('owned_origin_fixture')
    module.__file__ = str(module_path)
    module.__spec__ = types.SimpleNamespace(origin=str(module_path), submodule_search_locations=[str(root)])
    module.__path__ = [str(root)]
    if mutation == 'outside_path':
        module.__path__ = [str(tmp_path)]
    elif mutation == 'outside_spec':
        module.__spec__.submodule_search_locations = [str(tmp_path)]
    elif mutation == 'pathless':
        module.__file__ = None
        module.__path__ = []
        module.__spec__ = None
    else:
        module_path.write_text('value = 2\n')
    monkeypatch.setitem(sys.modules, module.__name__, module)
    with pytest.raises(ValueError):
        worker.production_modules(root, expected, [module.__name__])


def test_reviewed_pathless_namespace_is_recorded(tmp_path, monkeypatch):
    root = tmp_path / 'source'
    root.mkdir()
    (root / 'a.py').write_text('value = 1\n')
    expected = {row['path']: row for row in inventory(root)}
    module = types.ModuleType('owned_namespace_fixture')
    module.__path__ = [str(root)]
    module.__spec__ = types.SimpleNamespace(origin=None, submodule_search_locations=[str(root)])
    monkeypatch.setitem(sys.modules, module.__name__, module)
    record = worker.production_modules(root, expected, [module.__name__])[module.__name__]
    assert record == {'path': None, 'sha256': None, 'namespace_paths': ['.'], 'spec_search_paths': ['.']}


def strict_source(tmp_path, extra=''):
    p = tmp_path / 'pyproject.toml'
    p.write_text('[tool.pytest.ini_options]\n'
                 'addopts = "--strict-markers --strict-config --durations=5 --snapshot-warn-unused"\n'
                 'markers = ["owned: fixture marker", "integration: integration fixture"]\n' + extra)
    expected = {row['path']: row for row in inventory(tmp_path)}
    config = {'strict_upstream_pytest': True,
              'upstream_pytest_config': {'path': 'pyproject.toml', 'sha256': expected['pyproject.toml']['sha256']}}
    return p, expected, config


def test_only_proven_strict_flags_and_markers_are_restored(tmp_path):
    _, expected, config = strict_source(tmp_path)
    options = worker.reviewed_pytest_options(tmp_path, expected, config)
    assert options == ['--strict-markers', '--strict-config', '--durations=5', '-o',
                       'markers=owned: fixture marker\nintegration: integration fixture']
    assert '--snapshot-warn-unused' not in options


@pytest.mark.parametrize('mutation', ['hash', 'flag', 'markers', 'false'])
def test_strict_options_refuse_changed_or_unproven_configuration(tmp_path, mutation):
    p, expected, config = strict_source(tmp_path)
    if mutation == 'hash':
        config['upstream_pytest_config']['sha256'] = '0' * 64
    elif mutation == 'false':
        config['strict_upstream_pytest'] = False
    else:
        text = p.read_text()
        text = text.replace('--durations=5', '--durations=7') if mutation == 'flag' else text.replace(
            '["owned: fixture marker", "integration: integration fixture"]', '"owned"')
        p.write_text(text)
        expected = {row['path']: row for row in inventory(tmp_path)}
        config['upstream_pytest_config']['sha256'] = expected['pyproject.toml']['sha256']
    with pytest.raises(ValueError):
        worker.reviewed_pytest_options(tmp_path, expected, config)


def test_private_progress_preserves_actual_collection_and_phase_reports(tmp_path):
    root = tmp_path / 'source'
    package = root / 'owned_progress_fixture'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('value = 1\n')
    (root / 'test_owned.py').write_text('import owned_progress_fixture\n'
                                       'def test_value():\n    assert owned_progress_fixture.value == 1\n')
    scratch = tmp_path / 'scratch'
    scratch.mkdir()
    output, progress = scratch / 'result.json', scratch / 'progress.jsonl'
    config = {'execution_root': str(root), 'source_files': inventory(root),
              'python_minor': list(sys.version_info[:2]),
              'dependency_versions': {'pytest': importlib.metadata.version('pytest')},
              'import_roots': ['.'], 'selectors': ['test_owned.py::test_value'],
              'network_mode': 'deny', 'test_files': ['test_owned.py'],
              'production_packages': ['owned_progress_fixture'], 'instance_id': 'owned-fixture',
              'role': 'base', 'base_commit': 'a' * 40, 'test_patch_sha256': 'b' * 64,
              'code_patch_sha256': None, 'environment_sha256': 'c' * 64,
              'source_files_index_sha256': 'd' * 64, 'cpu_seconds': 30,
              'output_path': str(output), 'progress_path': str(progress)}
    config_path = scratch / 'config.json'
    config_path.write_text(json.dumps(config))
    process = subprocess.run([sys.executable, '-I', '-B', worker.__file__, str(config_path)],
                             cwd=scratch, env={'PATH': '/usr/bin:/bin', 'HOME': str(scratch),
                                              'TMPDIR': str(scratch), 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'},
                             capture_output=True, timeout=45)
    assert process.returncode == 0, process.stderr.decode()
    result = json.loads(output.read_bytes())
    events = [json.loads(line) for line in progress.read_text().splitlines()]
    assert events[0]['event'] == 'collection'
    assert events[0]['payload']['missing'] == []
    assert [event['payload'] for event in events if event['event'] == 'phase_report'] == result['phase_reports']
    assert [row['phase'] for row in result['phase_reports']] == ['setup', 'call', 'teardown']
    assert result['loaded_source_modules']['owned_progress_fixture']['sha256']


def test_python_process_launch_guard_is_explicit_and_rejects_child_creation():
    denied = []
    active = worker.process_guard(True, denied)
    try:
        with pytest.raises(PermissionError, match='external process'):
            subprocess.run([sys.executable, '-c', 'raise AssertionError("must not execute")'])
    finally:
        active['value'] = False
    assert denied == [{'event': 'subprocess.Popen', 'reason': 'unreviewed_external_process'}]
    with pytest.raises(ValueError):
        worker.process_guard(False, [])
