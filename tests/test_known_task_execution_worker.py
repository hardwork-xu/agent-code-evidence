"""Counterexamples for the native test adapter. / 原生测试适配器反例。"""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from benchmarks.known_task_execution import worker


def files(root):
    return [{'path': p.relative_to(root).as_posix(),
             'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
             'bytes': p.stat().st_size} for p in sorted(root.rglob('*')) if p.is_file()]


@pytest.mark.parametrize('mutation', ['changed', 'added', 'removed', 'bytecode', 'symlink'])
def test_full_source_identity_rejects_mutations(tmp_path, mutation):
    target = tmp_path / 'a.py'
    target.write_bytes(b'value = 1\n')
    index = files(tmp_path)
    if mutation == 'changed':
        target.write_bytes(b'value = 2\n')
    elif mutation == 'added':
        (tmp_path / 'b.py').write_bytes(b'')
    elif mutation == 'removed':
        target.unlink()
    elif mutation == 'bytecode':
        (tmp_path / 'a.pyc').write_bytes(b'foreign')
    else:
        (tmp_path / 'b.py').symlink_to(target)
    with pytest.raises(ValueError):
        worker.validate_tree(tmp_path, index)


def test_network_fence_preserves_local_tcp_and_rejects_egress():
    denied = []
    old = worker.network_guard('loopback', denied)
    try:
        with socket.socket() as server, socket.socket() as client:
            server.bind(('127.0.0.1', 0))
            server.listen(1)
            client.connect(server.getsockname())
            peer, _ = server.accept()
            peer.close()
        with pytest.raises(PermissionError):
            socket.getaddrinfo('unreviewed.example', 443)
        assert denied == [{'host': 'unreviewed.example',
                           'reason': 'unreviewed_network_destination'}]
    finally:
        worker.restore_network(old)


@pytest.mark.parametrize('body,expected,phase', [
    ('def test_value():\n    assert fixturepkg.value == 1\n', 'passed', 'call'),
    ('def test_value():\n    assert fixturepkg.value == 2\n', 'failed', 'call'),
    ('@pytest.mark.skip(reason="fixture")\ndef test_value():\n    assert False\n', 'skipped', 'setup'),
    ('@pytest.mark.xfail(reason="fixture")\ndef test_value():\n    assert False\n', 'xfailed', 'call'),
    ('@pytest.mark.xfail(reason="fixture")\ndef test_value():\n    assert True\n', 'xpassed', 'call'),
    ('@pytest.mark.xfail(reason="fixture", strict=True)\ndef test_value():\n    assert True\n', 'xpassed', 'call'),
    ('def teardown_function():\n    raise RuntimeError("fixture cleanup")\n'
     'def test_value():\n    assert fixturepkg.value == 1\n', 'error', 'teardown'),
])
def test_actual_child_results_do_not_hide_failures(tmp_path, body, expected, phase):
    source = tmp_path / 'source'
    package = source / 'fixturepkg'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('value = 1\n')
    (source / 'test_fixture.py').write_text('import fixturepkg\nimport pytest\n' + body +
                                         '\ndef test_unselected():\n    assert False\n')
    scratch = tmp_path / 'scratch'
    scratch.mkdir()
    output = tmp_path / 'result.json'
    config = {
        'execution_root': str(source), 'source_files': files(source),
        'python_minor': list(sys.version_info[:2]),
        'dependency_versions': {'pytest': importlib.metadata.version('pytest')},
        'import_roots': ['.'], 'selectors': ['test_fixture.py::test_value'],
        'network_mode': 'deny', 'test_files': ['test_fixture.py'],
        'production_packages': ['fixturepkg'], 'instance_id': 'owned-fixture',
        'role': 'base', 'base_commit': 'a' * 40, 'test_patch_sha256': 'b' * 64,
        'code_patch_sha256': None, 'environment_sha256': 'c' * 64,
        'source_files_index_sha256': 'd' * 64, 'cpu_seconds': 30,
        'output_path': str(output),
    }
    config_path = tmp_path / 'config.json'
    config_path.write_text(json.dumps(config))
    environment = {'PATH': str(Path(sys.executable).parent) + ':/usr/bin:/bin',
                   'HOME': str(scratch), 'TMPDIR': str(scratch),
                   'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'}
    run = subprocess.run([sys.executable, '-I', '-B', worker.__file__, str(config_path)],
                         cwd=scratch, env=environment, capture_output=True, timeout=45)
    assert output.is_file(), run.stderr.decode()
    result = json.loads(output.read_bytes())
    assert run.returncode == result['process_exit_code']
    assert result['results'][0]['state'] == expected
    assert result['results'][0]['phase'] == phase
    assert result['selected'] == ['test_fixture.py::test_value']
    assert result['deselected'] == ['test_fixture.py::test_unselected']
    assert result['source_before_after_verified']
    assert result['loaded_source_modules']['fixturepkg']['path'] == 'fixturepkg/__init__.py'
    assert not list(source.rglob('*.pyc'))


def test_unknown_network_mode_is_not_silently_allowed():
    with pytest.raises(ValueError):
        worker.network_guard('unrestricted', [])


def test_crash_category_does_not_disclose_stack_path():
    class Crash:
        message = 'MemoryError: allocation denied in /private/example'
    class Report:
        class Long:
            reprcrash = Crash()
        longrepr = Long()
    assert worker.error_class(Report()) == 'MemoryError'


@pytest.mark.parametrize('names,versions', [
    (['unreviewed.plugin'], {}), (['pytest_asyncio.plugin'], {}),
    (['pytest_asyncio.plugin', 'pytest_asyncio.plugin'], {'pytest-asyncio': '0.21.1'}),
    ('pytest_asyncio.plugin', {'pytest-asyncio': '0.21.1'}),
])
def test_unreviewed_or_unlocked_plugins_are_rejected(names, versions):
    with pytest.raises(ValueError):
        worker.reviewed_plugins(names, versions)
