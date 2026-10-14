"""Bilingual tables from retained records / 从保留记录生成双语表。"""
from __future__ import annotations

import argparse
import json
from statistics import mean

from .check import RUN, validate
from .runner import ROOT


def render(zh=False):
    summary = json.loads((RUN / 'summary.json').read_bytes())
    manifest = json.loads((RUN / 'manifest.json').read_bytes())
    counts = summary['prediction_statuses']
    rows = ['# ' + ('外部真实任务先导实验：负面与混合结果' if zh else 'External real-task pilot: negative and mixed results'), '',
        ('**结论：预先规定的两个推进门槛均未达到。研究成熟度仍未建立。**' if zh else
         '**Decision: both predeclared advancement gates failed. Mature research remains unestablished.**'), '',
        (f'本轮冻结39任务、6个未使用仓库；{counts["predicted"]}项生成预测，{counts["failed"]}项因32 MiB Python源码总量上限失败。全部39项保留：32项行指标可评分，7项无删除行目标。共有702个方法预算记录，不是702个独立任务。' if zh else
         f'The frozen selection has 39 tasks across six unused repositories: {counts["predicted"]} produced predictions and {counts["failed"]} failed the32 MiB Python-source cap. All39 are retained: 32 tasks have removed-line targets and seven do not. There are 702 method-budget records, not 702 independent tasks.'), '',
        f'Run: `{RUN.name}`. Measured source: `{manifest["provenance"]["git_commit"]}`. Protocol: `aefdf06fc34f7c74434c67640e80128df350260a`.', '',
        ('环境：Apple M1 Pro、16 GiB、10 CPU、macOS arm64，Python '+manifest['provenance']['python']+'，单工作进程。无需模型或API；未执行上游源码。源码载入、索引和打包时间只作描述，不作性能优势结论。' if zh else
         'Environment: Apple M1 Pro,16 GiB,10 CPUs,macOS arm64,Python '+manifest['provenance']['python']+',one worker. No model/API or upstream source execution. Source load/index/packing wall time is descriptive; no performance superiority claim.'), '',
        '## ' + ('主要终点：16000字节，按仓库宏平均' if zh else 'Primary endpoint:16000 bytes,repository macro means'), '',
        ('失败在有标签时计空预测零分；无目标不编造零分或完美召回。以下精度、召回和F1均为补丁编辑代理指标。' if zh else
         'Failures contribute empty-prediction zero scores when labels exist. Absent targets are undefined, not zero or perfect recall. Precision/recall/F1 below describe patch edits only.'), '',
        '| Method | Line precision | Line recall | Line F1 | Edited-file F1 |', '|---|---:|---:|---:|---:|']
    for cell in summary['macro']:
        if cell['budget'] == 16000:
            rows.append(f'| {cell["method"]} | {cell["line"]["precision"]:.6%} | {cell["line"]["recall"]:.6%} | {cell["line"]["f1"]:.6%} | {cell["file"]["f1"]:.6%} |')
    rows += ['', '| Comparison | Positive repositories | F1 difference (pp) | Recall difference (pp) | Gate |', '|---|---:|---:|---:|---|']
    for cell in summary['primary_comparisons']:
        rows.append(f'| graph vs {cell["baseline"]} | {cell["positive_repos"]}/6 | {100*cell["macro_f1_difference"]:+.6f} | {100*cell["macro_recall_difference"]:+.6f} | failed |')
    rows += ['', ('窗口基线对照出现微小F1正差，但低于预设0.03绝对增益；声明基线更高。两对照召回都退化，不能用微小正差掩盖门槛失败。' if zh else
                  'The small positive F1 difference against windows is below the predeclared 0.03 absolute gain. Declaration BM25 has higher F1. Recall declines against both; the small positive difference cannot substitute for passing the gate.'), '',
        '| Repository | Selected | Prediction failures | Line-scorable | No line target |', '|---|---:|---:|---:|---:|']
    for cell in summary['per_repo']:
        if cell['budget'] == 16000 and cell['method'] == 'graph_expand':
            rows.append(f'| {cell["repo"]} | {cell["selected"]} | {cell["prediction_failures"]} | {cell["line"]["scorable"]} | {cell["line"]["no_target"]} |')
    rows += ['', '## ' + ('三档预算与失败敏感性' if zh else 'Three budgets and failure sensitivity'), '', '| Budget | Method | Line F1 | Line recall |', '|---:|---|---:|---:|']
    for cell in summary['macro']:
        rows.append(f'| {cell["budget"]} | {cell["method"]} | {cell["line"]["f1"]:.6%} | {cell["line"]["recall"]:.6%} |')
    rows += ['', ('下面仅成功预测条件下的统计使用同一原始结果，不能替代上面的全部样本分析，也不是新留出实验。' if zh else
                  'Successful-prediction-only statistics below reanalyze the same raw records. They do not replace the all-selected analysis or constitute a new holdout.'), '',
             '| Method (16000 bytes) | Conditional line F1 | Conditional line recall |', '|---|---:|---:|']
    for method in ('bm25_windows', 'bm25_declarations', 'anchors_only', 'graph_expand', 'window_expand', 'file_expand'):
        cells = [c['line']['successful_prediction_only'] for c in summary['per_repo']
                 if c['method'] == method and c['budget'] == 16000]
        rows.append(f'| {method} | {mean(c["f1"] for c in cells):.6%} | {mean(c["recall"] for c in cells):.6%} |')
    rows += ['', '## ' + ('来源与独立计算核对' if zh else 'Source and separately implemented calculation checks'), '',
        ('本执行内部的独立解析器与Fraction计算重算39项/702格，无差异；没有调用研究scorer/analyzer。另对86个Python文件块核对1757删除行和1679旧侧上下文行出现次数，全部匹配固定base源码；10个非Python块仅分类，3个新文件没有旧侧。重复出现次数不是独立样本。' if zh else
         'Within this execution,a separately implemented parser/Fraction calculation recomputed 39 tasks/702 cells without discrepancy; it did not invoke the study scorer/analyzer. Another parser checked 86 Python file sections,1757 removed-line occurrences and 1679 old-side context occurrences against exact-base source. Ten non-Python sections were categorized only; three new files have no old side. Occurrences are not independent samples.'), '',
        ('这些检查不是外部复现、独立人类同行评议或科研成熟证明。612个实际上下文含30个budget_too_small、492个partial及90个ready；ready仅指候选交付，不能当完整语义闭包。5个资源失败另贡献90个保守评分记录。' if zh else
         'These checks are not external replication,independent human peer review or research maturity. The 612 actual contexts include 30 budget_too_small,492 partial and 90 ready; ready describes candidate delivery,not complete semantic closure. Five resource failures contribute another 90 conservative score records.'), '',
        '## ' + ('研究决策与边界' if zh else 'Research decision and limits'), '',
        ('停止基于此pilot推进“图扩展提升任务上下文”的宽泛声明。保留既有版本证据、未知状态和选择性回放的条件性工程结果；这个单base实验没有检验跨版本恢复。下一研究应针对可审计版本变化与成本/拒判权衡提出独立可证伪问题，先冻结新任务与强原生基线，再收集语义或下游证据。不能在39项上调参后称确认研究。' if zh else
         'Do not advance the broad graph-improves-task-context claim on this pilot. Retain the existing conditional engineering results on versioned evidence,unknown states and selective replay; this single-base study did not test version recovery. The next study should formulate a separate falsifiable question about auditable version changes and cost/abstention tradeoffs,freeze untouched tasks and strong native baselines,and collect semantic or downstream evidence. Tuning on these39 tasks cannot establish a confirmatory study.'), '',
        ('补丁编辑不是必要上下文；仓库样本数不均衡、每项只有单base、数据与上游实现并未完整复现agent任务。包含测试、声明排名及预算打包均影响结果。连续同名声明可能产生no_anchor；初次原始记录未保存候选/锚点侧车，不能只凭原始输出推断候选身份或缺行原因。没有运行Agentless、Aider或官方SWE-bench检索，对它们不作性能/质量优越声明。' if zh else
         'Patch edits are not necessary context. Repository samples are imbalanced,each task has one base,and no complete upstream agent task is reproduced. Tests,ranking and packing affect output. Consecutive same-name declarations can yield no_anchor. Original predictions did not retain candidate/anchor sidecars,so output alone cannot prove their identity or explain omitted lines. Agentless,Aider and official SWE-bench retrieval were not run; no superiority claim is made.'), '',
        '## ' + ('后验确定性打包诊断' if zh else 'Post-hoc deterministic packing diagnosis'), '',
        ('4个任务的72个输出逐一精确复现原始hash、坐标、字节和状态。共同候选锚点一致；5处交付缺行已确认由64–68字节额外元数据使同一源码段超预算、整段拒绝。该机制不能解释全部召回劣势；这是针对已知失败的后验诊断，不是独立留出实验，原始结果与推进结论保持不变。' if zh else
         'All 72 outputs of four selected cases exactly replayed original hashes,coordinates,bytes and statuses. Common candidate anchors matched. Five delivered-source omissions were traced to 64–68 extra metadata bytes pushing the same source piece beyond budget. This cannot explain the whole recall deficit. It is post-hoc diagnosis of known failures,not a new independent holdout; primary results and gates remain unchanged.'), '',
        '[Diagnostic records / 诊断记录](../../benchmarks/external_context/diagnostics/posthoc-packing-replay-20261014/) · [Interpretation / 解释](../../benchmarks/external_context/results/'+RUN.name+'/postrun-retrieval-interpretation.json)', '',
        '## ' + ('复现与原始证据' if zh else 'Reproduction and raw evidence'), '',
        '[Protocol / 协议](EXTERNAL_PILOT_PROTOCOL.md) · [Prior work / 已有工作](EXTERNAL_RELATED_WORK.md)', '',
        '[Raw run / 原始运行](../../benchmarks/external_context/results/'+RUN.name+'/manifest.json) · [Scores](../../benchmarks/external_context/results/'+RUN.name+'/scores.json) · [Summary](../../benchmarks/external_context/results/'+RUN.name+'/summary.json) · [Coordinate targets](../../benchmarks/external_context/results/'+RUN.name+'/targets.json)', '',
        '[Calculation audit](../../benchmarks/external_context/results/'+RUN.name+'/postrun-score-audit.json) · [Label/source audit](../../benchmarks/external_context/results/'+RUN.name+'/postrun-label-source-audit.json)', '',
        '```bash', 'PYTHONPATH=src python -m benchmarks.external_context.check', 'PYTHONPATH=src python -m benchmarks.external_context.report --check', '```', '',
        '[English](../en/EXTERNAL_PILOT_RESULTS.md) · [中文](../zh/EXTERNAL_PILOT_RESULTS.md)', '']
    return '\n'.join(rows)


def main():
    parser = argparse.ArgumentParser(description='Generate pilot report / 生成试验报告')
    parser.add_argument('--check', action='store_true', help='Verify current tables / 核验现有表')
    args = parser.parse_args()
    validate()
    for language in ('en', 'zh'):
        path = ROOT / 'docs' / language / 'EXTERNAL_PILOT_RESULTS.md'
        value = render(language == 'zh')
        if args.check:
            if path.read_text() != value:
                raise ValueError('report differs from retained records')
        else:
            path.write_text(value)


if __name__ == '__main__':
    main()
