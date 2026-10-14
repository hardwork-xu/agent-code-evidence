"""Small hostile-archive and replay fixtures / 小型恶意归档与回放夹具。

These are runner checks, not natural-repository research outcomes.
它们验证实验运行器，不是自然仓库研究结果。
"""
from copy import deepcopy
import io
import json
import tarfile

import pytest

from benchmarks.catalog_reuse import suite


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(suite.canonical(value) + b'\n')
    return suite.digest(path.read_bytes())


def make_archive(path, files, *, extra=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, 'w:gz') as archive:
        root = tarfile.TarInfo('fixture')
        root.type = tarfile.DIRTYPE
        archive.addfile(root)
        for name, raw in {'LICENSE': b'MIT fixture license\n', **files}.items():
            member = tarfile.TarInfo('fixture/' + name)
            member.size = len(raw)
            archive.addfile(member, io.BytesIO(raw))
        for member, raw in extra or []:
            archive.addfile(member, io.BytesIO(raw))


def snapshot(root, commit, files, *, extra=None):
    archive = root / f'archives/{commit}.tar.gz'
    make_archive(archive, files, extra=extra)
    records = [{'path': p, 'bytes': len(raw), 'sha256': suite.digest(raw)}
               for p, raw in sorted(files.items())]
    license_raw = b'MIT fixture license\n'
    metadata = {'schema_version': 2, 'repo': 'fixture/project', 'commit': commit,
                'source_prefix': 'pkg/', 'archive_path': archive.relative_to(root).as_posix(),
                'archive_bytes': archive.stat().st_size,
                'archive_sha256': suite.digest(archive.read_bytes()),
                'source_tree_sha256': suite.digest(json.dumps(
                    [[r['path'], r['bytes'], r['sha256']] for r in records],
                    ensure_ascii=False, separators=(',', ':')).encode()),
                'source_files': len(records), 'source_bytes': sum(r['bytes'] for r in records),
                'files': records, 'root_licenses': [{'path': 'LICENSE', 'bytes': len(license_raw),
                                                  'sha256': suite.digest(license_raw)}],
                'gates': {'fixture': True}}
    relative = f'inputs/{commit}/snapshot.json'
    metadata_hash = save(root / relative, metadata)
    record = {k: metadata[k] for k in ['commit', 'archive_path', 'archive_sha256',
                                      'source_tree_sha256', 'source_files', 'source_bytes']}
    record.update(metadata_path=relative, metadata_sha256=metadata_hash)
    return metadata, record


@pytest.fixture
def fixture_study(tmp_path, monkeypatch):
    root = tmp_path / 'inputs'
    before, after = 'a' * 40, 'b' * 40
    files = {'pkg/main.py': b'from .helper import value\ndef entry():\n    return value()\n',
             'pkg/helper.py': b'def value():\n    return 1\n'}
    _, first = snapshot(root, before, files)
    _, second = snapshot(root, after, {**files, 'pkg/unrelated.py': b'OTHER = 1\n'})
    identity = 'pkg/main.py:entry'
    anchors = {'repo': 'fixture/project', 'initial_commit': before,
               'anchors': [{'path': 'pkg/main.py', 'symbol': 'entry', 'identity': identity,
                            'selection_sha256': suite.digest(identity.encode())}]}
    anchors_path = 'inputs/anchors.json'
    anchors_hash = save(root / anchors_path, anchors)
    rule = {'repositories': ['fixture/project'], 'anchors_per_repo': 1,
            'primary_sampling': {'ancestor_offsets_oldest_to_newest': [8, 0]},
            'expected_secondary_event_pairs': {'fixture/project': 1}}
    rule_hash = save(root / 'inputs/input-rule.json', rule)
    manifest = {'schema_version': 1, 'status': 'input_assets_ready',
                'input_rule_path': 'inputs/input-rule.json', 'input_rule_sha256': rule_hash,
                'repositories': [{'repo': 'fixture/project', 'fixed_head': after,
                                  'source_prefix': 'pkg/', 'snapshots': [first, second],
                                  'primary_snapshots': [{'order': 0, 'ancestor_offset': 8, 'commit': before},
                                                        {'order': 1, 'ancestor_offset': 0, 'commit': after}],
                                  'all_secondary_event_pairs': [{'order': 0, 'parent': before, 'commit': after}],
                                  'anchors_path': anchors_path, 'anchors_sha256': anchors_hash}]}
    manifest_path = root / 'ready-manifest.json'
    pins = {'schema_version': 1, 'status': 'pinned_input_definitions',
            'input_rule_path': 'inputs/input-rule.json', 'input_rule_sha256': rule_hash,
            'repositories': deepcopy(manifest['repositories'])}
    pins['repositories'][0]['anchors'] = anchors
    for record in pins['repositories'][0]['snapshots']:
        record['metadata'] = json.loads((root / record['metadata_path']).read_bytes())
    pin_path = root / 'public-inputs.json'
    pin_hash = save(pin_path, pins)
    monkeypatch.setattr(suite, 'PIN_PATH', pin_path)
    manifest['sources_pin_sha256'] = pin_hash
    save(manifest_path, manifest)
    protocol = {'schema_version': 1, 'status': 'frozen', 'methods': list(suite.METHODS),
                'graph_policy': {'max_depth': 4, 'max_nodes': 64},
                'measurement': {'warmup': 1, 'repetitions': 1, 'memory_repetitions': 0},
                'input_rule_sha256': rule_hash,
                'sources_pin_sha256': pin_hash,
                'implementation_sha256': suite.implementation_fingerprint(),
                'sources': {'repositories': ['fixture/project'], 'snapshots_per_repository': 2,
                            'anchors_per_repository': 1, 'ancestor_offsets_oldest_to_newest': [8, 0],
                            'fixed_heads': {'fixture/project': after},
                            'source_prefixes': {'fixture/project': 'pkg/'}},
                'performance_target': {'minimum_reduction_fraction': .2,
                                       'minimum_repositories_meeting_target': 1},
                'resource_gate': {'absolute_peak_rss_bytes': 1024**3,
                                  'maximum_candidate_to_primary_baseline_peak_rss_ratio': 2}}
    protocol_path = tmp_path / 'protocol.json'
    save(protocol_path, protocol)
    return manifest_path, protocol_path, protocol, files


def test_exact_tar_loader_and_real_core_fixture(fixture_study, tmp_path):
    inputs, protocol_path, protocol, files = fixture_study
    manifest, repositories = suite.load_inputs(inputs, protocol)
    repository = repositories[0]
    first = repository.snapshots[repository.primary[0]]
    assert first.load() == {p: raw.decode() for p, raw in files.items()}
    output = tmp_path / 'results'
    result = suite.run_study(inputs, protocol_path, output)
    assert result['status'] == 'passed'
    assert len(result['rows']) == 24
    assert all(row['canonical_equal'] for row in result['rows'])
    assert all(row['actual_graph_sha256'] == row['expected_graph_sha256'] for row in result['rows'])
    fine = [r for r in result['rows'] if r['method'] == suite.METHODS[-1]
            and r['panel'] == 'primary' and r['phase'] == 'replay']
    root = [r for r in result['rows'] if r['method'] == suite.METHODS[-2]
            and r['panel'] == 'primary' and r['phase'] == 'replay']
    assert {r['reused'] for r in fine} == {1}
    assert {r['rebuilt'] for r in root} == {1}
    assert all(r['catalog_stats']['tracked_graphs'] == 1 for r in fine)
    assert all('per_graph' in r for r in result['rows'])
    assert all('source_commit' in r and 'protocol_sha256' in r for r in result['rows'])
    assert all(not r['measured'] and 'elapsed_ns' not in r
               for r in result['rows'] if r['panel'].startswith('secondary:'))
    assert json.loads((output / 'summary.json').read_bytes())['memory_target_met'] is False
    assert len((output / 'rows.jsonl').read_text().splitlines()) == len(result['rows'])
    # Inputs remain byte-for-byte frozen; no results or source paths enter them.
    assert json.loads(inputs.read_bytes()) == manifest
    raw_result = (output / 'run.json').read_text()
    assert str(tmp_path) not in raw_result


@pytest.mark.parametrize('kind', ['traversal', 'symlink', 'duplicate', 'extra', 'multiple_roots'])
def test_hostile_archive_rejected_without_extraction(tmp_path, kind):
    files = {'pkg/main.py': b'def entry():\n    return 1\n'}
    if kind == 'traversal':
        member = tarfile.TarInfo('fixture/../escape.py')
        raw = b'raise RuntimeError("not executed")\n'
    elif kind == 'symlink':
        member = tarfile.TarInfo('fixture/pkg/symlink.py')
        member.type = tarfile.SYMTYPE
        member.linkname = '../../private'
        raw = b''
    elif kind == 'duplicate':
        member = tarfile.TarInfo('fixture/pkg/main.py')
        raw = files['pkg/main.py']
    elif kind == 'extra':
        member = tarfile.TarInfo('fixture/pkg/extra.py')
        raw = b'VALUE = 9\n'
    else:
        member = tarfile.TarInfo('second_root/unrelated')
        raw = b''
    if member.isfile():
        member.size = len(raw)
    metadata, _ = snapshot(tmp_path, 'c' * 40, files, extra=[(member, raw)])
    with pytest.raises(ValueError):
        suite.Snapshot(tmp_path, metadata).load()
    assert not (tmp_path / 'escape.py').exists()
    assert not (tmp_path / 'pkg').exists()


def test_source_hash_and_missing_declared_source_are_not_silently_ignored(tmp_path):
    metadata, _ = snapshot(tmp_path, 'c' * 40, {'pkg/main.py': b'def entry():\n    return 1\n'})
    tampered = deepcopy(metadata)
    tampered['files'][0]['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='content checksum'):
        suite.Snapshot(tmp_path, tampered).load()
    tampered = deepcopy(metadata)
    tampered['files'].append({'path': 'pkg/missing.py', 'bytes': 0, 'sha256': suite.digest(b'')})
    with pytest.raises(ValueError, match='missing declared'):
        suite.Snapshot(tmp_path, tampered).load()


def test_pep263_source_decoding_and_blob_checks(tmp_path):
    raw = b'# coding: latin-1\nVALUE = "caf\xe9"\ndef entry():\n    return VALUE\n'
    metadata, _ = snapshot(tmp_path, 'c' * 40, {'pkg/main.py': raw})
    assert 'café' in suite.Snapshot(tmp_path, metadata).load()['pkg/main.py']
    metadata['files'][0]['git_blob_oid'] = '0' * 40
    with pytest.raises(ValueError, match='Git blob'):
        suite.Snapshot(tmp_path, metadata).load()


def test_checksum_source_archive_and_metadata_drift(fixture_study):
    inputs, _, protocol, _ = fixture_study
    manifest = json.loads(inputs.read_bytes())
    metadata_path = inputs.parent / manifest['repositories'][0]['snapshots'][0]['metadata_path']
    metadata_path.write_bytes(metadata_path.read_bytes() + b' ')
    with pytest.raises(ValueError, match='metadata checksum'):
        suite.load_inputs(inputs, protocol)


def test_no_overwrite_and_failed_oracle_run_retained(fixture_study, tmp_path, monkeypatch):
    inputs, protocol_path, _, _ = fixture_study
    output = tmp_path / 'keep'
    output.mkdir()
    sentinel = output / 'sentinel'
    sentinel.write_text('existing')
    with pytest.raises(FileExistsError):
        suite.run_study(inputs, protocol_path, output)
    assert sentinel.read_text() == 'existing'
    with pytest.raises(FileExistsError):
        suite.write_new(sentinel, {'replace': True})
    original = suite.fresh_graphs
    def wrong(*args):
        values = original(*args)
        return (values[0] + b' ', *values[1:])
    monkeypatch.setattr(suite, 'fresh_graphs', wrong)
    failed = tmp_path / 'failed'
    with pytest.raises(RuntimeError, match='canonical graph mismatch'):
        suite.run_study(inputs, protocol_path, failed)
    result = json.loads((failed / 'run.json').read_bytes())
    assert result['status'] == 'failed'
    assert result['rows'][0]['status'] == 'failed'
    assert result['rows'][0]['mismatch_anchor_indices'] == [0]
    assert not (failed / 'summary.json').exists()
    with pytest.raises(ValueError, match='failed'):
        suite.summarize(result)


def test_protocol_draft_and_count_drift_fail_before_measurement(fixture_study, tmp_path):
    inputs, protocol_path, protocol, _ = fixture_study
    draft = deepcopy(protocol)
    draft['status'] = 'draft_before_measurement'
    with pytest.raises(ValueError, match='freeze'):
        suite.validate_protocol(draft)
    with pytest.raises(ValueError, match='CLI counts'):
        suite.run_study(inputs, protocol_path, tmp_path / 'count-drift', repetitions=2)
    result = json.loads((tmp_path / 'count-drift/run.json').read_bytes())
    assert result['rows'] == [] and result['status'] == 'failed'


def test_rotation_and_rss_units():
    orders = [suite.method_order(0, repetition) for repetition in range(4)]
    assert {order[0] for order in orders} == set(suite.METHODS)
    assert all(set(order) == set(suite.METHODS) for order in orders)
    assert suite.method_order(1, -1) == suite.METHODS
    assert suite.peak_rss_bytes(123, 'Darwin') == 123
    assert suite.peak_rss_bytes(123, 'Linux') == 125952
    with pytest.raises(ValueError, match='macOS and Linux'):
        suite.peak_rss_bytes(123, 'Windows')


def test_fresh_rss_worker_fixture_not_concurrent_with_timing(fixture_study):
    inputs, protocol_path, _, _ = fixture_study
    row = suite.rss_worker(inputs, protocol_path, 'fixture/project', suite.METHODS[-1])
    assert row['status'] == 'passed' and row['snapshots'] == 2
    assert row['peak_rss_bytes'] > 0
    assert len(row['graph_digests']) == 2


def test_summary_requires_complete_grid_and_preserves_negative_results(fixture_study, tmp_path):
    inputs, protocol_path, _, _ = fixture_study
    result = suite.run_study(inputs, protocol_path, tmp_path / 'summary-fixture')
    changed = deepcopy(result)
    changed['rows'].pop()
    with pytest.raises(ValueError, match='missing or duplicate'):
        suite.summarize(changed)
    changed = deepcopy(result)
    for row in changed['rows']:
        if row['panel'] == 'primary' and row['method'] == suite.METHODS[-1]:
            row['elapsed_ns'] *= 1000
            row['load_ns'] *= 1000
            row['initialize_ns'] *= 1000
            row['graph_ns'] *= 1000
    report = suite.summarize(changed)
    assert report['replay_target_met'] is False
    assert report['repositories_meeting_replay_target'] == 0
    assert report['groups']['fixture/project']['primary_replay_reduction_D_vs_C'] < 0
    assert report['memory_target_met'] is False


@pytest.mark.parametrize('tamper', ['remove_repository', 'empty_all', 'snapshot', 'phase',
                                  'measured', 'source_tree', 'archive', 'empty_digests',
                                  'negative_counts', 'drop_status_counts'])
def test_self_asserted_grid_and_row_tampering_are_rejected(fixture_study, tmp_path, tamper):
    inputs, protocol_path, _, _ = fixture_study
    result = suite.run_study(inputs, protocol_path, tmp_path / 'tamper-fixture')
    if tamper in {'remove_repository', 'empty_all'}:
        result['sources'] = []
        result['rows'] = []
        result['memory_rows'] = []
    elif tamper == 'snapshot':
        result['rows'][0]['snapshot_id'] = 'd' * 40
    elif tamper == 'phase':
        result['rows'][0]['phase'] = 'replay'
    elif tamper == 'measured':
        result['rows'][0]['measured'] = False
    elif tamper == 'source_tree':
        result['rows'][0]['source_tree_sha256'] = '0' * 64
    elif tamper == 'archive':
        result['rows'][0]['archive_sha256'] = '0' * 64
    elif tamper == 'empty_digests':
        result['rows'][0]['actual_graph_sha256'] = []
        result['rows'][0]['expected_graph_sha256'] = []
    elif tamper == 'negative_counts':
        result['rows'][0]['reused'] = -1
    else:
        result['rows'][0]['per_graph'] = []
    with pytest.raises(ValueError):
        suite.validate_results(result)


def test_rehashed_mutable_metadata_cannot_change_authoritative_source(fixture_study):
    inputs, _, protocol, _ = fixture_study
    manifest = json.loads(inputs.read_bytes())
    reference = manifest['repositories'][0]['snapshots'][0]
    path = inputs.parent / reference['metadata_path']
    metadata = json.loads(path.read_bytes())
    metadata['files'][0]['sha256'] = '0' * 64
    reference['metadata_sha256'] = save(path, metadata)
    save(inputs, manifest)
    with pytest.raises(ValueError, match='source pins'):
        suite.load_inputs(inputs, protocol)


def test_frozen_label_requires_public_source_and_code_bindings(fixture_study):
    _, _, protocol, _ = fixture_study
    changed = deepcopy(protocol)
    changed.pop('sources_pin_sha256')
    with pytest.raises(ValueError, match='source-pin SHA256'):
        suite.validate_protocol(changed)
    changed = deepcopy(protocol)
    changed['implementation_sha256'] = {}
    with pytest.raises(ValueError, match='implementation differs'):
        suite.validate_protocol(changed)


def test_selected_anchor_capture_includes_decorators(tmp_path):
    files = {'pkg/main.py': b'@decorator\ndef entry():\n    return 1\n'}
    metadata, _ = snapshot(tmp_path, 'c' * 40, files)
    identity = 'pkg/main.py:entry'
    repo = suite.Repository('fixture/project', 'c' * 40, {}, (), (),
                            ({'path': 'pkg/main.py', 'symbol': 'entry',
                              'selection_sha256': suite.digest(identity.encode())},))
    anchor = repo.anchors(suite.Snapshot(tmp_path, metadata).load())[0]
    assert anchor['start_line'] == 1 and anchor['text'].startswith('@decorator\n')


def test_loader_rejects_symlink_asset_before_read(tmp_path):
    real = tmp_path / 'source'
    real.write_text('private')
    (tmp_path / 'linked').symlink_to(real)
    with pytest.raises(ValueError, match='symlink'):
        suite.local_asset(tmp_path, 'linked')
    with pytest.raises(ValueError, match='unsafe'):
        suite.local_asset(tmp_path, '../source')


def test_cli_bilingual_help_and_worker_json(fixture_study, capsys):
    from scripts.run_catalog_study import main
    with pytest.raises(SystemExit) as stop:
        main(['--help'])
    assert stop.value.code == 0 and '已准备源码清单' in capsys.readouterr().out
    inputs, protocol_path, _, _ = fixture_study
    assert main(['--rss-worker', '--inputs', str(inputs), '--protocol', str(protocol_path),
                 '--repository', 'fixture/project', '--method', suite.METHODS[-1]]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'passed'
