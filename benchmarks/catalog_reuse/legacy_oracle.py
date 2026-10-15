"""Compare fresh graphs to the frozen, unmodified resolver / 对照未修改的固定解析器。

Only project resolver code runs; analyzed upstream programs are never executed.
仅运行解析器，不执行被分析的上游程序。该检查不证明 Python 语义。
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

from .suite import (ROOT, canonical, digest, fresh_graphs, load_inputs,
                    validate_protocol, write_new, environment)

REFERENCE = 'ce6e36de7f6860296d66dadcb3105a8bbda9eb9a'
WORKER = '''import hashlib,json,sys
sys.path.insert(0,sys.argv[1])
from contextproof.dependencies import _Corpus
from contextproof.graph import build_graph,canonical_graph_bytes
v=json.load(sys.stdin)
corpus=_Corpus.from_texts(v['texts'])
digests=[]
for anchor in v['anchors']:
    graph=build_graph(v['texts'],v['snapshot_id'],[anchor],_corpus=corpus,**v['policy'])
    digests.append(hashlib.sha256(canonical_graph_bytes(graph)).hexdigest())
print(json.dumps(digests))
'''


def reference_identity(checkout: Path) -> dict:
    """Reject modified resolver files / 拒绝已修改的参照解析器。"""
    head = subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', 'HEAD'],
                                   text=True, stderr=subprocess.PIPE).strip()
    if head != REFERENCE:
        raise ValueError('reference must use the fixed commit / 参照必须位于固定提交')
    status = subprocess.check_output(['git', '-C', str(checkout), 'status', '--porcelain',
                                     '--', 'src/contextproof'], text=True, stderr=subprocess.PIPE)
    if status:
        raise ValueError('reference resolver must be unmodified / 参照解析器不得修改')
    files = {}
    for path in sorted((checkout / 'src/contextproof').glob('*.py')):
        relative = path.relative_to(checkout).as_posix()
        committed = subprocess.check_output(['git', '-C', str(checkout), 'show',
                                            REFERENCE + ':' + relative], stderr=subprocess.PIPE)
        if path.read_bytes() != committed:
            raise ValueError('reference bytes differ from fixed commit / 参照字节与固定提交不符')
        files[relative] = digest(committed)
    if not files:
        raise ValueError('reference resolver sources are missing / 缺失参照源码')
    return {'source_commit': head, 'source_files_sha256': files}


def reference_graph_digests(checkout: Path, texts: dict, snapshot_id: str,
                            anchors: list[dict], policy: dict) -> list[str]:
    payload = {'texts': texts, 'snapshot_id': snapshot_id, 'anchors': anchors, 'policy': policy}
    child = subprocess.run([sys.executable, '-I', '-c', WORKER, str(checkout / 'src')],
                           input=canonical(payload), capture_output=True, timeout=120)
    if child.returncode:
        # Do not publish raw stderr: it can contain the local checkout path.
        # 不公开原始 stderr，避免本机路径外泄。
        raise RuntimeError('reference reconstruction failed / 参照重建失败')
    result = json.loads(child.stdout)
    if not isinstance(result, list) or len(result) != len(anchors):
        raise ValueError('reference output shape differs / 参照输出形状不符')
    return result


def compare(inputs: Path, protocol_path: Path, checkout: Path, output: Path) -> dict:
    """Retain every checked snapshot and failure / 保留全部已检查快照及失败。"""
    if output.exists() or output.is_symlink():
        raise FileExistsError('new output required / 需要全新结果路径')
    output.parent.mkdir(parents=True, exist_ok=True)
    result = {'schema_version': 1, 'status': 'running', 'rows': [],
              'started_at_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'Fresh resolver replay equivalence, not Python semantics',
              'command': 'python -m benchmarks.catalog_reuse.legacy_oracle --inputs INPUTS --protocol PROTOCOL --reference-checkout REFERENCE --output NEW_JSON'}
    try:
        protocol_raw = protocol_path.read_bytes()
        protocol = json.loads(protocol_raw)
        validate_protocol(protocol)
        result.update(reference=reference_identity(checkout), protocol_sha256=digest(protocol_raw),
                      input_manifest_sha256=digest(inputs.read_bytes()),
                      current_source_commit=subprocess.check_output(
                          ['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True,
                          stderr=subprocess.PIPE).strip(),
                      current_implementation_sha256=environment()['implementation_sha256'],
                      validator_sha256=digest(Path(__file__).read_bytes()))
        _, repositories = load_inputs(inputs, protocol)
        for repository in repositories:
            anchors = repository.anchors(repository.snapshots[repository.primary[0]].load())
            for commit, snapshot in sorted(repository.snapshots.items()):
                texts = snapshot.load()
                current = [digest(g) for g in fresh_graphs(texts, commit, anchors,
                                                          protocol['graph_policy'])]
                reference = reference_graph_digests(checkout, texts, commit, anchors,
                                                   protocol['graph_policy'])
                mismatches = [i for i, (a, b) in enumerate(zip(current, reference)) if a != b]
                row = {'repository': repository.name, 'snapshot_id': commit,
                       'source_tree_sha256': snapshot.metadata['source_tree_sha256'],
                       'current_graph_sha256': current, 'reference_graph_sha256': reference,
                       'mismatch_anchor_indices': mismatches, 'canonical_equal': not mismatches,
                       'status': 'passed' if not mismatches else 'failed'}
                result['rows'].append(row)
                print(json.dumps({'repository': repository.name, 'snapshot_id': commit,
                                  'status': row['status']}), flush=True)
                if mismatches:
                    raise RuntimeError('frozen reference mismatch / 固定参照不一致')
        result['status'] = 'passed'
    except Exception as error:
        result.update(status='failed', error_type=type(error).__name__,
                      error_code='reference_validation_incomplete_or_failed')
        raise
    finally:
        result.update(finished_at_utc=datetime.now(timezone.utc).isoformat(),
                      snapshot_count=len(result['rows']),
                      graph_count=sum(len(r['current_graph_sha256']) for r in result['rows']),
                      mismatch_graph_count=sum(len(r['mismatch_anchor_indices']) for r in result['rows']))
        write_new(output, result)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Fixed-resolver replay check / 固定解析器回放核对')
    parser.add_argument('--inputs', type=Path, required=True, help='Input manifest / 输入清单')
    parser.add_argument('--protocol', type=Path, required=True, help='Frozen protocol / 冻结协议')
    parser.add_argument('--reference-checkout', type=Path, required=True,
                        help='Unmodified fixed reference checkout / 未修改的固定参照checkout')
    parser.add_argument('--output', type=Path, required=True, help='New result JSON / 全新结果JSON')
    args = parser.parse_args(argv)
    try:
        result = compare(args.inputs, args.protocol, args.reference_checkout.resolve(), args.output)
    except Exception as error:
        print('Validation failed / 验证失败: ' + type(error).__name__, file=sys.stderr)
        return 2
    print(json.dumps({k: result[k] for k in ['status', 'snapshot_count', 'graph_count',
                                            'mismatch_graph_count']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
