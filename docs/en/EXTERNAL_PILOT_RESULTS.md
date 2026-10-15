# External real-task pilot: negative and mixed results

**Decision: both predeclared advancement gates failed. Mature research remains unestablished.**

The frozen selection has 39 tasks across six unused repositories: 34 produced predictions and 5 failed the32 MiB Python-source cap. All39 are retained: 32 tasks have removed-line targets and seven do not. There are 702 method-budget records, not 702 independent tasks.

Run: `pilot-20261014T081813Z`. Measured source: `2451b574856048f3d9dded1fc1f55f209241cdc2`. Protocol: `aefdf06fc34f7c74434c67640e80128df350260a`.

Environment: Apple M1 Pro,16 GiB,10 CPUs,macOS arm64,Python 3.12.2,one worker. No model/API or upstream source execution. Source load/index/packing wall time is descriptive; no performance superiority claim.

## Primary endpoint:16000 bytes,repository macro means

Failures contribute empty-prediction zero scores when labels exist. Absent targets are undefined, not zero or perfect recall. Precision/recall/F1 below describe patch edits only.

| Method | Line precision | Line recall | Line F1 | Edited-file F1 |
|---|---:|---:|---:|---:|
| bm25_windows | 1.123534% | 18.234442% | 0.816360% | 13.009500% |
| bm25_declarations | 1.274970% | 18.620775% | 1.140966% | 15.829078% |
| anchors_only | 1.085895% | 8.756266% | 1.035492% | 16.761905% |
| graph_expand | 0.965480% | 8.898059% | 0.881158% | 14.029541% |
| window_expand | 1.019999% | 9.350917% | 0.810069% | 16.761905% |
| file_expand | 1.037065% | 12.128694% | 0.843673% | 16.761905% |

| Comparison | Positive repositories | F1 difference (pp) | Recall difference (pp) | Gate |
|---|---:|---:|---:|---|
| graph vs bm25_windows | 2/6 | +0.064799 | -9.336383 | failed |
| graph vs bm25_declarations | 2/6 | -0.259808 | -9.722716 | failed |

The small positive F1 difference against windows is below the predeclared 0.03 absolute gain. Declaration BM25 has higher F1. Recall declines against both; the small positive difference cannot substitute for passing the gate.

| Repository | Selected | Prediction failures | Line-scorable | No line target |
|---|---:|---:|---:|---:|
| Significant-Gravitas/AutoGPT | 1 | 0 | 1 | 0 |
| huggingface/transformers | 10 | 5 | 9 | 1 |
| keras-team/keras | 10 | 0 | 8 | 2 |
| langchain-ai/langchain | 10 | 0 | 8 | 2 |
| tensorflow/models | 2 | 0 | 2 | 0 |
| yt-dlp/yt-dlp | 6 | 0 | 4 | 2 |

## Three budgets and failure sensitivity

| Budget | Method | Line F1 | Line recall |
|---:|---|---:|---:|
| 8000 | bm25_windows | 0.804657% | 10.482226% |
| 16000 | bm25_windows | 0.816360% | 18.234442% |
| 32000 | bm25_windows | 0.718537% | 20.878179% |
| 8000 | bm25_declarations | 1.665541% | 13.931732% |
| 16000 | bm25_declarations | 1.140966% | 18.620775% |
| 32000 | bm25_declarations | 0.725397% | 19.398329% |
| 8000 | anchors_only | 1.053091% | 6.081369% |
| 16000 | anchors_only | 1.035492% | 8.756266% |
| 32000 | anchors_only | 1.123448% | 10.693298% |
| 8000 | graph_expand | 0.995380% | 6.203918% |
| 16000 | graph_expand | 0.881158% | 8.898059% |
| 32000 | graph_expand | 0.926545% | 10.819485% |
| 8000 | window_expand | 0.977264% | 6.602203% |
| 16000 | window_expand | 0.810069% | 9.350917% |
| 32000 | window_expand | 0.828068% | 12.140399% |
| 8000 | file_expand | 0.956427% | 6.602203% |
| 16000 | file_expand | 0.843673% | 12.128694% |
| 32000 | file_expand | 0.800058% | 15.285823% |

Successful-prediction-only statistics below reanalyze the same raw records. They do not replace the all-selected analysis or constitute a new holdout.

| Method (16000 bytes) | Conditional line F1 | Conditional line recall |
|---|---:|---:|
| bm25_windows | 1.175725% | 19.744867% |
| bm25_declarations | 1.419318% | 20.386199% |
| anchors_only | 1.401939% | 11.863303% |
| graph_expand | 1.248724% | 12.008006% |
| window_expand | 1.241316% | 12.504522% |
| file_expand | 1.274921% | 15.282300% |

## Source and separately implemented calculation checks

Within this execution,a separately implemented parser/Fraction calculation recomputed 39 tasks/702 cells without discrepancy; it did not invoke the study scorer/analyzer. Another parser checked 86 Python file sections,1757 removed-line occurrences and 1679 old-side context occurrences against exact-base source. Ten non-Python sections were categorized only; three new files have no old side. Occurrences are not independent samples.

These checks are not external replication,independent human peer review or research maturity. The 612 actual contexts include 30 budget_too_small,492 partial and 90 ready; ready describes candidate delivery,not complete semantic closure. Five resource failures contribute another 90 conservative score records.

## Research decision and limits

Do not advance the broad graph-improves-task-context claim on this pilot. Retain the existing conditional engineering results on versioned evidence,unknown states and selective replay; this single-base study did not test version recovery. The next study should formulate a separate falsifiable question about auditable version changes and cost/abstention tradeoffs,freeze untouched tasks and strong native baselines,and collect semantic or downstream evidence. Tuning on these39 tasks cannot establish a confirmatory study.

Patch edits are not necessary context. Repository samples are imbalanced,each task has one base,and no complete upstream agent task is reproduced. Tests,ranking and packing affect output. Consecutive same-name declarations can yield no_anchor. Original predictions did not retain candidate/anchor sidecars,so output alone cannot prove their identity or explain omitted lines. Agentless,Aider and official SWE-bench retrieval were not run; no superiority claim is made.

## Post-hoc deterministic packing diagnosis

All 72 outputs of four selected cases exactly replayed original hashes,coordinates,bytes and statuses. Common candidate anchors matched. Five delivered-source omissions were traced to 64–68 extra metadata bytes pushing the same source piece beyond budget. This cannot explain the whole recall deficit. It is post-hoc diagnosis of known failures,not a new independent holdout; primary results and gates remain unchanged.

[Diagnostic records / 诊断记录](../../benchmarks/external_context/diagnostics/posthoc-packing-replay-20261014/) · [Interpretation / 解释](../../benchmarks/external_context/results/pilot-20261014T081813Z/postrun-retrieval-interpretation.json)

## Reproduction and raw evidence

[Protocol / 协议](EXTERNAL_PILOT_PROTOCOL.md) · [Prior work / 已有工作](EXTERNAL_RELATED_WORK.md)

[Raw run / 原始运行](../../benchmarks/external_context/results/pilot-20261014T081813Z/manifest.json) · [Scores](../../benchmarks/external_context/results/pilot-20261014T081813Z/scores.json) · [Summary](../../benchmarks/external_context/results/pilot-20261014T081813Z/summary.json) · [Coordinate targets](../../benchmarks/external_context/results/pilot-20261014T081813Z/targets.json)

[Calculation audit](../../benchmarks/external_context/results/pilot-20261014T081813Z/postrun-score-audit.json) · [Label/source audit](../../benchmarks/external_context/results/pilot-20261014T081813Z/postrun-label-source-audit.json)

```bash
PYTHONPATH=src python -m benchmarks.external_context.check
PYTHONPATH=src python -m benchmarks.external_context.report --check
```

[English](../en/EXTERNAL_PILOT_RESULTS.md) · [中文](../zh/EXTERNAL_PILOT_RESULTS.md)
