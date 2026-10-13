#!/usr/bin/env python3
"""Check frozen research claims offline / 离线核对研究声明与证据边界。

Passing is record consistency, never scientific maturity. This version knows one
frozen study profile; accepting a new claim needs new evidence and profile review.
通过仅表示记录一致，不代表研究成熟；新增结论需要新证据和新的评审配置。
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from scripts.check_attribution import safe_path  # noqa: E402
from scripts.check_research_artifacts import check_holdout, check_tasks  # noqa: E402

HOLDOUT = 'benchmarks/incremental_holdout/results/primary-20261004.json'
TASK = 'benchmarks/task_evidence/results/primary-20261004'
STATES = {
    'C1-source-identity': 'supported_artifact_identity',
    'C2-replay-parity': 'supported_frozen_sample',
    'C3-replay-performance': 'supported_frozen_sample',
    'C4-semantic-freshness': 'not_established_zero_complete_coverage',
    'C5-execution-witness': 'supported_development_diagnostic',
    'C6-agent-task-benefit': 'not_established',
    'C7-novelty': 'scoped_engineering_contribution_only',
    'C8-external-validation': 'not_done',
}
GAPS = {'semantic-freshness', 'task-relevance', 'agent-benefit', 'generality',
        'contribution-assessment'}


def read(root: Path, name: str):
    return json.loads(safe_path(root, name).read_text())


def metrics(root: Path) -> dict:
    """Recalculate saved measurements, not new executions / 回算而非重新实验。"""
    h = read(root, HOLDOUT)
    cases = read(root, TASK + '/cases.json')
    totals = defaultdict(lambda: defaultdict(int))
    for row in h['timing_rows']:
        if row['phase'] == 'replay':
            totals[(row['group'], row['method'])][row['repetition']] += row['elapsed_ns']
    timing = []
    for group in sorted({r['group'] for r in h['timing_rows']}):
        baseline = statistics.median(totals[(group, 'incremental_whole_corpus_guard')].values())
        candidate = statistics.median(totals[(group, 'incremental_read_set')].values())
        timing.append({'repository': group.removeprefix('natural:'),
                       'baseline_ms': baseline / 1e6, 'candidate_ms': candidate / 1e6,
                       'reduction': 1 - candidate / baseline,
                       'rss_ratio': h['summary']['groups'][group.removeprefix('natural:')]['candidate_rss_ratio'],
                       'memory_gate_met': h['summary']['groups'][group.removeprefix('natural:')]['memory_gate_met']})
    task_rows = []
    for case in cases:
        g = case['metrics']['fresh_graph']
        b = case['metrics']['lexical_matched_lines']
        full = case['metrics']['fresh_full_source']['context_lines']
        task_rows.append({'id': case['id'], 'repository': case['repository'],
                          'graph_recall': g['recall'], 'bm25_recall': b['recall'],
                          'graph_lines': g['context_lines'], 'corpus_lines': full,
                          'covered_witness_lines': g['covered_witness_lines'],
                          'execution_density': g['covered_witness_lines'] / g['context_lines'],
                          'context_fraction': g['context_lines'] / full})
    return {'reference_graphs': sum(len(r['graphs']) for r in h['cold_reference']),
            'complete_graphs': sum(r['complete'] for r in h['cold_reference']),
            'canonical_mismatches': h['summary']['canonical_mismatches'],
            'timing': timing, 'tasks': task_rows,
            'macro_graph_recall': statistics.mean(r['graph_recall'] for r in task_rows),
            'macro_bm25_recall': statistics.mean(r['bm25_recall'] for r in task_rows),
            'macro_execution_density': statistics.mean(r['execution_density'] for r in task_rows),
            'macro_context_fraction': statistics.mean(r['context_fraction'] for r in task_rows)}


def validate(root: Path, *, validate_artifacts: bool = True) -> dict:
    """Fail closed on stale bytes or unsupported promotion / 拒绝旧证据与状态越级。"""
    ledger = read(root, 'research/claims.json')
    if (ledger['schema_version'] != 1
            or ledger['profile'] != 'frozen-20261004-research-claims-v1'
            or ledger['decision'] != 'mature_research_not_established'):
        raise ValueError('unreviewed research profile or maturity promotion / 未评审的配置或成熟度升级')
    claims = ledger['claims']
    if len(claims) != len(STATES) or {r['id']: r['state'] for r in claims} != STATES:
        raise ValueError('missing or promoted claim state / 声明缺失或状态越级')
    gaps = ledger['unmet_criteria']
    if len(gaps) != len(GAPS) or {r['id'] for r in gaps} != GAPS or any(
            r['status'] != 'missing' for r in gaps):
        raise ValueError('unreviewed removal of missing evidence / 未评审地移除缺失证据')
    hashes = ledger['evidence_sha256']
    required = {HOLDOUT, TASK + '/cases.json', TASK + '/runs.json',
                TASK + '/provenance.json', TASK + '/summary.json',
                'benchmarks/incremental_holdout/protocol.json',
                'benchmarks/incremental_holdout/manifest.json',
                'benchmarks/task_evidence/manifest.json'}
    required.update(p for claim in claims for p in claim['evidence'])
    required.update(p.relative_to(root).as_posix() for p in
                    (root / 'src/contextproof').glob('*.py'))
    if not required <= hashes.keys():
        raise ValueError('missing source/evidence hash / 缺失源码或证据哈希')
    for name, expected in hashes.items():
        if hashlib.sha256(safe_path(root, name).read_bytes()).hexdigest() != expected:
            raise ValueError('evidence hash mismatch: ' + name)
    h, p = read(root, HOLDOUT), read(root, TASK + '/provenance.json')
    if (h['run_id'] != ledger['holdout']['run_id']
            or p['run_id'] != ledger['tasks']['run_id']
            or h['environment']['source_commit'] != ledger['measured_commit']
            or p['git_head'] != ledger['measured_commit']):
        raise ValueError('run/source identity differs from ledger / 运行或源码身份不符')
    for name, measured_hash in h['provenance']['implementation_files'].items():
        if hashes.get(name) != measured_hash:
            raise ValueError('runtime differs from measured implementation: ' + name)
    primary = h['protocol_snapshot']['primary_comparison']
    if (ledger['holdout']['baseline'] != primary['baseline']
            or ledger['holdout']['candidate'] != primary['candidate']
            or ledger['holdout']['unit'] != 'repository'
            or ledger['tasks']['unit'] != 'case within known development repository'):
        raise ValueError('comparator or observation unit changed / 对照或观测单位被改变')
    if validate_artifacts:
        check_holdout(root)
        check_tasks(root)
    observed = metrics(root)
    if (observed['reference_graphs'] != 768 or observed['complete_graphs'] != 0
            or observed['canonical_mismatches'] != 0 or len(observed['tasks']) != 9
            or len(observed['timing']) != 4
            or sum(r['reduction'] >= .2 for r in observed['timing']) < 3
            or not all(r['memory_gate_met'] for r in observed['timing'])):
        raise ValueError('registered frozen-profile facts changed / 固定研究事实改变')
    return {'record_validation': 'passed', 'maturity': ledger['decision'],
            'validation_scope': ledger['validation_scope'],
            'claims': claims, 'unmet_criteria': gaps, 'metrics': observed}


def render(report: dict, language: str) -> str:
    zh = language == 'zh'
    m = report['metrics']
    rss_increase = (next(r['rss_ratio'] for r in m['timing']
                         if r['repository'] == 'agronholm/anyio') - 1) * 100
    lines = [('# 研究状态与声明验收' if zh else '# Research status and claim acceptance'), '',
             ('**现状：可复现的窄范围工程研究；尚未建立成熟研究结论。**' if zh else
              '**Status: reproducible, narrowly scoped engineering research; mature research is not established.**'), '',
             ('此页由固定原始记录生成。新增状态账本与检查器不算新的实验、科研贡献或独立评审。' if zh else
              'This page is generated from frozen records. A new ledger/checker is not a new experiment, research contribution or independent review.'), '',
             ('通过检查只表示记录和声明状态一致。是否有实质贡献需结合已有工作与独立检视；不把发表或学术首创等同于研究质量。' if zh else
              'Passing verifies record/claim consistency only. Substantive contribution needs comparison with prior work and independent scrutiny; publication or academic firstness is not a substitute for research quality.'), '',
             '| ID | ' + ('声明 | 状态 |' if zh else 'Claim | State |'), '|---|---|---|']
    for c in report['claims']:
        lines.append(f"| {c['id']} | {c['statement_zh' if zh else 'statement_en']} | `{c['state']}` |")
    lines += ['', '## ' + ('已记录的性能结果' if zh else 'Recorded performance results'), '',
              ('四个便利抽样仓库、各8修订和24固定锚点、5计时重复，单台M1 Pro。基线为持久索引+整库相等复用；候选增加读取集合复用。单位为仓库，重复不是独立数据集。' if zh else
               'Four convenience repositories, 8 revisions and 24 fixed anchors each, 5 timing repeats on one M1 Pro. Baseline: persistent indexing plus whole-corpus reuse. Candidate: additional read-set reuse. Repository is the unit; repetitions are not independent datasets.'), '',
              '| Repository | Baseline ms | Candidate ms | Replay reduction |', '|---|---|---|---|']
    for t in m['timing']:
        lines.append(f"| {t['repository']} | {t['baseline_ms']:.2f} | {t['candidate_ms']:.2f} | {t['reduction']:.2%} |")
    lines += ['', (f"完整参考图 {m['complete_graphs']}/{m['reference_graphs']}；回放摘要不一致 {m['canonical_mismatches']}。保留未知状态不产生fresh语义。Anyio RSS增加{rss_increase:.1f}%；内存门槛通过不表示内存下降。" if zh else
                   f"Complete reference graphs: {m['complete_graphs']}/{m['reference_graphs']}; replay digest mismatches: {m['canonical_mismatches']}. Preserving unknowns does not certify fresh semantics. Anyio RSS increased {rss_increase:.1f}%; passing its memory gate does not mean reduced memory."), '',
              '## ' + ('补充：同一9题记录的覆盖代价分析' if zh else 'Supplement: coverage costs on the same nine saved cases'), '',
              ('这是同数据回算，不是新运行或独立留出。3个已知开发仓库、72个子进程；没有LLM运行或人工gold标签。执行密度=覆盖见证行/携带源码行，不是任务相关性precision；源码比例=携带行/语料行。' if zh else
               'This is same-data reanalysis, not a new run or independent holdout. Three known development repositories, 72 children; no LLM run or human gold labels. Execution density = covered witness lines / supplied source lines, not task-relevance precision. Context fraction = supplied lines / corpus lines.'), '',
              '| Case | Graph recall | BM25 recall | Execution density | Context fraction | Supplied lines |', '|---|---|---|---|---|---|']
    for t in m['tasks']:
        lines.append(f"| {t['id']} | {t['graph_recall']:.2%} | {t['bm25_recall']:.2%} | {t['execution_density']:.2%} | {t['context_fraction']:.2%} | {t['graph_lines']} |")
    lines += ['', (f"宏平均：Graph覆盖 {m['macro_graph_recall']:.2%}；BM25覆盖 {m['macro_bm25_recall']:.2%}；执行密度 {m['macro_execution_density']:.2%}；源码比例 {m['macro_context_fraction']:.2%}。" if zh else
                   f"Macro averages: graph recall {m['macro_graph_recall']:.2%}; BM25 recall {m['macro_bm25_recall']:.2%}; execution density {m['macro_execution_density']:.2%}; context fraction {m['macro_context_fraction']:.2%}."), '',
              ('高覆盖可能来自很宽的声明范围。packaging-metadata只覆盖13条执行见证却携带3484行。Pluggy注册案例BM25更好。历史模型任务图、fresh锚点和BM25均24/25；没有证明图带来下游收益。' if zh else
               'High recall may result from broad declaration spans: packaging-metadata covers 13 executed witness lines while supplying 3,484 lines. BM25 wins the Pluggy registration case. Historical model tasks tie at 24/25 for graph, fresh anchors and BM25; graph-specific downstream benefit is unproven.'), '',
              '## ' + ('尚缺的实质证据' if zh else 'Substantive evidence still missing'), '']
    lines += ['- ' + g['zh' if zh else 'en'] for g in report['unmet_criteria']]
    lines += ['', ('下一项优先实验：在许可、源码版本与标签核验完成后，固定预算盲测新仓库的外部任务相关性标签；只用issue正文自动定位，比较强词法检索、普通上下文展开和图展开。失败应保留并收窄主张。此实验尚未运行；即使成功，也不自动证明智能体修复收益。' if zh else
                  'Next priority: after license/source/label verification, compare graph expansion with strong lexical retrieval and ordinary context expansion on unseen repositories with external task-relevance labels, fixed budgets and issue-only automatic localization. Retain failures and narrow claims when needed. This experiment has not run; even success would not establish agent repair benefit.'), '',
              '## ' + ('复核命令与证据' if zh else 'Checks and evidence'), '',
              '```bash', 'python scripts/check_research_claims.py',
              '# Expected exit 2: current evidence does not establish maturity / 当前证据不足，预期退出2',
              'python scripts/check_research_claims.py --require-mature',
              '# Regenerate this page only / 仅重建此页',
              'python scripts/check_research_claims.py --write-docs', '```', '',
              '[Claim ledger / 声明账本](../../research/claims.json) · '
              '[Full study / 完整研究](MATURATION_REPORT.md) · '
              '[Prior work / 相关工作](RELATED_WORK.md)', '',
              '[Holdout raw](../../' + HOLDOUT + ') · [Task raw](../../' + TASK + '/runs.json)', '',
              ('[English](../en/RESEARCH_STATUS.md)' if zh else '[中文](../zh/RESEARCH_STATUS.md)'), '']
    return '\n'.join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-mature', action='store_true',
                        help='fail when substantive evidence is missing / 缺少实质证据时失败')
    parser.add_argument('--write-docs', action='store_true',
                        help='regenerate bilingual status pages / 生成双语状态页')
    args = parser.parse_args(argv)
    try:
        report = validate(ROOT)
        for language in ('en', 'zh'):
            path = ROOT / f'docs/{language}/RESEARCH_STATUS.md'
            expected = render(report, language)
            if args.write_docs:
                path.write_text(expected)
            elif path.read_text() != expected:
                raise ValueError('status page differs from registered evidence: ' + language)
    except (ValueError, KeyError, TypeError, OSError, ZeroDivisionError) as error:
        print(json.dumps({'record_validation': 'failed', 'error': str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if args.require_mature else 0


if __name__ == '__main__':
    raise SystemExit(main())
