"""Independent payload/source checks / 独立验证交付字节及物理行。"""
import builtins
from collections import Counter
import inspect
import json
import hashlib
from pathlib import Path

import pytest

from benchmarks.external_context import retrieval as r


def physical_lines(text):
    # Deliberately independent of source_lines and its regex implementation.
    # 独立状态机，不复用待测模块的分行函数。
    result, first, i = [], 0, 0
    while i < len(text):
        if text[i] in '\r\n':
            end = i + 1
            if text[i] == '\r' and end < len(text) and text[end] == '\n':
                end += 1
            result.append(text[first:end])
            i = first = end
        else:
            i += 1
    if first < len(text):
        result.append(text[first:])
    return result


def verify_payload(result, texts, issue):
    assert result['consumed'] == len(result['rendered'].encode('utf-8')) <= result['budget']
    assert result['rendered_sha256'] == hashlib.sha256(result['rendered'].encode()).hexdigest()
    assert result['source_text_hashes'] == {
        path: hashlib.sha256(text.encode()).hexdigest() for path, text in texts.items()}
    if not result['rendered']:
        assert result['status'] == 'budget_too_small'
        assert result['blocks'] == [] and result['unique_source_lines'] == 0
        return
    payload = json.loads(result['rendered'])
    assert payload['issue'] == issue
    assert payload['blocks'] == result['blocks']
    assert payload['status'] == result['status']
    assert payload['method'] == result['method']
    assert payload['budget'] == result['budget']
    assert payload['source_text_hashes'] == {
        path: hashlib.sha256(texts[path].encode()).hexdigest()
        for path in {b['path'] for b in payload['blocks']}}
    seen = set()
    for block in payload['blocks']:
        path, start, end = block['path'], block['start_line'], block['end_line']
        lines = physical_lines(texts[path])
        assert 1 <= start <= end <= len(lines)
        assert end - start + 1 <= 80
        assert block['text'] == ''.join(lines[start - 1:end])
        keys = {(path, number) for number in range(start, end + 1)}
        assert not keys & seen
        seen.update(keys)
    assert len(seen) == result['unique_source_lines']
    assert payload['omitted_source_lines'] == result['candidate_source_lines'] - len(seen)
    assert result['consumed'] > sum(len(b['text'].encode()) for b in payload['blocks'])


@pytest.fixture
def source():
    return {'main.py': 'from helper import auxiliary\n\ndef invoice(amount):\n    return auxiliary(amount)\n',
            'helper.py': 'def auxiliary(amount):\n    return amount + 1\n'}


def test_all_methods_share_real_payload_contract(source):
    results = r.retrieve_all(source, 'invoice')
    assert len(results) == 18
    assert {(x['method'], x['budget']) for x in results} == {
        (m, b) for m in r.METHODS for b in [8000, 16000, 32000]}
    for result in results:
        verify_payload(result, source, 'invoice')
    graphs = [x for x in results if x['method'] == 'graph_expand']
    assert all(any(b['path'] == 'helper.py' for b in x['blocks']) for x in graphs)
    for method in ['anchors_only', 'window_expand', 'file_expand']:
        assert all({b['path'] for b in x['blocks']} == {'main.py'}
                   for x in results if x['method'] == method)
    assert len({json.dumps(x['anchors'], sort_keys=True) for x in results}) == 1


def test_18_outputs_prepare_indices_and_graph_only_once(source, monkeypatch):
    calls = Counter()
    old_parse, old_search, old_graph = r._parse_file, r.search, r.build_graph

    def parse(*args, **kwargs):
        calls['parse'] += 1
        return old_parse(*args, **kwargs)

    def search(*args, **kwargs):
        calls['search'] += 1
        return old_search(*args, **kwargs)

    def graph(*args, **kwargs):
        calls['graph'] += 1
        assert kwargs == {'max_depth': 2, 'max_nodes': 128}
        return old_graph(*args, **kwargs)

    monkeypatch.setattr(r, '_parse_file', parse)
    monkeypatch.setattr(r, 'search', search)
    monkeypatch.setattr(r, 'build_graph', graph)
    r.retrieve_all(source, 'invoice')
    assert calls == {'parse': len(source), 'search': 2, 'graph': 1}


@pytest.mark.parametrize('newline', ['\n', '\r\n', '\r'])
def test_utf8_and_physical_newlines_are_preserved(newline):
    text = newline.join(['def needle():', '    value = "你好😀\u2028\f世界"', '    return value'])
    source = {'unicode_变量.py': text}
    for result in r.retrieve_all(source, 'needle 你好'):
        verify_payload(result, source, 'needle 你好')
    full = r.retrieve_context(source, 'needle', method='anchors_only')
    assert full['unique_source_lines'] == 3
    assert ''.join(x['text'] for x in full['blocks']) == text


def test_large_declarations_are_fixed_80_line_pieces_not_budget_truncated():
    text = 'def needle():\n' + ''.join(f'    value_{i} = "' + 'x' * 50 + '"\n' for i in range(240))
    source = {'large.py': text}
    small = r.retrieve_context(source, 'needle', method='anchors_only', budget=8000)
    large = r.retrieve_context(source, 'needle', method='anchors_only', budget=32000)
    verify_payload(small, source, 'needle')
    verify_payload(large, source, 'needle')
    assert small['status'] == 'partial' and small['rejected_piece_count'] > 0
    assert large['unique_source_lines'] == 241
    assert [(s['start'], s['end']) for s in small['candidate_spans']] == [
        (1, 80), (81, 160), (161, 240), (241, 241)]
    assert all((b['start_line'], b['end_line']) in [(1, 80), (81, 160), (161, 240), (241, 241)]
               for b in small['blocks'])


def test_overlong_single_line_is_not_sliced():
    source = {'long.py': 'needle = "' + 'x' * 40000 + '"\n'}
    result = r.retrieve_context(source, 'needle', method='bm25_windows', budget=32000)
    verify_payload(result, source, 'needle')
    assert result['status'] == 'partial' and result['blocks'] == []
    assert result['candidate_source_lines'] == 1


def test_parent_child_decl_index_and_payload_do_not_duplicate_lines(monkeypatch):
    text = 'class NeedleParent:\n    marker = "needle"\n    def needle_method(self):\n        return self.marker\n'
    source = {'nested.py': text}
    original = r.search
    observed = []

    def search(snapshot, *args, **kwargs):
        if snapshot.chunks and snapshot.chunks[0].kind != 'window':
            counts = Counter((c.path, n) for c in snapshot.chunks
                             for n in range(c.start_line, c.end_line + 1))
            assert max(counts.values()) == 1
            observed.append(counts)
        return original(snapshot, *args, **kwargs)

    monkeypatch.setattr(r, 'search', search)
    result = r.retrieve_context(source, 'NeedleParent needle_method', method='anchors_only')
    verify_payload(result, source, 'NeedleParent needle_method')
    assert len(result['anchors']) == 2 and observed
    assert result['unique_source_lines'] == 4


def test_top_three_anchors_are_fixed_not_budget_dependent():
    source = {'many.py': ''.join(f'def needle_{i}():\n    return {i}\n' for i in range(6))}
    results = r.retrieve_all(source, 'needle')
    assert all(len(row['anchors']) == 3 for row in results)
    assert len({json.dumps(row['anchors'], sort_keys=True) for row in results}) == 1


def test_fixed_nonoverlapping_windows_and_plain_file_expansion():
    source = {'file.py': 'def needle():\n    return 1\n' + '# filler\n' * 240}
    window = r.retrieve_context(source, 'needle', method='bm25_windows')
    assert [(s['start'], s['end']) for s in window['candidate_spans']] == [(1, 80)]
    expanded = r.retrieve_context(source, 'needle', method='file_expand', budget=32000)
    verify_payload(expanded, source, 'needle')
    assert expanded['unique_source_lines'] == 242
    nearby = r.retrieve_context(source, 'needle', method='window_expand', budget=32000)
    verify_payload(nearby, source, 'needle')
    assert nearby['unique_source_lines'] == 82


@pytest.mark.parametrize('issue', ['', '   ', '!?.,'])
def test_empty_query_is_not_filled_with_arbitrary_files(source, issue):
    for row in r.retrieve_all(source, issue):
        verify_payload(row, source, issue)
        assert row['status'] == 'empty_query' and row['blocks'] == []


def test_empty_source_and_no_declaration_anchor():
    assert all(x['blocks'] == [] for x in r.retrieve_all({}, 'needle'))
    source = {'settings.py': 'needle = 4\n'}
    rows = r.retrieve_all(source, 'needle')
    assert all(x['status'] == 'no_anchor' for x in rows if x['method'] in r.METHODS[2:])
    assert all(x['blocks'] for x in rows if x['method'] == 'bm25_windows')


def test_complete_issue_and_metadata_are_charged(source):
    issue = 'invoice ' + '中文😀' * 1000
    result = r.retrieve_context(source, issue, method='bm25_windows', budget=8000)
    verify_payload(result, source, issue)
    assert result['status'] == 'budget_too_small'
    assert result['consumed'] == 0 and result['blocks'] == []


def test_graph_frontier_is_bounded_in_payload_and_explicit_outside():
    source = {'app.py': 'def needle():\n' + ''.join(f'    unknown_{i}()\n' for i in range(50))}
    result = r.retrieve_context(source, 'needle', method='graph_expand')
    verify_payload(result, source, 'needle')
    payload = json.loads(result['rendered'])
    assert result['frontier'] and payload['frontier_count'] == len(result['frontier'])
    assert len(payload['frontier_summary']) <= 4
    assert all(set(x) == {'kind', 'count'} for x in payload['frontier_summary'])
    assert 'frontier' not in payload and payload['scope'].endswith('not-semantic-sufficiency')


def test_parser_failure_is_reported_and_does_not_hide_lexical_source():
    source = {'broken.py': 'def needle(\n'}
    rows = r.retrieve_all(source, 'needle')
    assert all(any(x['kind'] == 'unsupported_parse' for x in row['frontier']) for row in rows)
    assert any(row['blocks'] for row in rows if row['method'] == 'bm25_windows')


def test_graph_failure_retained_without_poisoning_baselines(source, monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError('injected graph failure')
    monkeypatch.setattr(r, 'build_graph', fail)
    results = r.retrieve_all(source, 'invoice')
    assert all(x['status'] == 'graph_error' and not x['blocks']
               for x in results if x['method'] == 'graph_expand')
    assert all(x['blocks'] for x in results if x['method'] == 'anchors_only')


def test_ambiguous_graph_owner_keeps_common_exact_anchor_source():
    source = {'conditional.py': 'if True:\n    def needle():\n        return 1\n'
              'else:\n    def needle():\n        return 2\n'}
    rows = {row['method']: row for row in r.retrieve_all(source, 'needle', budgets=(8000,))}
    baseline, graph = rows['anchors_only'], rows['graph_expand']
    verify_payload(graph, source, 'needle')
    assert baseline['blocks'] and graph['blocks'] == baseline['blocks']
    assert graph['candidate_spans'] == baseline['candidate_spans']
    assert any(f['kind'] == 'unresolved' for f in graph['frontier'])
    assert json.loads(graph['rendered'])['frontier_count'] > 0


def test_graph_depth_and_node_boundaries_retain_physical_source_and_frontiers():
    chain = {'chain.py': 'def needle():\n    return second()\n'
             'def second():\n    return third()\n'
             'def third():\n    return fourth()\n'
             'def fourth():\n    return 4\n'}
    depth = r.retrieve_context(chain, 'needle', method='graph_expand')
    verify_payload(depth, chain, 'needle')
    assert {(b['start_line'], b['end_line']) for b in depth['blocks']} == {
        (1, 2), (3, 4), (5, 6)}
    assert any(f['kind'] == 'truncated' and f['depth'] == 2 for f in depth['frontier'])
    wide = {'wide.py': 'def needle():\n'
            + ''.join(f'    callee_{i}()\n' for i in range(130))
            + ''.join(f'def callee_{i}():\n    return {i}\n' for i in range(130))}
    limited = r.retrieve_context(wide, 'needle', method='graph_expand', budget=32000)
    verify_payload(limited, wide, 'needle')
    assert any(f['kind'] == 'truncated' and f['reason'] == 'node budget exhausted'
               for f in limited['frontier'])
    assert limited['candidate_source_lines'] < len(physical_lines(wide['wide.py']))


def test_batch_and_single_method_deliver_identical_source(source):
    for result in r.retrieve_all(source, 'invoice'):
        single = r.retrieve_context(source, 'invoice', method=result['method'],
                                    budget=result['budget'])
        assert single == result


def test_deterministic_independent_of_input_mapping_order(source):
    assert r.retrieve_all(source, 'invoice') == r.retrieve_all(dict(reversed(list(source.items()))), 'invoice')


def test_no_file_reads_no_upstream_execution_no_gold_api(tmp_path, monkeypatch):
    marker = tmp_path / 'executed'
    text = f'from pathlib import Path\nPath({str(marker)!r}).write_text("bad")\n\ndef needle():\n    raise RuntimeError("do not execute")\n'
    source = {'unsafe.py': text}
    def forbidden(*args, **kwargs):
        raise AssertionError('retriever must not read files or labels')
    with monkeypatch.context() as patcher:
        patcher.setattr(builtins, 'open', forbidden)
        patcher.setattr(Path, 'read_text', forbidden)
        results = r.retrieve_all(source, 'needle')
    assert len(results) == 18 and not marker.exists()
    assert set(inspect.signature(r.retrieve_context).parameters) == {'texts', 'issue', 'method', 'budget'}
    assert set(inspect.signature(r.retrieve_all).parameters) == {'texts', 'issue', 'budgets'}


@pytest.mark.parametrize('path', ['/tmp/a.py', '../a.py', './a.py', 'a//b.py', 'a\\b.py', 'x.json'])
def test_unsafe_or_nonpython_paths_rejected(path):
    with pytest.raises(ValueError):
        r.retrieve_all({path: 'needle = 1'}, 'needle')


@pytest.mark.parametrize('budget', [0, -1, True, 1.5, '8000'])
def test_invalid_budgets(source, budget):
    with pytest.raises(ValueError):
        r.retrieve_context(source, 'invoice', method='anchors_only', budget=budget)
    with pytest.raises(ValueError):
        r.retrieve_all(source, 'invoice', budgets=(budget,))


def test_invalid_methods_types_and_duplicate_budgets(source):
    with pytest.raises(ValueError):
        r.retrieve_context(source, 'invoice', method='gold')
    with pytest.raises(ValueError):
        r.retrieve_all(source, 'invoice', budgets=(8000, 8000))
    with pytest.raises(ValueError):
        r.retrieve_all(source, None)
    with pytest.raises(ValueError):
        r.retrieve_all({'a.py': object()}, 'invoice')
