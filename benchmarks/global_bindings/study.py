"""Explicit-global reliability panel / 显式全局写入可靠性面板。

Only fixed developer-written fixtures execute here. Upstream sources are read
as text, never imported. Execution assertions live in the separate reviewed
upstream_execution runner. No timing or downstream repair claim is made.
此入口仅执行固定自编夹具；上游仅作文本，真实上游断言使用独立审阅入口。
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / 'research/frozen-catalog-20261014-source/src'
PIN = ROOT / 'benchmarks/global_bindings/inputs.json'
PROTOCOL = ROOT / 'benchmarks/global_bindings/protocol.json'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def safe_asset(root, name):
    """Only regular local files / 仅接受目录内普通文件。"""
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name
            or '\x00' in name or name.startswith('/') or any(p in {'', '.', '..'} for p in name.split('/'))):
        raise ValueError('unsafe input path / 不安全的输入路径')
    path = root
    for part in name.split('/'):
        path = path / part
        if path.is_symlink():
            raise ValueError('source symlink is not allowed / 不接受源码符号链接')
    if not path.is_file():
        raise ValueError('source file absent / 源码文件缺失')
    return path


def fingerprint(source):
    return {p.name: digest(p.read_bytes()) for p in sorted((source / 'contextproof').glob('*.py'))}


def validate_inputs(inputs):
    if inputs.get('schema_version') != 1 or len(inputs.get('head_panel', [])) != 8:
        raise ValueError('invalid fixed source panel')
    keys = [(s['repository'], s['sha']) for s in inputs['sources']]
    if len(keys) != 15 or len(set(keys)) != 15:
        raise ValueError('source versions must remain distinct')
    if len(inputs['anchors']) != 10 or len(inputs['own_fixtures']) != 32:
        raise ValueError('fixed anchor/fixture panel differs')
    for row in inputs['sources']:
        if not row['files'] or len(row['files']) > 1500:
            raise ValueError('invalid source file bound')
        if sum(x['bytes'] for x in row['files'].values()) > 16 * 1024**2:
            raise ValueError('source byte cap exceeded')


def select(text, path, symbol):
    """Independent AST identity selection / 独立按AST身份选择锚点。"""
    found = []

    def visit(node, parents=()):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = (*parents, child.name)
                if '.'.join(name) == symbol:
                    found.append(child)
                visit(child, name)
            else:
                visit(child, parents)
    visit(ast.parse(text))
    if len(found) != 1:
        raise ValueError('anchor absent or ambiguous')
    node = found[0]
    value = ''.join(text.splitlines(keepends=True)[node.lineno - 1:node.end_lineno])
    return {'id': digest(canonical([path, symbol])), 'path': path, 'symbol': symbol,
            'kind': 'class' if isinstance(node, ast.ClassDef) else 'function',
            'start_line': node.lineno, 'end_line': node.end_lineno,
            'text': value, 'text_sha256': digest(value.encode()),
            'file_sha256': digest(text.encode())}


def graph_record(graph, watched=()):
    # Never publish upstream source excerpts or local paths in graph metadata.
    # 图记录不包含上游源码片段或本机路径。
    from contextproof.graph import canonical_graph_bytes
    return {'canonical_sha256': digest(canonical_graph_bytes(graph)),
            'resolver_version': graph['policy']['resolver_version'],
            'nodes': len(graph['nodes']), 'edges': len(graph['edges']),
            'frontier_free': not graph['frontier'],
            'frontier_reasons': sorted({x['reason'] for x in graph['frontier']}),
            'watched_edges': [{k: e[k] for k in ('source', 'expression', 'operation', 'status', 'reason')}
                              for e in sorted(graph['edges'].values(), key=lambda e: e['id'])
                              if e['expression'] in watched]}


def value_state(namespace):
    try:
        value = namespace['getter']()
        return {'status': 'value', 'type': type(value).__name__,
                'value': value if type(value) in (int, float, str, bool, type(None)) else None}
    except Exception as error:
        return {'status': 'error', 'type': type(error).__name__}


def run(role, source_root, output):
    protocol = read(PROTOCOL)
    inputs = read(PIN)
    validate_inputs(inputs)
    source = BASELINE if role == 'baseline' else ROOT / 'src'
    if (protocol['inputs_sha256'] != digest(PIN.read_bytes())
            or protocol['runner_sha256'] != digest(Path(__file__).read_bytes())
            or protocol['engines'][role]['fingerprint'] != fingerprint(source)):
        raise ValueError('protocol/source fingerprint mismatch / 协议或源码指纹不匹配')
    sys.path.insert(0, str(source))
    import contextproof
    from contextproof.graph import RESOLVER_VERSION, build_graph
    if Path(contextproof.__file__).resolve().parent != (source / 'contextproof').resolve():
        raise ValueError('engine import path differs; use separate fresh processes')
    if RESOLVER_VERSION != protocol['engines'][role]['resolver_version']:
        raise ValueError('resolver version mismatch')
    own = []
    for case in inputs['own_fixtures']:
        text = case['source']
        row = {'case': case['name'], 'source_sha256': digest(text.encode()),
               'possible_global_write': case['possible_global_write'],
               'expected_runtime_change': case['runtime_changes']}
        try:
            namespace = {}
            exec(compile(text, 'own_fixture.py', 'exec'), namespace)
            before = value_state(namespace)
            namespace['writer']()
            after = value_state(namespace)
            built = build_graph({'own_fixture.py': text}, 'own-' + case['name'],
                                [select(text, 'own_fixture.py', 'getter')], **protocol['graph_policy'])
            row.update(status='ok', runtime_changed=before != after, before=before, after=after,
                       graph=graph_record(built, ['x']))
        except Exception as error:
            # Keep failed fixtures; errors never become successful measurements.
            # 保留失败夹具，不将异常包装为成功测量。
            row.update(status='failed', error_type=type(error).__name__)
        own.append(row)
    # Validate all 15 sources, including zero-match repositories with no anchors.
    # 保留无匹配仓库，并核对全部15个版本，不按候选结果删选。
    corpora = {}
    assets = []
    for item in inputs['sources']:
        texts = {}
        for name, pin in item['files'].items():
            raw = safe_asset(source_root, item['directory'] + '/' + name).read_bytes()
            if len(raw) != pin['bytes'] or digest(raw) != pin['sha256']:
                raise ValueError('source bytes differ from fixed input')
            texts[name] = raw.decode('utf-8')
        key = (item['repository'], item['sha'])
        corpora[key] = texts
        assets.append({'repository': key[0], 'sha': key[1], 'files': len(texts),
                       'bytes': sum(x['bytes'] for x in item['files'].values()),
                       'source_role': item['source_role'], 'status': 'verified'})
    natural = []
    for item in inputs['anchors']:
        row = dict(item)
        texts = corpora[(item['repository'], item['sha'])]
        try:
            anchor = select(texts[item['path']], item['path'], item['symbol'])
            graph = build_graph(texts, item['sha'], [anchor], **protocol['graph_policy'])
            row.update(status='built', anchor_text_sha256=anchor['text_sha256'],
                       graph=graph_record(graph, item.get('watched_names', [])))
        except Exception as error:
            row.update(status='failed', error_type=type(error).__name__)
        natural.append(row)
    result = {'schema_version': 1, 'run_id': 'globals-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + role,
              'time_utc': datetime.now(timezone.utc).isoformat(), 'role': role,
              'classification': protocol['classification'], 'protocol_sha256': digest(PROTOCOL.read_bytes()),
              'inputs_sha256': digest(PIN.read_bytes()), 'engine': protocol['engines'][role],
              'environment': {'python': platform.python_version(), 'system': platform.system(),
                              'machine': platform.machine()},
              'upstream_source_executed_by_graph_runner': False,
              'performance_measured': False, 'own': own, 'assets': assets, 'natural': natural}
    with output.open('xb') as stream:
        stream.write(canonical(result) + b'\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', choices=('baseline', 'candidate'), required=True,
                        help='Fixed original or repaired resolver / 原版或修复版')
    parser.add_argument('--source-root', type=Path, required=True,
                        help='Prepared pinned source directory / 固定源码准备目录')
    parser.add_argument('--output', type=Path, required=True,
                        help='New result file; never overwrite / 新结果文件，不覆盖')
    args = parser.parse_args()
    result = run(args.role, args.source_root, args.output)
    print(result['run_id'], 'own', len(result['own']), 'natural', len(result['natural']))


if __name__ == '__main__':
    main()
