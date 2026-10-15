"""Within-root dependency change demo / 查询根内无关新增与相关碰撞演示。

Synthetic input, real resolver path; no analyzed program execution or timing claim.
输入为合成，运行真实解析器；不执行被分析程序、不作为自然性能结果。
"""
import hashlib
import json

from contextproof.graph import build_graph, canonical_graph_bytes
from contextproof.reuse import GraphSession

source = 'from pkg.worker import compute\ndef run(x):\n    return compute(x)\n'
selected = 'def run(x):\n    return compute(x)\n'
anchor = {'id': 'catalog-demo', 'path': 'pkg/use.py', 'symbol': 'run', 'kind': 'function',
          'start_line': 2, 'end_line': 3, 'text': selected,
          'text_sha256': hashlib.sha256(selected.encode()).hexdigest()}
initial = {'pkg/use.py': source, 'pkg/worker.py': 'def compute(x):\n    return x * x + 1\n'}
unrelated = dict(initial, **{'pkg/other.py': 'def unused(x):\n    return x + 2\n'})
collision = dict(unrelated, **{'pkg/worker.pyi': 'def compute(x: int) -> int: ...\n'})
rows = []
for mode in ['incremental_read_set', 'incremental_catalog_coarse_guard',
             'incremental_catalog_root_guard', 'incremental_catalog_read_set']:
    session = GraphSession([anchor], mode=mode)
    session.update(initial, 'initial')
    update = session.update(unrelated, 'unrelated-within-root')
    collide = session.update(collision, 'candidate-collision')
    for texts, snapshot_id, replay in [(unrelated, 'unrelated-within-root', update),
                                       (collision, 'candidate-collision', collide)]:
        fresh = build_graph(texts, snapshot_id, [anchor])
        if canonical_graph_bytes(replay.graphs[0]) != canonical_graph_bytes(fresh):
            raise RuntimeError('fresh mismatch / fresh不一致')
    rows.append({'mode': mode, 'within_root_add_reused': update.reused,
                 'alias_collision_rebuilt': collide.rebuilt,
                 'frontier_entries': len(update.graphs[0]['frontier']),
                 'canonical_equal': True})
print(json.dumps({'scope / 范围': 'Synthetic mechanism demo; not natural performance / 合成机制演示，非自然性能',
                  'results': rows}, indent=2, ensure_ascii=False))
