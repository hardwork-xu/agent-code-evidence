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
MEASURED_COMMIT = 'a0070ea71cea3c8944c004559602616114011b76'
HISTORICAL_SOURCE_ROOT = 'research/frozen-20261004-source/contextproof'
# Immutable identity of the original implementation_files table, independent of
# rehashed ledger entries. A different measured implementation needs a new profile.
MEASURED_IMPLEMENTATION_SHA256 = '6188045421630dc62251e3216e017b2bcd517616618f5177f43608400fd0a494'
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
            or ledger['measured_commit'] != MEASURED_COMMIT
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
    h, p = read(root, HOLDOUT), read(root, TASK + '/provenance.json')
    measured = h['provenance']['implementation_files']
    table_bytes = json.dumps(measured, sort_keys=True, separators=(',', ':')).encode()
    if hashlib.sha256(table_bytes).hexdigest() != MEASURED_IMPLEMENTATION_SHA256:
        raise ValueError('implementation provenance differs from measured profile')
    historical = ledger.get('historical_sources')
    if historical is not None:
        expected_mapping = {name: HISTORICAL_SOURCE_ROOT + '/' + Path(name).name
                            for name in measured}
        if historical != expected_mapping:
            raise ValueError('historical source mapping differs from measured implementation')
        if {name for name in hashes if name.startswith('src/contextproof/')} != set(measured):
            raise ValueError('historical source hash keys differ from measured implementation')
        for name, archive in historical.items():
            if hashes.get(name) != measured[name] or hashes.get(archive) != measured[name]:
                raise ValueError('historical source/archive hash differs from measured implementation: ' + name)
    required = {HOLDOUT, TASK + '/cases.json', TASK + '/runs.json',
                TASK + '/provenance.json', TASK + '/summary.json',
                'benchmarks/incremental_holdout/protocol.json',
                'benchmarks/incremental_holdout/manifest.json',
                'benchmarks/task_evidence/manifest.json'}
    required.update(p for claim in claims for p in claim['evidence'])
    if historical is None:
        # Backward compatibility: an undeclared archive retains the original
        # requirement that all current runtime files match the old ledger.
        required.update(path.relative_to(root).as_posix() for path in
                        (root / 'src/contextproof').glob('*.py'))
    else:
        required.update(measured)
        required.update(historical.values())
    if not required <= hashes.keys():
        raise ValueError('missing source/evidence hash / 缺失源码或证据哈希')
    for name, expected in hashes.items():
        actual_name = historical.get(name, name) if historical is not None else name
        if hashlib.sha256(safe_path(root, actual_name).read_bytes()).hexdigest() != expected:
            raise ValueError('evidence hash mismatch: ' + name)
    if (h['run_id'] != ledger['holdout']['run_id']
            or p['run_id'] != ledger['tasks']['run_id']
            or h['environment']['source_commit'] != ledger['measured_commit']
            or p['git_head'] != ledger['measured_commit']):
        raise ValueError('run/source identity differs from ledger / 运行或源码身份不符')
    for name, measured_hash in measured.items():
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
    current_sources = {path.relative_to(root).as_posix() for path in
                       (root / 'src/contextproof').glob('*.py')}
    def current_matches(name, expected):
        try:
            return hashlib.sha256(safe_path(root, name).read_bytes()).hexdigest() == expected
        except (OSError, ValueError):
            # Current runtime is outside the historical identity gate; unavailable
            # or redirected current files cannot certify equality with the archive.
            return False
    evolved = current_sources != set(measured) or any(
        not current_matches(name, expected) for name, expected in measured.items())
    return {'record_validation': 'passed', 'maturity': ledger['decision'],
            'validation_scope': ledger['validation_scope'],
            'historical_implementation': {'measured_commit': ledger['measured_commit'],
                                         'source_count': len(measured),
                                         'binding': 'archived_source' if historical is not None else 'current_runtime_legacy',
                                         'archive_root': HISTORICAL_SOURCE_ROOT if historical is not None else None,
                                         'current_runtime_evolved': evolved},
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
    historical = report['historical_implementation']
    if historical['binding'] == 'archived_source':
        evolution_zh = '当前源码已演化；' if historical['current_runtime_evolved'] else '归档没有产生当前运行时的新测量；'
        evolution_en = ('Current source has evolved; ' if historical['current_runtime_evolved'] else
                        'Archiving does not create a new measurement of current runtime; ')
        lines += ['', (f"历史测量固定于提交 `{historical['measured_commit']}` 的{historical['source_count']}份实现源码。"
                       '账本核对[原测量源码归档](../../research/frozen-20261004-source/contextproof)，保留原始源码路径及测量哈希。'
                       + evolution_zh + '下列旧性能数字只适用于归档实现，不证明当前运行时的速度。归档与账本修复没有重跑旧基准。'
                       if zh else
                       f"Historical measurements bind to {historical['source_count']} implementation files at commit `{historical['measured_commit']}`. "
                       'The ledger checks the [archived measured source](../../research/frozen-20261004-source/contextproof) and preserves the original source paths and measured hashes. '
                       + evolution_en + 'The historical performance numbers below apply only to that archived implementation and do not establish current runtime speed. Archiving and repairing the ledger did not rerun the old benchmark.')]
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
    lines += ['', ('尚未完成的下一项验证是：在许可、源码版本与标签核验后，对另行固定的未见任务使用独立语义/必要上下文标签，比较相同预算的强词法检索、普通上下文展开和图展开。这个完整语义/必要上下文验证尚未运行；已经完成的39任务issue-only编辑定位pilot使用补丁代理标签。两者不可混同，即使语义验证成功也不自动证明智能体修复收益。' if zh else
                  'The outstanding validation requires a separately frozen unseen task set with independent semantic/necessary-context labels, reviewed licenses and source pins, and matched-budget lexical retrieval, ordinary context expansion and graph expansion. This full semantic/necessary-context validation has not run. The completed 39-task issue-only edit-localization pilot uses patch-proxy labels; it is a different endpoint. Even successful semantic validation would not by itself establish agent repair benefit.'), '',
              ('已完成工作见[39任务pilot及负面结果](EXTERNAL_PILOT_RESULTS.md)、[原样上游测试资格核验](KNOWN_TASK_EXECUTION.md)和[事后子集敏感性分析](KNOWN_TASK_SENSITIVITY.md)。这些记录保留已见任务的失败，不能建立必要上下文或生成修复收益。另行冻结的[八任务绑定观测](SEMANTIC_OBSERVER.md)现已完成32条件：6/8执行合格、3/8有可计分primitive站点，仅2/8任务接受，主门槛未通过。有限执行前绑定不等于完整语义验证。' if zh else 'Completed work is reported separately in the [39-task pilot and negative results](EXTERNAL_PILOT_RESULTS.md), [unchanged-upstream test qualification](KNOWN_TASK_EXECUTION.md) and [post-hoc subset sensitivity](KNOWN_TASK_SENSITIVITY.md). These records retain known-task failures and do not establish necessary context or generated-repair benefit. The separately frozen [eight-task binding observations](SEMANTIC_OBSERVER.md) now complete 32 conditions: 6/8 execution-qualified, 3/8 with scoreable primitive sites, only 2/8 accepting tasks; the main gate failed. Finite pre-op bindings are a different endpoint from full semantic validation.'), '',
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
