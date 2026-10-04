"""Replay sampling and adversarial controls / 回放采样与不利场景。"""
from scripts.run_selective_reuse import anchors_for, synthetic_loaders, replay_group, summarize


def test_sampling_is_deterministic_and_ignores_classes():
    texts = {'b.py': 'def second():\n    return 2\n',
             'a.py': 'class C:\n    def method(self):\n        return 1\n\ndef first():\n    return 1\n'}
    anchors = anchors_for(texts)
    assert anchors == anchors_for(dict(reversed(list(texts.items()))))
    assert {a['symbol'] for a in anchors} == {'first', 'second'}


def test_all_controls_and_result_schema():
    rows = []
    for workload, expected in [('unrelated_file_change', 4), ('referenced_file_change', 0),
                               ('path_catalog_addition', 0)]:
        loaders, ids, anchors = synthetic_loaders(10, workload)
        current = replay_group(workload, loaders, ids, anchors, repetitions=1)
        assert len(current) == 6
        replay = [r for r in current if r['phase'] == 'replay']
        assert all(r['equivalence'] and r['status'] == 'passed' for r in replay)
        assert next(r for r in replay if r['method'] == 'read_set_certificate')['reused'] == expected
        assert len({tuple(r['graphs']) for r in replay}) == 1
        assert all(r['elapsed_ns'] >= r['graph_ns'] > 0 for r in replay)
        rows += current
    result = summarize({'rows': rows})
    assert len(result['groups']) == 3
    assert not result['utility_target_met']


def test_mismatch_preserves_preceding_rows(monkeypatch):
    import scripts.run_selective_reuse as runner
    original = runner.GraphSession.update

    def corrupt(self, texts, snapshot_id):
        result = original(self, texts, snapshot_id)
        if self._mode == 'read_set_certificate' and snapshot_id == 'after':
            result.graphs[0]['id'] = 'intentionally-corrupt-test-only'
        return result

    monkeypatch.setattr(runner.GraphSession, 'update', corrupt)
    loaders, ids, anchors = synthetic_loaders(10, 'unrelated_file_change')
    rows, checkpoints = [], []
    import pytest
    with pytest.raises(RuntimeError, match='canonical graph mismatch'):
        replay_group('failure-injection', loaders, ids, anchors, 1, rows=rows,
                     checkpoint=lambda: checkpoints.append(len(rows)))
    assert rows[-1]['status'] == 'failed'
    assert rows[-1]['error'] == 'canonical_graph_mismatch'
    assert checkpoints[-1] == len(rows)


def test_failed_rows_cannot_be_summarized_as_success():
    import pytest
    with pytest.raises(ValueError, match='failed measurement'):
        summarize({'rows': [{'status': 'failed'}]})
