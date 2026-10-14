"""Validate and pair fixed development results / 校验并配对固定开发结果。

Hashes bind artifacts, not authorship or semantic truth. This report does not
execute source, import either engine, measure speed, or infer semantic accuracy.
哈希仅绑定产物；本报告不执行源码、导入引擎、计时或推断语义准确率。
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
PIN = ROOT / 'benchmarks/global_bindings/inputs.json'
PROTOCOL = ROOT / 'benchmarks/global_bindings/protocol.json'
ROLES = ('baseline', 'candidate')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def read(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('missing or symlinked result asset')
    return json.loads(path.read_bytes())


def fail(message):
    raise ValueError(message)


def keyed(rows, fields, expected, label):
    if not isinstance(rows, list):
        fail(label + ' must be a list')
    mapped = {}
    for row in rows:
        if not isinstance(row, dict) or any(field not in row for field in fields):
            fail(label + ' row identity missing')
        key = tuple(row[field] for field in fields)
        if key in mapped:
            fail(label + ' duplicate identity')
        mapped[key] = row
    if set(mapped) != set(expected):
        fail(label + ' fixed denominator or key set differs')
    return mapped


def validate_graph_record(graph, version, policy):
    if not isinstance(graph, dict) or set(graph) != {
            'canonical_sha256', 'resolver_version', 'nodes', 'edges',
            'frontier_free', 'frontier_reasons', 'watched_edges'}:
        fail('graph record schema differs')
    if not sha(graph['canonical_sha256']) or graph['resolver_version'] != version:
        fail('graph source seal or resolver version differs')
    if any(type(graph[key]) is not int or graph[key] < 0 for key in ('nodes', 'edges')):
        fail('graph counts must be nonnegative integers')
    if graph['nodes'] > policy['max_nodes'] or type(graph['frontier_free']) is not bool:
        fail('graph bounds or frontier flag invalid')
    reasons = graph['frontier_reasons']
    if (not isinstance(reasons, list) or any(not isinstance(r, str) or not r for r in reasons)
            or reasons != sorted(set(reasons)) or graph['frontier_free'] != (not reasons)):
        fail('frontier reasons and flag disagree')
    watched = graph['watched_edges']
    if not isinstance(watched, list) or len(watched) > graph['edges']:
        fail('invalid watched-edge count')
    keys = set()
    for edge in watched:
        if not isinstance(edge, dict) or set(edge) != {'source', 'expression', 'operation', 'status', 'reason'}:
            fail('watched edge schema differs')
        key = (edge['source'], edge['expression'], edge['operation'])
        if (not sha(edge['source']) or not isinstance(edge['expression'], str)
                or not edge['expression'] or edge['operation'] not in {'read', 'call', 'scope'}
                or edge['status'] not in {'resolved', 'unresolved', 'truncated'}
                or not isinstance(edge['reason'], str) or not edge['reason'] or key in keys):
            fail('invalid or duplicate watched edge')
        if edge['status'] != 'resolved' and edge['reason'] not in reasons:
            fail('nonresolved watched edge has no retained frontier reason')
        keys.add(key)
    return graph


def validate_state(state):
    if not isinstance(state, dict) or state.get('status') not in {'value', 'error'}:
        fail('invalid runtime state')
    wanted = {'status', 'type', 'value'} if state['status'] == 'value' else {'status', 'type'}
    if set(state) != wanted or not isinstance(state['type'], str) or not state['type']:
        fail('invalid runtime state fields')


def validate_record(result, role, inputs, protocol, protocol_sha, inputs_sha):
    fields = {'schema_version', 'run_id', 'time_utc', 'role', 'classification',
              'protocol_sha256', 'inputs_sha256', 'engine', 'environment',
              'upstream_source_executed_by_graph_runner', 'performance_measured',
              'own', 'assets', 'natural'}
    if (set(result) != fields or type(result.get('schema_version')) is not int
            or result['schema_version'] != 1 or result.get('role') != role
            or not isinstance(result.get('run_id'), str)
            or re.fullmatch(r'globals-\d{8}T\d{6}Z-' + role, result['run_id']) is None
            or result.get('protocol_sha256') != protocol_sha
            or result.get('inputs_sha256') != inputs_sha
            or result.get('classification') != protocol['classification']
            or result.get('engine') != protocol['engines'][role]
            or result.get('performance_measured') is not False
            or result.get('upstream_source_executed_by_graph_runner') is not False):
        fail('result role, run ID, classification, protocol or engine differs')
    if set(result.get('environment', {})) != {'python', 'system', 'machine'}:
        fail('environment record missing')
    own_expected = {(row['name'],): row for row in inputs['own_fixtures']}
    own = keyed(result.get('own'), ('case',), own_expected, 'own fixtures')
    for key, row in own.items():
        case = own_expected[key]
        common = {'case', 'source_sha256', 'possible_global_write', 'expected_runtime_change', 'status'}
        expected_keys = common | ({'error_type'} if row.get('status') == 'failed' else
                                  {'runtime_changed', 'before', 'after', 'graph'})
        if set(row) != expected_keys:
            fail('own row schema differs')
        if (row.get('source_sha256') != digest(case['source'].encode())
                or type(row.get('possible_global_write')) is not bool
                or row['possible_global_write'] is not case['possible_global_write']
                or type(row.get('expected_runtime_change')) is not bool
                or row['expected_runtime_change'] is not case['runtime_changes']):
            fail('own source or frozen expected label differs')
        if row.get('status') == 'failed':
            if not isinstance(row.get('error_type'), str) or not row['error_type'] or 'graph' in row:
                fail('failed own case must retain an error and no successful graph')
        elif row.get('status') == 'ok':
            validate_state(row.get('before'))
            validate_state(row.get('after'))
            if type(row.get('runtime_changed')) is not bool or row['runtime_changed'] != (row['before'] != row['after']):
                fail('runtime observation and change flag disagree')
            validate_graph_record(row.get('graph'), protocol['engines'][role]['resolver_version'], protocol['graph_policy'])
            edges = row['graph']['watched_edges']
            if len(edges) != 1 or edges[0]['expression'] != 'x' or edges[0]['operation'] != 'read':
                fail('own getter must retain its single watched read')
        else:
            fail('own case status invalid')
    asset_expected = {(row['repository'], row['sha']): row for row in inputs['sources']}
    assets = keyed(result.get('assets'), ('repository', 'sha'), asset_expected, 'source assets')
    for key, row in assets.items():
        source = asset_expected[key]
        if (set(row) != {'repository', 'sha', 'files', 'bytes', 'source_role', 'status'}
                or row.get('status') != 'verified' or type(row.get('files')) is not int
                or row['files'] != len(source['files']) or type(row.get('bytes')) is not int
                or row['bytes'] != sum(f['bytes'] for f in source['files'].values())
                or row.get('source_role') != source['source_role']):
            fail('fixed asset counts or role differ')
    fields = ('repository', 'sha', 'path', 'symbol', 'role')
    natural_expected = {tuple(row[field] for field in fields): row for row in inputs['anchors']}
    natural = keyed(result.get('natural'), fields, natural_expected, 'natural anchors')
    for key, row in natural.items():
        fixed = natural_expected[key]
        expected_keys = set(fixed) | {'status'} | ({'error_type'} if row.get('status') == 'failed'
                                                   else {'anchor_text_sha256', 'graph'})
        if set(row) != expected_keys:
            fail('natural row schema differs')
        if any(row.get(name) != value for name, value in fixed.items()):
            fail('fixed natural anchor metadata differs')
        if row.get('status') == 'failed':
            if not isinstance(row.get('error_type'), str) or not row['error_type'] or 'graph' in row:
                fail('failed natural row must retain its error')
        elif row.get('status') == 'built':
            if not sha(row.get('anchor_text_sha256')):
                fail('natural anchor source seal missing')
            validate_graph_record(row.get('graph'), protocol['engines'][role]['resolver_version'], protocol['graph_policy'])
            if any(edge['expression'] not in fixed.get('watched_names', []) for edge in row['graph']['watched_edges']):
                fail('unexpected watched natural expression')
        else:
            fail('natural row status invalid')
    return own, natural


def compare_edges(before, after):
    """Union actual node/expression/operation keys / 配对实际节点、表达式、操作键的并集。"""
    def key(edge):
        return edge['source'], edge['expression'], edge['operation']
    left, right = {key(e): e for e in before}, {key(e): e for e in after}
    return [{'source': k[0], 'expression': k[1], 'operation': k[2],
             'baseline': left.get(k), 'candidate': right.get(k),
             'changed': left.get(k) != right.get(k)} for k in sorted(left.keys() | right.keys())]


def validate_results(results_dir, *, protocol_path=PROTOCOL, inputs_path=PIN, require_index=True):
    directory = Path(results_dir)
    protocol_path, inputs_path = Path(protocol_path), Path(inputs_path)
    protocol, inputs = read(protocol_path), read(inputs_path)
    protocol_sha, inputs_sha = digest(protocol_path.read_bytes()), digest(inputs_path.read_bytes())
    if (protocol.get('schema_version') != 1 or protocol.get('inputs_sha256') != inputs_sha
            or protocol.get('runner_sha256') != digest((ROOT / 'benchmarks/global_bindings/study.py').read_bytes())
            or protocol.get('graph_policy') != {'max_depth': 4, 'max_nodes': 256}
            or set(protocol.get('engines', {})) != set(ROLES)
            or protocol['engines']['baseline']['resolver_version'] != 3
            or protocol['engines']['candidate']['resolver_version'] != 4
            or len(inputs.get('own_fixtures', [])) != 32 or len(inputs.get('anchors', [])) != 10
            or len(inputs.get('sources', [])) != 15):
        fail('fixed protocol/input denominator or runner binding differs')
    hashes, results, maps = {}, {}, {}
    for role in ROLES:
        filename = role + '.json'
        path = directory / filename
        results[role] = read(path)
        hashes[filename] = digest(path.read_bytes())
        maps[role] = validate_record(results[role], role, inputs, protocol, protocol_sha, inputs_sha)
    amendments = {}
    if (directory / 'amendments').exists():
        if (directory / 'amendments').is_symlink():
            fail('amendment directory is a symlink')
        for path in sorted((directory / 'amendments').rglob('*')):
            if path.is_symlink():
                fail('amendment asset is a symlink')
            if path.is_file():
                amendments[path.relative_to(directory).as_posix()] = digest(path.read_bytes())
    index = {'schema_version': 1, 'protocol_sha256': protocol_sha, 'inputs_sha256': inputs_sha,
             'files': hashes, 'run_ids': {role: results[role]['run_id'] for role in ROLES},
             'amendments': amendments}
    if require_index and read(directory / 'index.json') != index:
        fail('result integrity index differs')
    own_summary = {}
    for role in ROLES:
        rows = list(maps[role][0].values())
        own_summary[role] = {
            'cases': len(rows), 'failed': sum(row['status'] == 'failed' for row in rows),
            'observed_runtime_changes': sum(row.get('runtime_changed') is True for row in rows),
            'runtime_label_mismatches': sum(row['status'] == 'ok' and row['runtime_changed'] != row['expected_runtime_change'] for row in rows),
            'possible_write_cases': sum(row['possible_global_write'] for row in rows),
            'possible_write_resolved': sum(row['status'] == 'ok' and row['possible_global_write'] and row['graph']['watched_edges'][0]['status'] == 'resolved' for row in rows),
            'possible_write_unknown': sum(row['status'] == 'ok' and row['possible_global_write'] and row['graph']['watched_edges'][0]['status'] == 'unresolved' for row in rows),
            'nonwriting_controls': sum(not row['possible_global_write'] for row in rows),
            'nonwriting_controls_resolved': sum(row['status'] == 'ok' and not row['possible_global_write'] and row['graph']['watched_edges'][0]['status'] == 'resolved' for row in rows)}
    natural = []
    for key in sorted(maps['baseline'][1]):
        left, right = maps['baseline'][1][key], maps['candidate'][1][key]
        natural.append({'identity': dict(zip(('repository', 'sha', 'path', 'symbol', 'role'), key)),
            'baseline_status': left['status'], 'candidate_status': right['status'],
            'baseline_error_type': left.get('error_type'), 'candidate_error_type': right.get('error_type'),
            'baseline_frontier_free': left.get('graph', {}).get('frontier_free'),
            'candidate_frontier_free': right.get('graph', {}).get('frontier_free'),
            'watched_pairs': compare_edges(left.get('graph', {}).get('watched_edges', []), right.get('graph', {}).get('watched_edges', []))})
    return {'schema_version': 1, 'classification': protocol['classification'], 'index': index,
            'own': own_summary, 'natural': natural,
            'natural_statuses': {role: dict(Counter(row['status'] for row in maps[role][1].values())) for role in ROLES},
            'claim_boundary': 'Developer fixtures and fixed existing source diagnosis; no unseen accuracy, performance, downstream benefit or mature research claim.'}


def render(summary, language):
    chinese = language == 'zh'
    lines = ['# 显式全局绑定开发验证' if chinese else '# Explicit-global binding development verification', '',
        summary['classification'], '',
        '这是固定开发夹具与源码诊断；不报告未见样本准确率、性能或下游收益。' if chinese else
        'Fixed development fixtures and source diagnosis; no unseen accuracy, performance or downstream-benefit claim.', '',
        '| 记录 / Record | Baseline | Candidate |', '|---|---:|---:|']
    for field in ['cases', 'failed', 'observed_runtime_changes', 'runtime_label_mismatches',
                  'possible_write_cases', 'possible_write_resolved', 'possible_write_unknown',
                  'nonwriting_controls', 'nonwriting_controls_resolved']:
        lines.append(f"| {field} | {summary['own']['baseline'][field]} | {summary['own']['candidate'][field]} |")
    lines.extend(['', '## 固定源码锚点 / Fixed source anchors', '',
                  '| Repository / SHA / Symbol | Baseline | Candidate | Changed watched keys |', '|---|---|---|---:|'])
    for row in summary['natural']:
        identity = row['identity']
        title = identity['repository'] + ' / ' + identity['sha'][:8] + ' / ' + identity['symbol']
        left = row['baseline_status'] + (' / ' + row['baseline_error_type'] if row['baseline_error_type'] else '')
        right = row['candidate_status'] + (' / ' + row['candidate_error_type'] if row['candidate_error_type'] else '')
        lines.append(f"| {title} | {left} | {right} | {sum(p['changed'] for p in row['watched_pairs'])} |")
    lines.extend(['', '失败、未知、截断和修订记录保留；配对使用真实节点/表达式/操作键的并集。' if chinese else
        'Failures, unknowns, truncations and amendments are retained. Pairing uses the union of actual node/expression/operation keys.',
        '哈希绑定文件而非真实性签名；通过完整性检查不等于语义正确或成熟研究。' if chinese else
        'Hashes bind files and are not authenticity signatures; integrity checks do not establish semantic correctness or research maturity.', ''])
    return '\n'.join(lines)


def generate_report(results_dir, *, protocol_path=PROTOCOL, inputs_path=PIN):
    directory = Path(results_dir)
    summary = validate_results(directory, protocol_path=protocol_path, inputs_path=inputs_path, require_index=False)
    outputs = {'index.json': canonical(summary['index']) + b'\n',
               'summary.json': canonical(summary) + b'\n',
               'REPORT_en.md': render(summary, 'en').encode(), 'REPORT_zh.md': render(summary, 'zh').encode()}
    if any((directory / filename).exists() for filename in outputs):
        fail('generated report already exists; never overwrite retained evidence')
    for filename, raw in outputs.items():
        with (directory / filename).open('xb') as stream:
            stream.write(raw)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        summary = validate_results(args.results)
        if read(args.results / 'summary.json') != summary:
            fail('generated summary differs')
        for language in ('en', 'zh'):
            if (args.results / ('REPORT_' + language + '.md')).read_text() != render(summary, language):
                fail('generated bilingual report differs')
    else:
        summary = generate_report(args.results)
    print('validated roles', ', '.join(summary['index']['run_ids']), 'fixed own32/natural10/assets15')


if __name__ == '__main__':
    main()
