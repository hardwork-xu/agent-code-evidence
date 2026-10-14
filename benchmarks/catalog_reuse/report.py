"""Generate identical bilingual results from sealed records / 从封存记录生成双语结果。"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from .suite import ROOT, METHODS, digest, safe_path, summarize, validate_results

INDEX = ROOT / 'benchmarks/catalog_reuse/results/index.json'


def load_records(index_path: Path = INDEX) -> tuple[dict, dict, dict]:
    """Check retained data and all snapshot digests before reporting / 报告前检查数据与摘要。"""
    index = json.loads(index_path.read_bytes())
    if index.get('status') != 'sealed' or index.get('schema_version') != 1:
        raise ValueError('result index is not sealed / 结果索引未封存')
    if digest((ROOT / 'benchmarks/catalog_reuse/protocol.json').read_bytes()) != index['protocol_sha256']:
        raise ValueError('frozen protocol changed / 冻结协议已变')
    if digest((ROOT / 'benchmarks/catalog_reuse/inputs.json').read_bytes()) != index['sources_pin_sha256']:
        raise ValueError('source pins changed / 来源固定记录已变')
    for relative, expected in index['files_sha256'].items():
        path = index_path.parent / safe_path(relative)
        if not path.is_file() or path.is_symlink() or digest(path.read_bytes()) != expected:
            raise ValueError('retained result file changed / 保留结果文件已变')
    folder = index_path.parent / safe_path(index['run_directory'])
    run = json.loads((folder / 'run.json').read_bytes())
    validate_results(run)
    if (run['protocol_sha256'] != index['protocol_sha256']
            or run['environment']['source_commit'] != index['measured_source_commit']
            or run['environment']['source_dirty']):
        raise ValueError('measured source/protocol identity differs / 实测源码或协议身份不符')
    rows = [json.loads(line) for line in (folder / 'rows.jsonl').read_text().splitlines()]
    if rows != run['rows']:
        raise ValueError('row journal differs from run / 逐行日志与运行记录不符')
    summary = summarize(run)
    if summary != json.loads((folder / 'summary.json').read_bytes()):
        raise ValueError('saved summary differs / 保存摘要不符')
    reference = json.loads((folder / 'legacy-oracle.json').read_bytes())
    if (reference.get('status') != 'passed' or reference['mismatch_graph_count'] != 0
            or reference['protocol_sha256'] != run['protocol_sha256']
            or reference['current_source_commit'] != run['environment']['source_commit']
            or reference['current_implementation_sha256'] != run['environment']['implementation_sha256']
            or reference['input_manifest_sha256'] != run['input_manifest_sha256']
            or reference['reference']['source_commit'] != run['protocol']['baseline_commit']):
        raise ValueError('frozen-reference check incomplete / 固定参照检查未完成')
    expected = {(r['repository'], commit) for r in run['sources'] for commit in r['source_tree_sha256']}
    refrows = reference['rows']
    keys = [(r['repository'], r['snapshot_id']) for r in refrows]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError('frozen-reference source grid differs / 固定参照来源网格不符')
    refs = dict(zip(keys, refrows))
    for row in run['rows']:
        ref = refs[row['repository'], row['snapshot_id']]
        if (not ref['canonical_equal'] or ref['current_graph_sha256'] != ref['reference_graph_sha256']
                or ref['current_graph_sha256'] != row['expected_graph_sha256']):
            raise ValueError('frozen-reference graph digest differs / 固定参照图摘要不符')
    for memory in run['memory_rows']:
        file = folder / ('memory-' + str([r['repository'] for r in run['sources']].index(memory['repository']))
                         + '-' + str(memory['repetition']) + '-' + str(METHODS.index(memory['method'])) + '.json')
        if json.loads(file.read_bytes()) != memory:
            raise ValueError('RSS file differs from run / RSS文件与运行记录不符')
    return index, run, summary


def table(summary: dict, chinese: bool) -> str:
    head = ('| 仓库 | C回放 ms | D回放 ms | D相对C减少 | D相对A减少 | D/C RSS | >=20% |'
            if chinese else '| Repository | C replay ms | D replay ms | D reduction vs C | D reduction vs A | D/C RSS | >=20% |')
    lines = [head, '|---|---:|---:|---:|---:|---:|---|']
    for name, group in summary['groups'].items():
        methods = group['methods']
        coarse = methods['incremental_catalog_root_guard']
        fine = methods['incremental_catalog_read_set']
        # Raw timers are nanoseconds; the runner's aggregate medians are milliseconds.
        lines.append(f"| {name} | {coarse['replay']['median_ms']:.3f} | {fine['replay']['median_ms']:.3f} | "
                     f"{100*group['primary_replay_reduction_D_vs_C']:.2f}% | "
                     f"{100*group['secondary_replay_reduction_D_vs_A']:.2f}% | "
                     f"{group['median_peak_rss_ratio_D_vs_C']:.3f} | "
                     f"{'yes' if group['replay_target_met'] else 'no'} |")
    return '\n'.join(lines)


def render(index: dict, run: dict, summary: dict, chinese: bool) -> str:
    rows = [r for r in run['rows'] if r['panel'] == 'primary' and r['repetition'] == 0
            and r['method'] == 'incremental_catalog_read_set']
    replay_rows = [r for r in rows if r['version_index'] > 0]
    catalog_batches = sum(r['catalog_changed'] for r in replay_rows)
    counts = Counter()
    for row in rows:
        counts.update(row['frontier_kinds'])
    location = '../../benchmarks/catalog_reuse/results/' + index['run_directory']
    wins = summary['repositories_meeting_replay_target']
    total_steps = len(run['rows'])
    measured_steps = sum(r['panel']=='primary' and r['repetition'] >= 0 for r in run['rows'])
    gate = 'passed' if summary['replay_target_met'] else 'failed'
    title = '# 目录依赖足迹：固定自然轨迹结果' if chinese else '# Catalog dependency footprints: fixed natural trajectories'
    opening = (f'运行 `{run["run_id"]}`，实测源码 `{index["measured_source_commit"]}`。主目标在 {wins}/4 库达成，整体性能门槛 **{gate}**。该结果仅支持固定解析器的回放一致性与工程成本，不是成熟研究、Python语义证明或agent效果。'
               if chinese else f'Run `{run["run_id"]}`, measured source `{index["measured_source_commit"]}`. The primary target was met in {wins}/4 repositories; the overall performance gate **{gate}**. This supports bounded resolver replay and engineering cost only, not mature research, Python semantic proof or agent benefit.')
    scope = (f'4库，17快照/库、24固定锚点/库；64个八转移批次中{catalog_batches}个有生产目录增删。一次预热、五次实测；保留{total_steps}条主/次级步骤，其中{measured_steps}条实测主步骤，另48个fresh RSS子进程。107个唯一快照共2568图与未修改旧解析器核对。重复与锚点不是独立样本。'
             if chinese else f'4 repositories,17 snapshots and24 fixed anchors each; {catalog_batches}/64 eight-transition batches changed the production catalog. One warmup and five measurements; {total_steps} retained primary/secondary steps, of which {measured_steps} are measured primary steps, plus48fresh RSS subprocesses. The unmodified resolver was checked on107unique snapshots/2568graphs. Repeats and anchors are not independent samples.')
    limits = ('全部unknown/truncated前沿均保留；RQ后续缺失锚点不替换。初始捕获和capture+replay总成本及每次RSS均在原始摘要中。未运行上游源码、模型或Docker；CI另行核验。来源样本便利且窗口时长不等，仅单机macOS测量；精细缓存不能弥补39任务pilot的检索负结果。'
              if chinese else 'Every unknown/truncated frontier remains; the later missing RQ anchor is not replaced. Initial capture, capture+replay totals and every RSS sample remain in raw summaries. No upstream source, model or Docker was executed; CI is verified separately. Convenience sources have unequal window durations and one macOS measurement host. Fine-grained caching does not repair the negative39-task localization pilot.')
    return '\n\n'.join([title, opening, scope, table(summary,chinese),
                           ('前沿状态计数（D首轮、含初始捕获；描述性、非语义错误率）：' if chinese else 'Frontier state counts (D first measured trajectory including capture; descriptive, not semantic error rate):') + '`' + json.dumps(dict(counts),sort_keys=True) + '`',
                           limits, f'[Protocol](CATALOG_PROTOCOL.md) · [Conditional guarantees](CATALOG_SOUNDNESS.md) · [Raw results]({location}/run.json) · [Frozen resolver check]({location}/legacy-oracle.json)'])+'\n'


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true',help='Verify generated documents / 核对生成文档')
    args=parser.parse_args(argv)
    index,run,summary=load_records()
    for chinese,language in [(False,'en'),(True,'zh')]:
        path=ROOT / 'docs' / language / 'CATALOG_RESULTS.md'
        expected=render(index,run,summary,chinese)
        if args.check:
            if not path.exists() or path.read_text()!=expected:
                raise ValueError('generated catalog report is stale / 生成目录报告已过期')
        else:
            path.write_text(expected)
    print('Catalog records and bilingual report checked / 目录记录和双语报告核对通过')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
