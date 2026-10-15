"""Bounded source-adjacent outputs never hide source mutations. / 日志不掩盖源码变化。"""
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys

import pytest

from benchmarks.known_task_execution import worker


def inventory(root):
    return [{'path': p.relative_to(root).as_posix(), 'bytes': p.stat().st_size,
             'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in sorted(root.rglob('*')) if p.is_file()]


def source_and_policy(root):
    package = root / 'autogpt'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('value = 1\n')
    (package / 'logs.py').write_text('# Owned source-proof fixture, not upstream code.\n')
    files = inventory(root)
    request = {'source_path': 'autogpt/logs.py',
               'source_sha256': next(r['sha256'] for r in files if r['path'] == 'autogpt/logs.py'),
               'files': ['logs/activity.log', 'logs/error.log'], 'max_total_bytes': 1048576}
    return files, request


@pytest.mark.parametrize('mutation', ['proof', 'names', 'cap', 'bool', 'extra'])
def test_unreviewed_log_exceptions_are_rejected(tmp_path, mutation):
    files, policy = source_and_policy(tmp_path)
    if mutation == 'proof':
        policy['source_sha256'] = '0' * 64
    elif mutation == 'names':
        policy['files'].append('logs/replacement.py')
    elif mutation == 'cap':
        policy['max_total_bytes'] = 2 * 1048576
    elif mutation == 'bool':
        policy['max_total_bytes'] = True
    else:
        policy['extra'] = True
    with pytest.raises(ValueError, match='unreviewed'):
        worker.reviewed_source_logs(files, policy)


@pytest.mark.parametrize('mutation', ['source', 'extra', 'large', 'hardlink', 'symlink'])
def test_allowed_logs_do_not_hide_other_changes(tmp_path, mutation):
    files, request = source_and_policy(tmp_path)
    policy = worker.reviewed_source_logs(files, request)
    (tmp_path / 'logs').mkdir()
    target = tmp_path / 'logs/activity.log'
    target.write_bytes(b'owned fixture output\n')
    if mutation == 'source':
        (tmp_path / 'autogpt/__init__.py').write_text('value = 2\n')
    elif mutation == 'extra':
        (tmp_path / 'logs/other.log').write_bytes(b'')
    elif mutation == 'large':
        target.write_bytes(b'x' * 1048577)
    elif mutation == 'hardlink':
        os.link(target, tmp_path / 'logs/error.log')
    else:
        target.unlink()
        target.symlink_to(tmp_path / 'autogpt/__init__.py')
    with pytest.raises(ValueError):
        worker.validate_tree(tmp_path, files, policy)


def test_actual_child_retains_source_identity_and_hashes_only_allowed_logs(tmp_path):
    root = tmp_path / 'source'
    _, policy = source_and_policy(root)
    (root / 'logs').mkdir()
    (root / 'test_owned.py').write_text(
        'from pathlib import Path\nimport autogpt\n'
        'def test_value():\n    assert autogpt.value == 1\n'
        '    root = Path(autogpt.__file__).parent.parent\n'
        '    (root / "logs/activity.log").write_text("owned private output")\n'
        '    (root / "logs/error.log").write_text("")\n')
    files = inventory(root)
    scratch = tmp_path / 'scratch'
    scratch.mkdir()
    output = scratch / 'result.json'
    config = {'execution_root': str(root), 'source_files': files,
              'python_minor': list(sys.version_info[:2]),
              'dependency_versions': {'pytest': importlib.metadata.version('pytest')},
              'import_roots': ['.'], 'selectors': ['test_owned.py::test_value'],
              'network_mode': 'deny', 'test_files': ['test_owned.py'],
              'production_packages': ['autogpt'], 'instance_id': 'owned-log-fixture',
              'role': 'base', 'base_commit': 'a' * 40, 'test_patch_sha256': 'b' * 64,
              'code_patch_sha256': None, 'environment_sha256': 'c' * 64,
              'source_files_index_sha256': 'd' * 64, 'cpu_seconds': 30,
              'output_path': str(output), 'allowed_source_logs': policy}
    path = scratch / 'config.json'
    path.write_text(json.dumps(config))
    run = subprocess.run([sys.executable, '-I', '-B', worker.__file__, str(path)],
                         cwd=scratch, env={'PATH': '/usr/bin:/bin', 'HOME': str(scratch),
                                          'TMPDIR': str(scratch), 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'},
                         capture_output=True, timeout=45)
    assert run.returncode == 0, run.stderr.decode()
    result = json.loads(output.read_bytes())
    assert result['results'][0]['state'] == 'passed'
    assert result['source_before_after_verified']
    assert result['runtime_log_artifacts'] == [
        {'path': 'logs/activity.log', 'bytes': 20,
         'sha256': hashlib.sha256(b'owned private output').hexdigest()},
        {'path': 'logs/error.log', 'bytes': 0, 'sha256': hashlib.sha256(b'').hexdigest()}]
    assert 'owned private output' not in output.read_text()
    assert worker.validate_tree(root, files, policy)


def test_explicit_process_guard_refuses_runtime_without_python_audit(monkeypatch):
    monkeypatch.delattr(sys, 'addaudithook')
    assert worker.process_guard(None, []) == {'value': False}
    with pytest.raises(ValueError, match='Python 3.8'):
        worker.process_guard(True, [])
