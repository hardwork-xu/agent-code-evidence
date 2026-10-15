"""Pinned metadata and downloader tests use tiny archives and fake transports only."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

import pytest

from scripts.prepare_catalog_sources import (
    INPUTS, digest, json_bytes, main, outside_git, prepare, validate_inputs,
)


def archive(entries):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as stream:
        root = tarfile.TarInfo('fixture-root/')
        root.type = tarfile.DIRTYPE
        stream.addfile(root)
        for path, raw, kind in entries:
            info = tarfile.TarInfo(path if path.startswith('/') else 'fixture-root/' + path)
            info.type = kind
            info.size = len(raw) if kind == tarfile.REGTYPE else 0
            if kind in {tarfile.SYMTYPE, tarfile.LNKTYPE}:
                info.linkname = '../../outside'
            stream.addfile(info, io.BytesIO(raw) if kind == tarfile.REGTYPE else None)
    return buffer.getvalue()


def fixture_inputs():
    before, after = 'a' * 40, 'b' * 40
    name = 'fixture/tiny'
    anchor = b'raise RuntimeError("upstream code must never execute")\ndef anchor():\n    return 1\n'
    license_text = b'Fixture license bytes retained exactly.\n'
    files_by_commit = {before: {'pkg/anchor.py': anchor},
                       after: {'pkg/anchor.py': anchor, 'pkg/new.py': b'new = 2\n'}}
    archives = {}
    entries = {}
    refs = []
    for commit, source_files in files_by_commit.items():
        folder = f'inputs/fixture--tiny/{commit}'
        members = [(path, raw, tarfile.REGTYPE) for path, raw in source_files.items()]
        members += [('LICENSE', license_text, tarfile.REGTYPE),
                    ('pkg/tests/ignored.py', b'raise RuntimeError("ignored tests")\n', tarfile.REGTYPE),
                    ('setup.py', b'raise RuntimeError("no install hooks")\n', tarfile.REGTYPE)]
        entries[commit] = members
        archives[commit] = archive(members)

        def asset(path, raw, local):
            return {'path': path, 'local_path': local, 'bytes': len(raw), 'sha256': digest(raw),
                    'git_blob_oid': hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()}

        files = [asset(path, raw, folder + '/source/' + path)
                 for path, raw in sorted(source_files.items())]
        canonical = [[f['path'], f['bytes'], f['sha256']] for f in files]
        tree_sha = digest(json.dumps(canonical, separators=(',', ':'), ensure_ascii=False).encode())
        metadata = {'schema_version': 2, 'repo': name, 'commit': commit, 'source_prefix': 'pkg/',
                    'archive_path': f'archives/fixture--tiny--{commit}.tar.gz',
                    'archive_url': f'https://codeload.github.com/{name}/tar.gz/{commit}',
                    'archive_sha256': digest(archives[commit]), 'archive_bytes': len(archives[commit]),
                    'source_directory': folder + '/source', 'source_files': len(files),
                    'source_bytes': sum(f['bytes'] for f in files), 'source_tree_sha256': tree_sha,
                    'files': files,
                    'root_licenses': [asset('LICENSE', license_text, folder + '/root-licenses/LICENSE')]}
        refs.append({'commit': commit, 'roles': [], 'metadata_path': folder + '/snapshot.json',
                     'metadata_sha256': digest(json_bytes(metadata)), 'metadata': metadata,
                     **{key: metadata[key] for key in ['archive_path', 'archive_sha256',
                         'source_tree_sha256', 'source_files', 'source_bytes']}})
    anchor_record = {'path': 'pkg/anchor.py', 'symbol': 'anchor', 'identity': 'pkg/anchor.py:anchor',
                     'selection_sha256': digest(b'pkg/anchor.py:anchor'),
                     'initial_definitions': [{'symbol': 'anchor', 'line': 2, 'end_line': 3}]}
    anchors = {'initial_commit': before, 'anchors': [anchor_record]}
    rule = {'status': 'fixture_only', 'no_upstream_execution': True}
    data = {'schema_version': 1, 'status': 'pinned_input_definitions',
            'selection': {'primary_ancestor_offsets': [1, 0], 'fixed_anchors_per_repository': 1},
            'input_rule': rule, 'input_rule_path': 'inputs/input-rule.json',
            'input_rule_sha256': digest(json_bytes(rule)),
            'counts': {'repositories': 1, 'primary_snapshots': 2, 'primary_source_batches': 1,
                       'secondary_event_pairs': 1, 'unique_snapshots': 2},
            'repositories': [{'repo': name, 'fixed_head': after, 'source_prefix': 'pkg/',
                              'first_parent_chain': [after, before],
                              'primary_snapshots': [{'order': 0, 'ancestor_offset': 1, 'commit': before},
                                                    {'order': 1, 'ancestor_offset': 0, 'commit': after}],
                              'all_secondary_event_pairs': [{'order': 0, 'parent': before, 'commit': after,
                                'first_parent_distance': 0,
                                'catalog_changes': [{'status': 'A', 'path': 'pkg/new.py'}]}],
                              'unique_snapshot_count': 2, 'anchors': anchors,
                              'anchors_path': 'inputs/fixture--tiny/anchors.json',
                              'anchors_sha256': digest(json_bytes(anchors)), 'snapshots': refs}]}
    return data, archives, entries


def transport_for(archives, calls):
    def fake(record, destination, _timeout):
        calls.append(record['name'])
        commit = record['name'].removesuffix('.tar.gz').split('--')[-1]
        destination.write_bytes(archives[commit])
    return fake


def replace_archive(data, archives, entries):
    ref = data['repositories'][0]['snapshots'][0]
    raw = archive(entries)
    archives[ref['commit']] = raw
    ref['metadata']['archive_sha256'] = ref['archive_sha256'] = digest(raw)
    ref['metadata']['archive_bytes'] = len(raw)
    ref['metadata_sha256'] = digest(json_bytes(ref['metadata']))


def test_public_metadata_is_complete_pinned_and_has_no_machine_paths():
    raw = INPUTS.read_bytes()
    data = json.loads(raw)
    validate_inputs(data)
    assert data['counts'] == {'repositories': 4, 'primary_snapshots': 68,
                             'primary_source_batches': 64, 'secondary_event_pairs': 23,
                             'unique_snapshots': 107, 'primary_chain_transitions': 512,
                             'included_path_add_delete_entries': 46}
    assert [r['secondary_event_pair_count'] for r in data['repositories']] == [7, 6, 4, 6]
    assert all(len(r['anchors']['anchors']) == 24 for r in data['repositories'])
    for private_marker in [b'/Users/', b'/home/', b'metadata_git_dir', b'127.0.0.1']:
        assert private_marker not in raw


def test_fixture_preparation_filters_and_preserves_exact_bytes_without_execution(tmp_path):
    data, archives, _ = fixture_inputs()
    calls = []
    output = tmp_path / 'output'
    result = prepare(data, output, transport=transport_for(archives, calls))
    assert len(calls) == 2
    assert result['status'] == 'input_assets_ready'
    assert result['sources_pin_sha256'] == digest(json_bytes(data))
    assert json.loads((output / 'ready-manifest.json').read_text()) == result
    for ref in result['repositories'][0]['snapshots']:
        assert 'metadata' not in ref
        metadata_raw = (output / ref['metadata_path']).read_bytes()
        assert digest(metadata_raw) == ref['metadata_sha256']
        metadata = json.loads(metadata_raw)
        source = output / metadata['source_directory']
        assert not (source / 'setup.py').exists()
        assert not (source / 'pkg/tests/ignored.py').exists()
        for asset in metadata['files'] + metadata['root_licenses']:
            assert digest((output / asset['local_path']).read_bytes()) == asset['sha256']
    def forbidden(*_):
        raise AssertionError('verified cache must not trigger a transport')
    repeated = prepare(data, output, transport=forbidden)
    assert repeated['archive_acquisition'] == {'downloaded': 0, 'cache_reused': 2}
    assert result['archive_acquisition'] == {'downloaded': 2, 'cache_reused': 0}
    assert {key: value for key, value in repeated.items() if key != 'archive_acquisition'} == {
        key: value for key, value in result.items() if key != 'archive_acquisition'}


def test_external_archive_cache_reuses_normal_files_without_network(tmp_path):
    data, archives, _ = fixture_inputs()
    cache = tmp_path / 'cache'
    cache.mkdir()
    for ref in data['repositories'][0]['snapshots']:
        (cache / Path(ref['archive_path']).name).write_bytes(archives[ref['commit']])
    def forbidden(*_):
        raise AssertionError('network must not be called')
    result = prepare(data, tmp_path / 'output', cache=cache, transport=forbidden)
    assert result['status'] == 'input_assets_ready'
    assert all((cache / Path(ref['archive_path']).name).is_file()
               for ref in result['repositories'][0]['snapshots'])


def test_corrupt_download_cleans_partial_and_invalidates_ready(tmp_path):
    data, _, _ = fixture_inputs()
    def corrupt(record, path, _timeout):
        path.write_bytes(b'x' * record['bytes'])
    with pytest.raises(ValueError, match='SHA-256'):
        prepare(data, tmp_path, transport=corrupt)
    assert json.loads((tmp_path / 'ready-manifest.json').read_text())['status'] == 'input_preparation_failed'
    assert not list(tmp_path.rglob('*.part'))
    assert not list((tmp_path / 'archives').glob('*.tar.gz'))


def test_mismatched_cache_and_source_are_not_overwritten(tmp_path):
    data, archives, _ = fixture_inputs()
    prepare(data, tmp_path, transport=transport_for(archives, []))
    ref = data['repositories'][0]['snapshots'][0]
    asset = ref['metadata']['files'][0]
    source = tmp_path / asset['local_path']
    source.write_bytes(b'user modification')
    with pytest.raises(ValueError, match='existing output'):
        prepare(data, tmp_path, transport=transport_for(archives, []))
    assert source.read_bytes() == b'user modification'
    assert json.loads((tmp_path / 'ready-manifest.json').read_text())['status'] == 'input_preparation_failed'


@pytest.mark.parametrize('attack', ['traversal', 'absolute', 'duplicate', 'symlink', 'hardlink',
                                   'extra_source', 'missing_license', 'changed_source'])
def test_archive_counterexamples_never_publish_ready(tmp_path, attack):
    data, archives, members = fixture_inputs()
    commit = data['repositories'][0]['snapshots'][0]['commit']
    entries = list(members[commit])
    if attack == 'traversal':
        entries.append(('../escaped.py', b'x = 1\n', tarfile.REGTYPE))
    elif attack == 'absolute':
        entries.append(('/absolute.py', b'x = 1\n', tarfile.REGTYPE))
    elif attack == 'duplicate':
        entries.append(entries[0])
    elif attack in {'symlink', 'hardlink'}:
        entries[0] = (entries[0][0], b'', tarfile.SYMTYPE if attack == 'symlink' else tarfile.LNKTYPE)
    elif attack == 'extra_source':
        entries.append(('pkg/undeclared.py', b'x = 1\n', tarfile.REGTYPE))
    elif attack == 'missing_license':
        entries = [entry for entry in entries if entry[0] != 'LICENSE']
    else:
        entries[0] = (entries[0][0], b'x' * len(entries[0][1]), tarfile.REGTYPE)
    replace_archive(data, archives, entries)
    with pytest.raises(ValueError):
        prepare(data, tmp_path / 'output', transport=transport_for(archives, []))
    assert json.loads((tmp_path / 'output/ready-manifest.json').read_text())['status'] == 'input_preparation_failed'
    assert not (tmp_path / 'escaped.py').exists()
    assert not list(tmp_path.rglob('*.part'))


def test_output_and_cache_inside_git_or_bare_repositories_are_rejected(tmp_path):
    ordinary = tmp_path / 'ordinary'
    ordinary.mkdir()
    (ordinary / '.git').write_text('gitdir: elsewhere\n')
    with pytest.raises(ValueError, match='Git tree'):
        outside_git(ordinary / 'new/output')
    bare = tmp_path / 'bare'
    subprocess.run(['git', 'init', '--quiet', '--bare', str(bare)], check=True)
    with pytest.raises(ValueError, match='Git tree'):
        outside_git(bare / 'new/output')


def test_nested_git_and_symlink_source_paths_are_rejected(tmp_path):
    data, archives, _ = fixture_inputs()
    folder = tmp_path / Path(data['repositories'][0]['snapshots'][0]['metadata']['source_directory'])
    folder.mkdir(parents=True)
    (folder / '.git').mkdir()
    with pytest.raises(ValueError, match='Git tree'):
        prepare(data, tmp_path, transport=transport_for(archives, []))
    (folder / '.git').rmdir()
    destination = tmp_path / 'untouched'
    destination.mkdir()
    (folder / 'pkg').symlink_to(destination, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        prepare(data, tmp_path, transport=transport_for(archives, []))
    assert list(destination.iterdir()) == []


def test_metadata_tampering_fails_before_any_download_and_replaces_stale_ready(tmp_path):
    data, archives, _ = fixture_inputs()
    prepare(data, tmp_path, transport=transport_for(archives, []))
    bad = deepcopy(data)
    bad['repositories'][0]['snapshots'][0]['metadata']['files'][0]['local_path'] = '../private'
    bad['repositories'][0]['snapshots'][0]['metadata_sha256'] = digest(
        json_bytes(bad['repositories'][0]['snapshots'][0]['metadata']))
    def forbidden(*_):
        raise AssertionError('invalid metadata must be rejected before transport')
    with pytest.raises(ValueError, match='relative path'):
        prepare(bad, tmp_path, transport=forbidden)
    assert json.loads((tmp_path / 'ready-manifest.json').read_text())['status'] == 'input_preparation_failed'


def test_cli_requires_explicit_output_and_binds_original_input_file_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr('sys.argv', ['prepare_catalog_sources'])
    with pytest.raises(SystemExit) as stopped:
        main()
    assert stopped.value.code == 2
    data, _, _ = fixture_inputs()
    raw = json.dumps(data, separators=(',', ':')).encode()
    pin = tmp_path / 'inputs.json'
    pin.write_bytes(raw)
    calls = []
    def fake_prepare(_data, _output, **kwargs):
        calls.append(kwargs)
        return {'total_unique_snapshots': 2}
    monkeypatch.setattr('scripts.prepare_catalog_sources.prepare', fake_prepare)
    monkeypatch.setattr('sys.argv', ['prepare_catalog_sources', '--output', str(tmp_path / 'output'),
                                   '--archive-cache', str(tmp_path / 'cache'), '--inputs', str(pin)])
    assert main() == 0
    assert calls[0]['sources_pin_sha256'] == digest(raw)
    assert calls[0]['cache'] == tmp_path / 'cache'
