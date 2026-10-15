"""Independent study-integrity review; fake clocks/sessions never measure performance.

独立核查结果完整性、异常保留和清单漂移；模拟仅用于流程测试，不作为性能证据。
"""
from argparse import Namespace
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest

from scripts import run_selective_reuse as runner


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def complete_result():
    rows = []
    group = 'synthetic:10:unrelated_file_change'
    for rep in (1, 2):
        for method in runner.METHODS:
            for version in (0, 1):
                rows.append({'group': group, 'repetition': rep, 'method': method,
                             'version_index': version, 'phase': 'capture' if version == 0 else 'replay',
                             'snapshot_id': 'before' if version == 0 else 'after',
                             'elapsed_ns': 100, 'load_ns': 25, 'graph_ns': 75,
                             'source_changed': version == 1,
                             'changed_paths': ['other.py'] if version else [],
                             'catalog_changed': False, 'reused': 0, 'rebuilt': 1,
                             'reasons': {'initial_capture' if version == 0 else 'baseline_rebuild': 1},
                             'graphs': [sha('graph-' + str(version))], 'complete': 1,
                             'equivalence': True, 'status': 'passed'})
    return {'status': 'passed', 'rows': rows, 'repetitions': 2, 'expected_groups': [group]}


def test_complete_authored_grid_is_accepted():
    result = complete_result()
    assert runner.validate_measurements(result) == 0
    summary = runner.summarize(result)
    assert summary['canonical_mismatches'] == 0
    assert not summary['utility_target_met']


@pytest.mark.parametrize('change', ['missing-row', 'duplicate', 'missing-group', 'graph-mismatch',
                                    'failed-row', 'false-equivalence', 'wrong-method'])
def test_incomplete_or_disagreeing_grid_is_rejected(change):
    result = complete_result()
    if change == 'missing-row':
        result['rows'].pop()
    elif change == 'duplicate':
        result['rows'].append(deepcopy(result['rows'][0]))
    elif change == 'missing-group':
        result['expected_groups'].append('synthetic:100:unrelated_file_change')
    elif change == 'graph-mismatch':
        result['rows'][0]['graphs'] = [sha('bad')]
    elif change == 'failed-row':
        result['rows'][0]['status'] = 'failed'
    elif change == 'false-equivalence':
        result['rows'][0]['equivalence'] = False
    else:
        result['rows'][0]['method'] = 'unlisted-method'
    with pytest.raises(ValueError):
        runner.summarize(result)


@pytest.mark.parametrize('status', ['failed', 'running', 'interrupted'])
def test_unfinished_or_failed_study_cannot_have_a_success_summary(status):
    result = complete_result()
    result['status'] = status
    with pytest.raises(ValueError):
        runner.summarize(result)


@pytest.mark.parametrize('field,value', [
    ('phase', 'replay'), ('snapshot_id', 'different-corpus'),
    ('source_changed', True), ('changed_paths', ['unexpected.py']),
    ('catalog_changed', True), ('elapsed_ns', -1), ('graphs', []),
])
def test_row_metadata_cannot_disagree_with_its_matched_observations(field, value):
    result = complete_result()
    result['rows'][0][field] = value
    with pytest.raises(ValueError):
        runner.summarize(result)


def test_same_fixed_input_cannot_change_graphs_between_repetitions():
    result = complete_result()
    for row in result['rows']:
        if row['repetition'] == 2 and row['version_index'] == 1:
            row['graphs'] = [sha('changed between repeated readings of same input')]
    with pytest.raises(ValueError):
        runner.summarize(result)


@pytest.fixture
def study(tmp_path, monkeypatch):
    data = tmp_path / 'data'
    data.mkdir()
    protocol = {'natural': {'repositories': ['Textualize/rich'], 'versions': 6},
                'synthetic': {'module_counts': [10], 'workloads': ['unrelated_file_change']},
                'timing': {'repetitions': 1}, 'supersedes_protocol_sha256': []}
    protocol_bytes = (json.dumps(protocol, sort_keys=True) + '\n').encode()
    (data / 'protocol.json').write_bytes(protocol_bytes)
    monkeypatch.setattr(runner, 'DATA', data)
    monkeypatch.setattr(runner, 'environment', lambda: {'test_fixture': True})
    args = Namespace(suite='synthetic', cache_dir=tmp_path / 'cache', output=tmp_path / 'run.json')
    return data, protocol, protocol_bytes, args


def frozen_manifest(protocol_bytes):
    source = 'def entry():\n    return 1\n'
    anchor = {'id': sha('rich/sample.py:entry'), 'path': 'rich/sample.py', 'symbol': 'entry',
              'kind': 'function', 'start_line': 1, 'end_line': 2,
              'text_sha256': sha(source), 'file_sha256': sha(source)}
    versions = [{'commit': format(i, '040x'), 'parents': [format(i - 1, '040x')],
                 'archive_sha256': sha('archive-' + str(i)),
                 'archive_url': 'https://codeload.github.com/Textualize/rich/tar.gz/' + format(i, '040x'),
                 'files': {'rich/sample.py': sha(source)},
                 'licenses': [{'path': 'LICENSE', 'sha256': sha('license'), 'local': 'LICENSE'}]}
                for i in range(1, 7)]
    return {'schema_version': 1, 'protocol_sha256': hashlib.sha256(protocol_bytes).hexdigest(),
            'pinned_at_utc': '2026-10-04T00:00:00+00:00',
            'sources_frozen_at_utc': '2026-10-04T00:01:00+00:00',
            'repositories': [{'repository': 'Textualize/rich', 'tag': 'test-fixture',
                              'selection_kind': 'github-latest-release', 'prefixes': ['rich/'],
                              'versions': versions, 'anchors': [anchor]}]}


def test_frozen_manifest_and_acknowledged_protocol_lineage_are_accepted(study):
    _, protocol, raw, _ = study
    manifest = frozen_manifest(raw)
    runner.validate_manifest(manifest, protocol)
    previous = sha('documented earlier protocol')
    protocol['supersedes_protocol_sha256'] = [previous]
    manifest['protocol_sha256'] = previous
    runner.validate_manifest(manifest, protocol)


@pytest.mark.parametrize('change', ['protocol', 'unfrozen', 'repository', 'versions', 'parent',
                                    'license', 'source-map', 'archive-hash', 'source-text'])
def test_documented_manifest_guards_reject_drift(study, change):
    _, protocol, raw, _ = study
    manifest = frozen_manifest(raw)
    repo = manifest['repositories'][0]
    if change == 'protocol':
        manifest['protocol_sha256'] = sha('unacknowledged protocol')
    elif change == 'unfrozen':
        manifest.pop('sources_frozen_at_utc')
    elif change == 'repository':
        repo['repository'] = 'unselected/repository'
    elif change == 'versions':
        repo['versions'].pop()
    elif change == 'parent':
        repo['versions'][1]['parents'] = ['0' * 40]
    elif change == 'license':
        repo['versions'][0]['licenses'] = []
    elif change == 'source-map':
        repo['versions'][0]['files'] = {}
    elif change == 'archive-hash':
        repo['versions'][0]['archive_sha256'] = 'short'
    else:
        repo['anchors'][0]['text'] = 'source should not be in metadata'
    with pytest.raises(ValueError):
        runner.validate_manifest(manifest, protocol)


@pytest.mark.parametrize('change', ['empty-anchor', 'duplicate-anchor', 'missing-anchor-path',
                                    'anchor-file-hash', 'prefix', 'duplicate-revisions'])
def test_selection_metadata_is_validated_before_measurement(study, change):
    _, protocol, raw, _ = study
    manifest = frozen_manifest(raw)
    repo = manifest['repositories'][0]
    if change == 'empty-anchor':
        repo['anchors'] = [{}]
    elif change == 'duplicate-anchor':
        repo['anchors'].append(deepcopy(repo['anchors'][0]))
    elif change == 'missing-anchor-path':
        repo['anchors'][0]['path'] = 'rich/missing.py'
    elif change == 'anchor-file-hash':
        repo['anchors'][0]['file_sha256'] = sha('different source file')
    elif change == 'prefix':
        repo['prefixes'] = ['tests/']
    else:
        # A cyclic repeated commit can satisfy adjacent equality unless uniqueness is checked.
        for version in repo['versions']:
            version['commit'] = '1' * 40
            version['parents'] = ['1' * 40]
    with pytest.raises(ValueError):
        runner.validate_manifest(manifest, protocol)


def install_fake_execution(monkeypatch, fail_at=None, error=RuntimeError):
    """Use fake API outputs and an integer clock; no actual performance inference."""
    calls = []
    ticks = iter(range(1, 10000))
    monkeypatch.setattr(runner.time, 'perf_counter_ns', lambda: next(ticks))

    class FakeSession:
        def __init__(self, anchors, mode):
            self.mode = mode
            self.count = len(anchors)

        def update(self, texts, snapshot_id):
            calls.append((self.mode, snapshot_id))
            if len(calls) == fail_at:
                raise error('private local path must not be copied to public result')
            return SimpleNamespace(graphs=[{'frontier': [], 'snapshot_id': snapshot_id,
                                            'source_hash': sha(json.dumps(texts, sort_keys=True))}
                                           for _ in range(self.count)],
                                   reused=0, rebuilt=self.count, reasons={'test_fixture': self.count})

    monkeypatch.setattr(runner, 'GraphSession', FakeSession)
    return calls


def test_existing_output_is_never_overwritten(study, monkeypatch):
    _, _, _, args = study
    original = b'previous immutable run\n'
    args.output.write_bytes(original)
    calls = install_fake_execution(monkeypatch)
    with pytest.raises(FileExistsError):
        runner.run(args)
    assert args.output.read_bytes() == original
    assert calls == []


def test_failure_retains_completed_rows_and_precise_progress(study, monkeypatch):
    _, _, _, args = study
    install_fake_execution(monkeypatch, fail_at=10)
    with pytest.raises(RuntimeError):
        runner.run(args)
    result = json.loads(args.output.read_text())
    assert result['status'] == 'failed'
    assert result['error_type'] == 'RuntimeError'
    assert len(result['rows']) == 3
    assert result['progress'] == {'group': 'synthetic:10:unrelated_file_change',
                                  'method': 'read_set_certificate', 'repetition': 1,
                                  'version_index': 1, 'snapshot_id': 'after'}
    assert 'private local path' not in args.output.read_text()
    assert 'summary' not in result
    assert result.get('finished_at_utc')


def test_keyboard_interrupt_is_retained_as_an_interruption(study, monkeypatch):
    _, _, _, args = study
    install_fake_execution(monkeypatch, fail_at=10, error=KeyboardInterrupt)
    with pytest.raises(KeyboardInterrupt):
        runner.run(args)
    result = json.loads(args.output.read_text())
    assert len(result['rows']) == 3
    assert result['status'] in {'failed', 'interrupted'}
    assert result['error_type'] == 'KeyboardInterrupt'
    assert result['progress']['version_index'] == 1
    assert result.get('finished_at_utc')


def test_checkpoint_persists_each_completed_observation(study, monkeypatch):
    _, _, _, args = study
    install_fake_execution(monkeypatch)
    original = runner.write
    lengths = []

    def observe(path, value):
        original(path, value)
        if path == args.output:
            persisted = json.loads(path.read_text())
            lengths.append(len(persisted['rows']))

    monkeypatch.setattr(runner, 'write', observe)
    runner.run(args)
    result = json.loads(args.output.read_text())
    assert result['status'] == 'passed'
    assert len(result['rows']) == 6
    assert set(range(1, 7)).issubset(lengths)
    assert all(a <= b for a, b in zip(lengths, lengths[1:]))
    assert all(r['elapsed_ns'] == 2 and r['load_ns'] == 1 and r['graph_ns'] == 1
               for r in result['rows'])
    assert all(r['source_changed'] == (r['version_index'] == 1) for r in result['rows'])
    assert result['finished_at_utc']
