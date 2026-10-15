"""Owned fixed-source parser boundaries / 自编固定源码解析边界，不执行上游。"""
import io
import tarfile

import pytest

from benchmarks.known_task_execution import prepare as p


def change(body='@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 2\n'):
    return ('diff --git a/module.py b/module.py\n'
            '--- a/module.py\n+++ b/module.py\n' + body)


@pytest.mark.parametrize('separator', ['\x85', '\u2028', '\u2029'])
def test_patch_counts_physical_lf_not_unicode_string_separators(separator):
    before = 'TEXT = "a' + separator + 'b"\nVALUE = 1\n'
    patch = change('@@ -2 +2 @@\n-VALUE = 1\n+VALUE = 2\n')
    assert p.apply_patch(before, patch) == before.replace('VALUE = 1', 'VALUE = 2')


@pytest.mark.parametrize('old,new', [
    ('a/other.py', 'b/other.py'), ('a/other.py', 'b/module.py'),
    ('a/module.py', 'b/other.py'), ('/dev/null', 'b/module.py')])
def test_file_markers_must_match_diff_identity_and_creation_mode(old, new):
    patch = change().replace('--- a/module.py', '--- ' + old)
    patch = patch.replace('+++ b/module.py', '+++ ' + new)
    with pytest.raises(ValueError, match='markers'):
        p.patch_blocks(patch)


def test_modified_file_must_exist_even_for_zero_old_lines():
    patch = change('@@ -0,0 +1 @@\n+VALUE = 2\n')
    with pytest.raises(ValueError, match='existence'):
        p.derive_roles({}, {'patch': patch, 'test_patch': ''})
    # An existing empty file is a valid modification, distinct from creation.
    roles = p.derive_roles({'module.py': b''}, {'patch': patch, 'test_patch': ''})
    assert roles['base_tests']['module.py'] == b''
    assert roles['fixed_tests']['module.py'] == b'VALUE = 2\n'


def test_new_file_creation_must_not_replace_existing_empty_file():
    patch = ('diff --git a/module.py b/module.py\nnew file mode 100644\n'
             '--- /dev/null\n+++ b/module.py\n@@ -0,0 +1 @@\n+VALUE = 2\n')
    with pytest.raises(ValueError, match='existence'):
        p.derive_roles({'module.py': b''}, {'patch': patch, 'test_patch': ''})
    roles = p.derive_roles({}, {'patch': patch, 'test_patch': ''})
    assert roles['base_tests'] == {}
    assert roles['fixed_tests']['module.py'] == b'VALUE = 2\n'


@pytest.mark.parametrize('name', ['.GIT/config', '.Git/HEAD', 'nested/.gIt/config'])
def test_case_variants_of_git_metadata_are_rejected_on_all_hosts(name):
    with pytest.raises(ValueError, match='unsafe'):
        p.safe_path(name)
    assert str(p.safe_path('module/git_utils.py')) == 'module/git_utils.py'
    assert str(p.safe_path('.gitignore')) == '.gitignore'


def test_patch_required_nonregular_member_is_not_silently_omitted(tmp_path):
    archive = tmp_path / 'owned.tar.gz'
    with tarfile.open(archive, 'w:gz') as out:
        item = tarfile.TarInfo('root/module.py')
        item.type = tarfile.SYMTYPE
        item.linkname = 'other.py'
        out.addfile(item)
        regular = tarfile.TarInfo('root/other.py')
        raw = b'VALUE = 1\n'
        regular.size = len(raw)
        out.addfile(regular, io.BytesIO(raw))
    row = {'repo': 'owned/source', 'instance_id': 'owned__source-1',
           'patch': change(), 'test_patch': ''}
    with pytest.raises(ValueError, match='nonregular'):
        p.archive_files(archive, p.digest(archive.read_bytes()), row)
    row['patch'] = ''
    files, omissions = p.archive_files(archive, p.digest(archive.read_bytes()), row)
    assert set(files) == {'other.py'}
    assert omissions == [{'path': 'module.py', 'reason': 'nonregular archive member'}]
