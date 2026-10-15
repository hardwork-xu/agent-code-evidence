"""Exact-source preparation and hostile input boundaries. / 精确源码与异常输入边界。"""
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest

from benchmarks.known_task_execution import prepare as p


CODE_PATCH = ('diff --git a/module.py b/module.py\n--- a/module.py\n+++ b/module.py\n'
              '@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 2\n')
TEST_PATCH = ('diff --git a/test_owned.py b/test_owned.py\nnew file mode 100644\n'
              '--- /dev/null\n+++ b/test_owned.py\n@@ -0,0 +1 @@\n'
              '+raise RuntimeError("source data must never execute during preparation")\n')


def archive(path, entries):
    with tarfile.open(path, 'w:gz') as out:
        for name, raw in entries:
            info = tarfile.TarInfo(name)
            if raw is None:
                info.type = tarfile.SYMTYPE
                info.linkname = '../../outside'
                out.addfile(info)
            else:
                info.size = len(raw)
                out.addfile(info, io.BytesIO(raw))
    return p.digest(path.read_bytes())


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    cache = tmp_path / 'cache'
    (cache / 'source-archives').mkdir(parents=True)
    source = cache / 'source-archives/owned.tar.gz'
    archive_sha = archive(source, [('root/module.py', b'VALUE = 1\n'),
                                   ('root/LICENSE', b'Owned fixture license text.\n')])
    row = {'instance_id': 'owned__source-1', 'repo': 'owned/source', 'base_commit': 'a' * 40,
           'patch': CODE_PATCH, 'test_patch': TEST_PATCH,
           'F2P': "['test_owned.py:None:test_change']", 'P2P': '[]',
           'test_command': 'this field is data, never executed',
           'Dockerfile': 'this field is data, never executed'}
    data = tmp_path / 'test.csv'
    with data.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    monkeypatch.setattr(p, 'DATASET_SHA256', p.digest(data.read_bytes()))
    pin = {'instance_id': row['instance_id'], 'repo': row['repo'],
           'base_commit': row['base_commit'], 'archive': 'source-archives/owned.tar.gz',
           'archive_sha256': archive_sha}
    pins = tmp_path / 'sources.json'
    pins.write_text(json.dumps({'tasks': [pin]}))
    return data, cache, row, pins, pin


def test_complete_preparation_preserves_original_and_separates_roles(inputs, tmp_path):
    data, cache, row, pins, _ = inputs
    output = tmp_path / 'prepared'
    result = p.prepare(data, cache, row['instance_id'], output, pins)
    assert result['upstream_executed'] is False
    assert result['F2P'] == ['test_owned.py:None:test_change']
    assert result['P2P'] == []
    assert (output / 'base_tests/module.py').read_bytes() == b'VALUE = 1\n'
    assert (output / 'fixed_tests/module.py').read_bytes() == b'VALUE = 2\n'
    for role in ['base_tests', 'fixed_tests']:
        assert (output / role / 'test_owned.py').read_text().startswith('raise RuntimeError')
        assert (output / role / 'module.py').stat().st_mode & 0o777 == 0o444
        assert (output / role).stat().st_mode & 0o777 == 0o555
    assert json.loads((output / 'manifest.json').read_bytes()) == result
    assert result['roles'][0]['source_files_index_sha256'] != result['roles'][1]['source_files_index_sha256']
    with pytest.raises(FileExistsError):
        p.prepare(data, cache, row['instance_id'], output, pins)


@pytest.mark.parametrize('name', ['', '/root/file', '../file', 'root/../file',
                                  'root//file', 'root/./file', 'root\\file',
                                  'root/with\0nul', 'C:/file', 'root/.git/config'])
def test_unsafe_source_paths_rejected(name):
    with pytest.raises(ValueError, match='unsafe'):
        p.safe_path(name)


@pytest.mark.parametrize('kind', ['traversal', 'multiple_roots', 'duplicate', 'required_link',
                                  'total_cap', 'checksum'])
def test_archive_identity_and_resource_failures(inputs, tmp_path, kind):
    _, _, original, _, _ = inputs
    row = dict(original)
    entries = [('root/module.py', b'VALUE = 1\n')]
    if kind == 'traversal':
        entries.append(('root/../escape', b'data'))
    elif kind == 'multiple_roots':
        entries.append(('other/a', b'data'))
    elif kind == 'duplicate':
        entries.append(entries[0])
    elif kind == 'required_link':
        row['repo'] = 'yt-dlp/yt-dlp'
        entries.append(('root/link', None))
    path = tmp_path / 'source.tar.gz'
    checksum = archive(path, entries)
    if kind == 'checksum':
        checksum = '0' * 64
    with pytest.raises(ValueError):
        p.archive_files(path, checksum, row, max_total=1 if kind == 'total_cap' else 1024)


def test_omissions_are_explicit_and_required_assets_are_never_silently_omitted(inputs, tmp_path):
    _, _, row, _, _ = inputs
    path = tmp_path / 'source.tar.gz'
    checksum = archive(path, [('root/module.py', b'VALUE = 1\n'), ('root/alias', None),
                              ('root/large.bin', b'x' * (5 * 1024**2 + 1))])
    files, omissions = p.archive_files(path, checksum, row)
    assert set(files) == {'module.py'}
    assert {r['path'] for r in omissions} == {'alias', 'large.bin'}
    row = dict(row, patch=CODE_PATCH.replace('module.py', 'large.bin'))
    with pytest.raises(ValueError, match='required'):
        p.archive_files(path, checksum, row)


@pytest.mark.parametrize('kind', ['garbage', 'rename', 'binary', 'delete', 'duplicate', 'no_hunk'])
def test_unsupported_patches_refused(kind):
    patch = CODE_PATCH
    if kind == 'garbage':
        patch = 'arbitrary command is not a patch'
    elif kind == 'rename':
        patch = patch.replace('b/module.py', 'b/other.py')
    elif kind == 'binary':
        patch += 'GIT binary patch\n'
    elif kind == 'delete':
        patch += 'deleted file mode 100644\n'
    elif kind == 'duplicate':
        patch += CODE_PATCH
    else:
        patch = patch.split('@@')[0]
    with pytest.raises(ValueError):
        p.patch_blocks(patch)


def test_patch_context_and_count_must_match():
    with pytest.raises(ValueError, match='context'):
        p.apply_patch('VALUE = 3\n', CODE_PATCH)
    with pytest.raises(ValueError, match='count'):
        p.apply_patch('VALUE = 1\n', CODE_PATCH.replace('@@ -1 +1 @@', '@@ -1,2 +1 @@'))


def test_pure_insertion_uses_the_line_after_the_zero_count_anchor():
    patch = ('diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n'
             '@@ -1,0 +2 @@\n+inserted\n')
    assert p.apply_patch('first\nlast\n', patch) == 'first\ninserted\nlast\n'


@pytest.mark.parametrize('header', ['@@ -999,0 +1 @@', '@@ -1 +999 @@', '@@ -0 +1 @@'])
def test_invalid_hunk_positions_cannot_silently_change_identity(header):
    with pytest.raises(ValueError, match='hunk'):
        p.apply_patch('VALUE = 1\n', CODE_PATCH.replace('@@ -1 +1 @@', header))


@pytest.mark.parametrize('kind', ['git_ancestor', 'unknown_task', 'base_mismatch', 'archive_escape'])
def test_preparation_does_not_enter_git_or_change_fixed_identity(inputs, tmp_path, kind):
    data, cache, row, pins, pin = inputs
    output = tmp_path / 'new-source'
    if kind == 'git_ancestor':
        (tmp_path / '.git').mkdir()
    elif kind == 'unknown_task':
        pin['instance_id'] = 'other'
    elif kind == 'base_mismatch':
        pin['base_commit'] = 'b' * 40
    else:
        pin['archive'] = '../arbitrary.tar.gz'
    pins.write_text(json.dumps({'tasks': [pin]}))
    with pytest.raises(ValueError):
        p.prepare(data, cache, row['instance_id'], output, pins)
    assert not output.exists()


def test_dataset_hash_and_literal_parser_do_not_execute(inputs, tmp_path):
    data, _, row, _, _ = inputs
    with pytest.raises(ValueError, match='hash'):
        p.task_row(data, row['instance_id'], '0' * 64)
    row['F2P'] = '__import__("os").system("false")'
    with data.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    with pytest.raises(ValueError):
        p.task_row(data, row['instance_id'], p.digest(data.read_bytes()))
    assert list(tmp_path.glob('unrequested*')) == []


def test_bilingual_cli_help_does_not_import_upstream():
    run = subprocess.run([sys.executable, '-B', '-m', 'benchmarks.known_task_execution.prepare',
                          '--help'], cwd=Path(__file__).parents[1], capture_output=True,
                         text=True, timeout=20)
    assert run.returncode == 0
    assert '准备固定源码角色' in run.stdout and '--output' in run.stdout
