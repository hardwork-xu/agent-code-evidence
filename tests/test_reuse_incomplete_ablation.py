"""Post-primary exploratory completeness-gate ablation; not a preregistered study.

Added after the primary study found zero complete natural graphs. Cache hits
preserve unknown/missing/truncated states, not program semantics or freshness.
主实验零完整图覆盖后添加的探索性消融；缓存命中不得提升未知/缺失/截断状态。
"""
import ast
import hashlib

import pytest

from benchmarks.selective_reuse.oracle_cases import anchor as oracle_anchor, cases
from contextproof.graph import build_graph, canonical_graph_bytes, compare_graphs, validate_graph
from contextproof.reuse import GraphSession


MODE = 'read_set_any_status'
CASES = cases()


def selected(source, path='app.py'):
    node = next(item for item in ast.parse(source).body
                if isinstance(item, ast.FunctionDef) and item.name == 'entry')
    text = ''.join(source.splitlines(keepends=True)[node.lineno - 1:node.end_lineno])
    return {'id': 'independent-' + path, 'path': path, 'symbol': 'entry', 'kind': 'function',
            'start_line': node.lineno, 'end_line': node.end_lineno, 'text': text,
            'text_sha256': hashlib.sha256(text.encode()).hexdigest()}


def assert_parity(session, texts, snapshot, anchors, **policy):
    replay = session.update(texts, snapshot)
    fresh = [build_graph(texts, snapshot, [anchor], **policy) for anchor in anchors]
    assert [canonical_graph_bytes(g) for g in replay.graphs] == [
        canonical_graph_bytes(g) for g in fresh]
    for graph in replay.graphs:
        validate_graph(graph)
        if graph['frontier']:
            assert not compare_graphs(graph, graph)['fresh']
    assert replay.reused + replay.rebuilt == len(anchors)
    return replay


@pytest.mark.parametrize('case', CASES, ids=lambda case: case.case_id)
def test_all_72_frozen_cases_preserve_fresh_build_bytes_and_statuses(case):
    anchors = [oracle_anchor(case)]
    session = GraphSession(anchors, mode=MODE, max_depth=8)
    assert_parity(session, case.before, 'before', anchors, max_depth=8)
    stable = assert_parity(session, case.before, 'unchanged-input', anchors, max_depth=8)
    assert stable.reused == 1
    changed = assert_parity(session, case.after, 'after', anchors, max_depth=8)
    assert_parity(session, case.before, 'restored', anchors, max_depth=8)
    # Runtime-effect fixtures retain the original resolver's declared boundary.
    # 不重标原样例；图相等不证明其中运行时副作用已被静态契约覆盖。
    expected = build_graph(case.after, 'after', anchors, max_depth=8)
    assert compare_graphs(changed.graphs[0], expected)['fresh'] == compare_graphs(expected, expected)['fresh']


def negative_sources():
    return {'app.py': 'from pkg import missing\ndef entry():\n    return missing()\n',
            'pkg/__init__.py': '# no such binding\n', 'unrelated.py': 'VALUE = 1\n'}


def test_default_remains_complete_only_but_ablation_reuses_unknown_unchanged_reads():
    before = negative_sources()
    anchors = [selected(before['app.py'])]
    after = before | {'unrelated.py': 'VALUE = 2\n'}
    for mode in (None, 'read_set_certificate', MODE):
        session = GraphSession(anchors, **({} if mode is None else {'mode': mode}))
        first = assert_parity(session, before, 'before', anchors)
        replay = assert_parity(session, after, 'after', anchors)
        assert first.graphs[0]['frontier']
        assert replay.reused == (1 if mode == MODE else 0)
        assert replay.graphs[0]['frontier'] == first.graphs[0]['frontier']
        assert not compare_graphs(first.graphs[0], replay.graphs[0])['fresh']


@pytest.mark.parametrize('replacement', [
    'def missing():\n    return 1\n',
    'def __getattr__(name):\n    return 1\n',
    'from elsewhere import *\n',
    'not valid (\n',
])
def test_node_free_negative_lookup_changes_force_rebuild_and_restore(replacement):
    before = negative_sources()
    anchors = [selected(before['app.py'])]
    session = GraphSession(anchors, mode=MODE)
    first = assert_parity(session, before, 'before', anchors)
    assert 'pkg/__init__.py' not in {n['path'] for n in first.graphs[0]['nodes'].values()}
    after = before | {'pkg/__init__.py': replacement}
    assert assert_parity(session, after, 'after', anchors).rebuilt == 1
    assert assert_parity(session, before, 'restored', anchors).rebuilt == 1


def test_missing_import_path_addition_invalidates_catalog():
    before = {'app.py': 'from absent import helper\ndef entry():\n    return helper()\n'}
    anchors = [selected(before['app.py'])]
    session = GraphSession(anchors, mode=MODE)
    assert_parity(session, before, 'before', anchors)
    after = before | {'absent.py': 'def helper():\n    return 3\n'}
    result = assert_parity(session, after, 'after', anchors)
    assert result.reasons == {'catalog_changed': 1}
    assert not result.graphs[0]['frontier']
    removed = assert_parity(session, before, 'removed', anchors)
    assert removed.rebuilt == 1
    assert removed.graphs[0]['frontier']


def chain_sources():
    return {'app.py': 'from helper import helper\ndef entry():\n    return helper()\n',
            'helper.py': 'from leaf import leaf\ndef helper():\n    return leaf()\n',
            'leaf.py': 'def leaf():\n    return 1\n', 'unrelated.py': 'VALUE = 1\n'}


@pytest.mark.parametrize('policy', [{'max_nodes': 1}, {'max_depth': 0}, {'max_depth': 1}])
def test_truncated_graph_reuse_preserves_frontier_and_never_becomes_fresh(policy):
    before = chain_sources()
    anchors = [selected(before['app.py'])]
    session = GraphSession(anchors, mode=MODE, **policy)
    first = assert_parity(session, before, 'before', anchors, **policy)
    assert any(f['kind'] == 'truncated' for f in first.graphs[0]['frontier'])
    after = before | {'unrelated.py': 'VALUE = 2\n'}
    reused = assert_parity(session, after, 'after', anchors, **policy)
    assert reused.reused == 1
    assert reused.graphs[0]['frontier'] == first.graphs[0]['frontier']
    assert not compare_graphs(first.graphs[0], reused.graphs[0])['fresh']


def test_node_budget_excluded_target_still_records_the_lookup_file():
    before = chain_sources()
    anchors = [selected(before['app.py'])]
    session = GraphSession(anchors, mode=MODE, max_nodes=1)
    first = assert_parity(session, before, 'before', anchors, max_nodes=1)
    assert 'helper.py' not in {n['path'] for n in first.graphs[0]['nodes'].values()}
    after = before | {'helper.py': 'def helper():\n    return 9\n'}
    changed = assert_parity(session, after, 'after', anchors, max_nodes=1)
    assert changed.rebuilt == 1
    assert changed.reasons == {'read_dependency_changed': 1}


def test_depth_zero_may_reuse_unread_dependency_but_keeps_truncation():
    before = chain_sources()
    anchors = [selected(before['app.py'])]
    session = GraphSession(anchors, mode=MODE, max_depth=0)
    assert_parity(session, before, 'before', anchors, max_depth=0)
    after = before | {'helper.py': 'def helper():\n    return 99\n'}
    result = assert_parity(session, after, 'after', anchors, max_depth=0)
    assert result.reused == 1
    assert result.graphs[0]['frontier']
    assert not compare_graphs(result.graphs[0], result.graphs[0])['fresh']


@pytest.mark.parametrize('state', ['missing-file', 'missing-symbol', 'unparseable-anchor'])
def test_unavailable_anchor_can_be_cached_without_losing_its_state_then_restored(state):
    original = 'def entry():\n    return 1\n'
    anchors = [selected(original)]
    before = {'unrelated.py': 'VALUE = 1\n'}
    if state == 'missing-symbol':
        before['app.py'] = 'def other():\n    return 1\n'
    elif state == 'unparseable-anchor':
        before['app.py'] = 'def entry(\n'
    session = GraphSession(anchors, mode=MODE)
    first = assert_parity(session, before, 'before', anchors)
    expected = 'unresolved' if state == 'unparseable-anchor' else 'missing'
    assert first.graphs[0]['anchors'][0]['status'] == expected
    changed = before | {'unrelated.py': 'VALUE = 2\n'}
    reused = assert_parity(session, changed, 'unrelated', anchors)
    assert reused.reused == 1
    assert reused.graphs[0]['anchors'][0]['status'] == expected
    restored = changed | {'app.py': original}
    rebuilt = assert_parity(session, restored, 'restored', anchors)
    assert rebuilt.rebuilt == 1
    assert not rebuilt.graphs[0]['frontier']


def test_unparseable_import_candidate_is_tracked_until_fixed_and_broken_again():
    before = {'app.py': 'from helper import helper\ndef entry():\n    return helper()\n',
              'helper.py': 'def helper(\n', 'unrelated.py': 'VALUE = 1\n'}
    anchors = [selected(before['app.py'])]
    session = GraphSession(anchors, mode=MODE)
    initial = assert_parity(session, before, 'before', anchors)
    assert initial.graphs[0]['frontier']
    unrelated = before | {'unrelated.py': 'VALUE = 2\n'}
    assert assert_parity(session, unrelated, 'unrelated', anchors).reused == 1
    restored = unrelated | {'helper.py': 'def helper():\n    return 2\n'}
    fixed = assert_parity(session, restored, 'fixed', anchors)
    assert fixed.rebuilt == 1
    assert not fixed.graphs[0]['frontier']
    broken = assert_parity(session, unrelated, 'broken-again', anchors)
    assert broken.rebuilt == 1
    assert broken.graphs[0]['frontier']


def test_returned_unknown_frontier_mutation_cannot_upgrade_cached_status():
    before = negative_sources()
    anchors = [selected(before['app.py'])]
    session = GraphSession(anchors, mode=MODE)
    first = assert_parity(session, before, 'before', anchors)
    first.graphs[0]['frontier'].clear()
    first.graphs[0]['anchors'][0]['frontier'].clear()
    first.graphs[0]['anchors'][0]['status'] = 'unchanged'
    replay = assert_parity(session, before, 'next', anchors)
    assert replay.reused == 1
    assert replay.graphs[0]['frontier']
    assert not compare_graphs(replay.graphs[0], replay.graphs[0])['fresh']
