"""Cycle artifacts retain all source invariants. / 周期日志不掩盖源码变化。"""
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


def fixture(root):
    paths = ['autogpt/logs.py', 'autogpt/log_cycle/log_cycle.py',
             'autogpt/memory/message_history.py', 'tests/unit/test_message_history.py']
    for name in paths:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('# Owned source-proof fixture, not upstream code.\n')
    (root / 'autogpt/__init__.py').write_text('value = 7\n')
    files = inventory(root)
    hashes = {row['path']: row['sha256'] for row in files}
    policy = {'source_path': paths[0], 'source_sha256': hashes[paths[0]],
              'files': ['logs/activity.log', 'logs/error.log',
                        'logs/DEBUG/auto_gpt/000/0_prompt_summary.json',
                        'logs/DEBUG/auto_gpt/000/1_summary.txt',
                        'logs/DEBUG/auto_gpt/000/2_prompt_summary.json',
                        'logs/DEBUG/auto_gpt/000/3_summary.txt'],
              'max_total_bytes': 1048576, 'overwrite_debug': '1',
              'cycle_source_proofs': [{'path': p, 'sha256': hashes[p]} for p in paths[1:]]}
    return files, policy


@pytest.mark.parametrize('mutation', ['proof', 'missing_source', 'directory', 'extra_file'])
def test_cycle_policy_requires_source_proofs_and_exact_paths(tmp_path, mutation):
    files, policy = fixture(tmp_path)
    if mutation == 'proof':
        policy['cycle_source_proofs'][1]['sha256'] = '0' * 64
    elif mutation == 'missing_source':
        files = [row for row in files if row['path'] != 'autogpt/log_cycle/log_cycle.py']
    elif mutation == 'directory':
        policy['overwrite_debug'] = '0'
    else:
        policy['files'].append('logs/DEBUG/auto_gpt/000/4_summary.txt')
    with pytest.raises(ValueError, match='unreviewed'):
        worker.reviewed_source_logs(files, policy)


def test_cycle_policy_needs_source_supported_environment_option(tmp_path, monkeypatch):
    files, policy = fixture(tmp_path)
    monkeypatch.delenv('OVERWRITE_DEBUG', raising=False)
    with pytest.raises(ValueError, match='directory option differs'):
        worker.execute({'execution_root': str(tmp_path), 'source_files': files,
                        'allowed_source_logs': policy})


@pytest.mark.parametrize('mutation', ['source', 'unlisted', 'hardlink', 'symlink', 'large'])
def test_cycle_logs_cannot_hide_source_changes_or_unbounded_outputs(tmp_path, mutation):
    files, policy = fixture(tmp_path)
    target = tmp_path / policy['files'][2]
    target.parent.mkdir(parents=True)
    target.write_bytes(b'owned cycle output')
    if mutation == 'source':
        (tmp_path / 'autogpt/memory/message_history.py').write_text('changed = True\n')
    elif mutation == 'unlisted':
        (target.parent / '4_summary.txt').write_bytes(b'')
    elif mutation == 'hardlink':
        os.link(target, target.parent / '1_summary.txt')
    elif mutation == 'symlink':
        target.unlink()
        target.symlink_to(tmp_path / 'autogpt/memory/message_history.py')
    else:
        target.write_bytes(b'x' * 1048577)
    with pytest.raises(ValueError):
        worker.validate_tree(tmp_path, files, policy)


def test_actual_child_retains_cycle_artifact_hashes_without_content(tmp_path):
    root = tmp_path / 'source'
    _, policy = fixture(root)
    (root / 'logs').mkdir()
    (root / 'test_owned.py').write_text(
        'from pathlib import Path\nimport autogpt\n'
        'def test_value():\n    assert autogpt.value == 7\n'
        '    root = Path(autogpt.__file__).parent.parent\n'
        '    names = ' + repr(policy['files']) + '\n'
        '    for name in names:\n'
        '        path = root / name\n        path.parent.mkdir(parents=True, exist_ok=True)\n'
        '        path.write_text("owned private cycle output")\n')
    files = inventory(root)
    scratch = tmp_path / 'scratch'
    scratch.mkdir()
    output = scratch / 'result.json'
    config = {'execution_root': str(root), 'source_files': files,
              'python_minor': list(sys.version_info[:2]),
              'dependency_versions': {'pytest': importlib.metadata.version('pytest')},
              'import_roots': ['.'], 'selectors': ['test_owned.py::test_value'],
              'network_mode': 'deny', 'test_files': ['test_owned.py'],
              'production_packages': ['autogpt'], 'instance_id': 'owned-cycle-fixture',
              'role': 'base', 'base_commit': 'a' * 40, 'test_patch_sha256': 'b' * 64,
              'code_patch_sha256': None, 'environment_sha256': 'c' * 64,
              'source_files_index_sha256': 'd' * 64, 'cpu_seconds': 30,
              'output_path': str(output), 'allowed_source_logs': policy}
    path = scratch / 'config.json'
    path.write_text(json.dumps(config))
    run = subprocess.run([sys.executable, '-I', '-B', worker.__file__, str(path)],
                         cwd=scratch, env={'PATH': '/usr/bin:/bin', 'HOME': str(scratch),
                                          'TMPDIR': str(scratch), 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
                                          'OVERWRITE_DEBUG': '1'}, capture_output=True, timeout=45)
    assert run.returncode == 0, run.stderr.decode()
    result = json.loads(output.read_bytes())
    assert result['results'][0]['state'] == 'passed'
    assert result['source_before_after_verified']
    assert result['runtime_log_artifacts'] == [
        {'path': name, 'bytes': 26,
         'sha256': hashlib.sha256(b'owned private cycle output').hexdigest()}
        for name in policy['files']]
    assert 'owned private cycle output' not in output.read_text()
    assert worker.validate_tree(root, files, policy)
