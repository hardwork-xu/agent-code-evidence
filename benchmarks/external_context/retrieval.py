"""Issue-only candidates and common physical-line packing / 仅问题定位与统一物理行打包。

This experimental adapter differs from the product's graph renderer. It never
reads labels, patches, files or executes repository code. Every UTF-8 byte of
the rendered issue, metadata and source counts against the context allowance.
完整图诊断在外部审计字段；不得把这些字段额外传给模型而不计预算。
"""
from __future__ import annotations

import ast
from collections import Counter, deque
from collections.abc import Mapping
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import PurePosixPath

from contextproof.graph import build_graph, validate_graph
from contextproof.index import _parse_file, source_lines
from contextproof.models import Chunk, Snapshot
from contextproof.retrieval import search, terms

METHODS = ('bm25_windows', 'bm25_declarations', 'anchors_only',
           'graph_expand', 'window_expand', 'file_expand')
BUDGETS = (8000, 16000, 32000)
WINDOW_LINES = 80
ANCHOR_LIMIT = 3
MAX_DEPTH = 2
MAX_NODES = 128


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class _Span:
    path: str
    start: int
    end: int


def _validate(texts, issue) -> dict[str, str]:
    if not isinstance(texts, Mapping) or not isinstance(issue, str):
        raise ValueError('source mapping and issue text required / 需要源码映射及问题文本')
    issue.encode('utf-8')
    copied = {}
    for path, text in texts.items():
        if not isinstance(path, str) or not isinstance(text, str):
            raise ValueError('source keys/values must be strings / 源码键值必须是字符串')
        p = PurePosixPath(path)
        if (not path or p.is_absolute() or '..' in p.parts or '\\' in path or '\0' in path
                or str(p) != path or path == '.' or p.suffix not in {'.py', '.pyi'}):
            raise ValueError('canonical relative Python source paths required / 需要规范相对Python路径')
        text.encode('utf-8')
        copied[path] = text
    return dict(sorted(copied.items()))


def _declarations(path: str, text: str, lines: list[str]) -> tuple[list[dict], list[dict]]:
    try:
        tree = ast.parse(text, filename=path)
    except (SyntaxError, ValueError, RecursionError) as error:
        return [], [{'kind': 'unsupported_parse', 'path': path,
                     'reason': type(error).__name__}]
    records = []
    pending = [(tree, ())]
    while pending:
        node, parents = pending.pop()
        scope = parents
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            scope = (*parents, node.name)
            start = min(node.lineno, *(d.lineno for d in node.decorator_list)) if node.decorator_list else node.lineno
            end = node.end_lineno
            snippet = ''.join(lines[start - 1:end])
            record = {'path': path, 'symbol': '.'.join(scope),
                      'kind': 'class' if isinstance(node, ast.ClassDef) else 'function',
                      'start_line': start, 'end_line': end, 'text': snippet,
                      'text_sha256': _sha(snippet)}
            record['id'] = _sha(_json(record))
            records.append(record)
        pending.extend((child, scope) for child in reversed(list(ast.iter_child_nodes(node))))
    return records, []


def _split(path: str, start: int, end: int) -> list[_Span]:
    return [_Span(path, first, min(first + WINDOW_LINES - 1, end))
            for first in range(start, end + 1, WINDOW_LINES)]


def _dedup(spans: list[_Span]) -> list[_Span]:
    return list(dict.fromkeys(spans))


def _graph_spans(graph: dict, anchors: list[dict]) -> list[_Span]:
    """Anchors then stable breadth-first dependencies / 先锚点再稳定广度优先依赖。"""
    roots = {row['entry_id']: row.get('node_id') for row in graph['anchors']}
    neighbors = {}
    for edge in graph['edges'].values():
        if edge['status'] != 'resolved':
            continue
        neighbors.setdefault(edge['source'], set()).update(
            node for node in [edge.get('target'), *edge.get('bindings', [])]
            if node in graph['nodes'])
    queue = deque(roots[a['id']] for a in anchors if roots.get(a['id']) in graph['nodes'])
    seen, spans = set(), []
    while queue:
        node_id = queue.popleft()
        if node_id in seen:
            continue
        seen.add(node_id)
        node = graph['nodes'][node_id]
        spans.extend(_split(node['path'], node['start_line'], node['end_line']))
        queue.extend(sorted(neighbors.get(node_id, []), key=lambda key: (
            graph['nodes'][key]['path'], graph['nodes'][key]['start_line'], key)))
    return _dedup(spans)


def _prepare(texts, issue, *, with_graph: bool) -> dict:
    texts = _validate(texts, issue)
    hashes = {p: _sha(t) for p, t in texts.items()}
    snapshot_id = _sha(_json(hashes))
    lines = {p: source_lines(t) for p, t in texts.items()}
    windows, declarations, owners, parse_frontier = [], [], [], []
    for path, text in texts.items():
        for span in _split(path, 1, len(lines[path])):
            snippet = ''.join(lines[path][span.start - 1:span.end])
            windows.append(Chunk(_sha(_json([path, span.start, span.end, hashes[path]])),
                                 path, span.start, span.end, snippet, '', 'window', hashes[path]))
        parsed, _ = _parse_file(path, text, hashes[path])
        # Innermost-owner chunks are disjoint: no parent-class copy of method text.
        # 最内层声明块互不重叠，不在父类索引中重复子方法源码。
        declarations.extend(c for c in parsed if c.kind in {'class', 'function'})
        records, failures = _declarations(path, text, lines[path])
        owners.extend(records)
        parse_frontier.extend(failures)
    window_hits = search(Snapshot(snapshot_id, hashes, windows, []), issue, limit=len(windows))
    declaration_hits = search(Snapshot(snapshot_id, hashes, declarations, []), issue,
                              limit=len(declarations))
    anchors, seen = [], set()
    for hit in declaration_hits:
        c = hit.chunk
        identity = (c.path, c.symbol, c.kind)
        if identity in seen:
            continue
        matches = [r for r in owners if (r['path'], r['symbol'], r['kind']) == identity
                   and r['start_line'] <= c.start_line <= c.end_line <= r['end_line']]
        if not matches:
            continue
        selected = min(matches, key=lambda r: (r['end_line'] - r['start_line'], r['start_line']))
        anchors.append({**selected, 'file_sha256': hashes[c.path]})
        seen.add(identity)
        if len(anchors) == ANCHOR_LIMIT:
            break
    anchor_spans = _dedup([s for a in anchors for s in
                          _split(a['path'], a['start_line'], a['end_line'])])
    candidate = {
        'bm25_windows': [_Span(h.chunk.path, h.chunk.start_line, h.chunk.end_line) for h in window_hits],
        'bm25_declarations': [_Span(h.chunk.path, h.chunk.start_line, h.chunk.end_line) for h in declaration_hits],
        'anchors_only': anchor_spans,
        'window_expand': _dedup(anchor_spans + [s for a in anchors for s in
            _split(a['path'], max(1, a['start_line'] - WINDOW_LINES),
                   min(len(lines[a['path']]), a['end_line'] + WINDOW_LINES))]),
    }
    # A strong non-graph control: BM25 ranks every window of the same anchor files;
    # unmatched windows follow in stable source order, with no dependency edges.
    # 强非图对照：锚点同文件全部窗口按BM25排序，其余按源码顺序，无依赖边。
    anchor_files = {a['path'] for a in anchors}
    ranked_file = [_Span(h.chunk.path, h.chunk.start_line, h.chunk.end_line)
                   for h in window_hits if h.chunk.path in anchor_files]
    candidate['file_expand'] = _dedup(anchor_spans + ranked_file + [
        _Span(c.path, c.start_line, c.end_line) for c in windows if c.path in anchor_files])
    graph_frontier, graph_error, graph_id = [], None, None
    candidate['graph_expand'] = []
    if with_graph and anchors:
        try:
            graph = build_graph(texts, snapshot_id, anchors,
                                max_depth=MAX_DEPTH, max_nodes=MAX_NODES)
            validate_graph(graph)
            # Resolution uncertainty must not erase the common lexical anchors.
            # 图解析的不确定性不得删除各展开方法共享的精确词法锚点。
            candidate['graph_expand'] = _dedup(anchor_spans + _graph_spans(graph, anchors))
            graph_frontier = graph['frontier']
            graph_id = graph['id']
        except (ValueError, RecursionError) as error:
            graph_error = type(error).__name__
            graph_frontier = [{'kind': 'graph_error', 'reason': graph_error}]
    return {'texts': texts, 'lines': lines, 'hashes': hashes, 'snapshot_id': snapshot_id,
            'issue': issue, 'anchors': anchors, 'candidates': candidate,
            'parse_frontier': parse_frontier, 'graph_frontier': graph_frontier,
            'graph_id': graph_id, 'graph_error': graph_error}


def _remaining(span: _Span, chosen: dict[str, set[int]]) -> list[_Span]:
    result, start = [], None
    for line in range(span.start, span.end + 2):
        available = line <= span.end and line not in chosen.get(span.path, set())
        if available and start is None:
            start = line
        elif not available and start is not None:
            result.append(_Span(span.path, start, line - 1))
            start = None
    return result


def _line_count(spans: list[_Span]) -> int:
    merged = {}
    for span in sorted(spans, key=lambda s: (s.path, s.start, s.end)):
        ranges = merged.setdefault(span.path, [])
        if ranges and span.start <= ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], span.end))
        else:
            ranges.append((span.start, span.end))
    return sum(end - start + 1 for ranges in merged.values() for start, end in ranges)


def _pack(prepared: dict, method: str, budget: int) -> dict:
    if type(budget) is not int or budget <= 0:
        raise ValueError('budget must be a positive UTF-8 byte count / 预算须为正UTF-8字节数')
    if method not in METHODS:
        raise ValueError('unknown retrieval method / 未知检索方法')
    spans = _dedup(prepared['candidates'][method])
    frontier = [*prepared['parse_frontier'], *(
        prepared['graph_frontier'] if method == 'graph_expand' else [])]
    counts = Counter(r['kind'] for r in frontier)
    # Same schema for every method; bounded diagnostics still consume real bytes.
    # 所有方法同一格式；有界诊断摘要仍按实际字节计费。
    summary = [{'kind': kind, 'count': count} for kind, count in sorted(counts.items())[:4]]
    total_lines = _line_count(spans)
    if not terms(prepared['issue']):
        base_status = 'empty_query'
    elif method == 'graph_expand' and prepared['graph_error']:
        base_status = 'graph_error'
    elif method in METHODS[2:] and not prepared['anchors']:
        base_status = 'no_anchor'
    elif not spans:
        base_status = 'no_match'
    else:
        base_status = 'ready'
    blocks, chosen = [], {}

    def envelope(items, selected_count):
        return {'kind': 'contextproof.external-context', 'schema_version': 1,
                'snapshot_id': prepared['snapshot_id'], 'method': method,
                'issue': prepared['issue'], 'budget': budget, 'unit': 'utf8_bytes',
                'scope': 'delivered-source-not-semantic-sufficiency',
                'status': 'partial' if base_status == 'ready' and selected_count < total_lines else base_status,
                'frontier_count': len(frontier), 'frontier_summary': summary,
                'frontier_summary_truncated': len(counts) > len(summary),
                'candidate_span_count': len(spans),
                'omitted_source_lines': total_lines - selected_count,
                'source_text_hashes': {p: prepared['hashes'][p] for p in sorted({b['path'] for b in items})},
                'blocks': items}

    empty = _json(envelope([], 0))
    metadata_fits = len(empty.encode('utf-8')) <= budget
    selected_count = 0
    rejected = 0
    if metadata_fits:
        for span in spans:
            for piece in _remaining(span, chosen):
                block = {'path': piece.path, 'start_line': piece.start, 'end_line': piece.end,
                         'text': ''.join(prepared['lines'][piece.path][piece.start - 1:piece.end])}
                count = piece.end - piece.start + 1
                trial = _json(envelope([*blocks, block], selected_count + count))
                if len(trial.encode('utf-8')) <= budget:
                    blocks.append(block)
                    selected_count += count
                    chosen.setdefault(piece.path, set()).update(range(piece.start, piece.end + 1))
                else:
                    # Skip this whole predeclared <=80-line piece; never budget-trim source.
                    # 跳过预先确定的整段，不按剩余预算任意截取源码。
                    rejected += 1
    value = envelope(blocks, selected_count)
    rendered = _json(value) if metadata_fits else ''
    if len(rendered.encode('utf-8')) > budget:
        raise AssertionError('final payload exceeds budget')
    return {'method': method, 'budget': budget, 'unit': 'utf8_bytes',
            'status': value['status'] if metadata_fits else 'budget_too_small',
            'rendered': rendered, 'consumed': len(rendered.encode('utf-8')),
            'rendered_sha256': _sha(rendered), 'blocks': blocks,
            'snapshot_id': prepared['snapshot_id'], 'source_text_hashes': prepared['hashes'],
            'unique_source_lines': selected_count, 'candidate_source_lines': total_lines,
            'rejected_piece_count': rejected, 'frontier': frontier,
            'anchors': prepared['anchors'], 'graph_id': prepared['graph_id'] if method == 'graph_expand' else None,
            'candidate_spans': [asdict(span) for span in spans],
            'diagnostics_scope': 'outside rendered; audit only, not delivered context'}


def retrieve_context(texts: Mapping[str, str], issue: str, *, method: str,
                     budget: int = 16000) -> dict:
    """Produce one issue-only payload without I/O / 不做I/O，仅由问题和源码产生上下文。

    All delivered metadata and the exact issue count toward the UTF-8 budget.
    Full audit-sidecar diagnostics do not constitute delivered evidence.
    完整问题及交付元数据均计预算；审计侧车不属于交付证据。
    """
    if method not in METHODS:
        raise ValueError('unknown retrieval method / 未知检索方法')
    return _pack(_prepare(texts, issue, with_graph=method == 'graph_expand'), method, budget)


def retrieve_all(texts: Mapping[str, str], issue: str, *, budgets=BUDGETS) -> list[dict]:
    """Share one index/ranking/graph across methods and budgets / 跨方法预算复用一次索引与图。

    Fixed experiment defaults are 8000/16000/32000 bytes, not tokens or KiB.
    固定默认值为8000/16000/32000字节，不是token或KiB。
    """
    budgets = tuple(budgets)
    if not budgets or any(type(b) is not int or b <= 0 for b in budgets) or len(set(budgets)) != len(budgets):
        raise ValueError('distinct positive budgets required / 需要互异正预算')
    prepared = _prepare(texts, issue, with_graph=True)
    return [_pack(prepared, method, budget) for method in METHODS for budget in budgets]
