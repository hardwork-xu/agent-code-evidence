# Exploratory ablation: preserving unknown cached graphs

This experiment was designed **after** the complete-only primary method
reused zero natural graphs. It uses the same frozen data and is not a holdout or
confirmation of the failed primary hypothesis. Only the completeness gate is
removed. Source-read and catalog checks, output provenance and all unknown,
missing or truncated statuses remain. Three baselines were rerun contemporaneously,
with one warmup and five complete trajectory repetitions per method.

The candidate reused **364/480** natural anchor transitions per repetition.
All sampled graphs remain incomplete. These are saved computations, not newly
certified fresh evidence. Canonical graph outputs match the rebuilt baseline.
Values below are medians in ms; positive percentage is faster, negative is slower.

## All transitions

| Repository | Rebuild ms | Whole-corpus ms | Any-status ms | vs rebuild | vs whole corpus |
|---|---:|---:|---:|---:|---:|
| PyCQA/pyflakes | 5462.68 | 5470.93 | 5130.30 | +6.1% | +6.2% |
| Textualize/rich | 10261.46 | 6565.84 | 1115.28 | +89.1% | +83.0% |
| more-itertools/more-itertools | 647.73 | 645.71 | 524.19 | +19.1% | +18.8% |
| python-humanize/humanize | 393.32 | 269.34 | 190.30 | +51.6% | +29.3% |

## Source-changing transitions only

| Repository | Rebuild ms | Whole-corpus ms | Any-status ms | vs rebuild | vs whole corpus |
|---|---:|---:|---:|---:|---:|
| PyCQA/pyflakes | 5462.68 | 5470.93 | 5130.30 | +6.1% | +6.2% |
| Textualize/rich | 6168.40 | 6156.81 | 652.75 | +89.4% | +89.4% |
| more-itertools/more-itertools | 647.73 | 645.71 | 524.19 | +19.1% | +18.8% |
| python-humanize/humanize | 237.84 | 236.80 | 158.74 | +33.3% | +33.0% |

## Initial capture plus complete replay

| Repository | Rebuild capture + replay ms | Whole corpus ms | Any status ms |
|---|---:|---:|---:|
| Textualize/rich | 12428.00 | 8752.27 | 3291.36 |
| python-humanize/humanize | 474.31 | 350.50 | 270.93 |
| more-itertools/more-itertools | 783.96 | 783.32 | 664.26 |
| PyCQA/pyflakes | 6550.06 | 6557.47 | 6223.23 |

This is a same-data exploratory mechanism ablation. It does not establish
out-of-sample performance, complete dependency registration in general Python,
semantic safety, task relevance, coding-agent improvement or new memoization theory.
A per-module incremental binding-summary baseline and retained-memory/RSS costs
are unmeasured. Source hashing still touches all supplied text, and read/catalog
invalidation remains coarse. Initial capture is included in the last table, but
process startup and session construction are not. The unchanged primary report
retains its original zero-coverage result and failed utility target.


- run_id: `ablation-20261004T200446Z`
- source commit: `67701873e42b6fbb79d60757ebc83cd1125de104`
- protocol SHA256: `a34c033ff773fcf9673ff60d21426fb9854073844110a6fad2f7e14911af58e7`
- [Raw / 原始数据](../../benchmarks/selective_reuse/results/ablation-20261004.json)
- [Protocol / 协议](../../benchmarks/selective_reuse/ablation-protocol.json)
- [Primary report / 主报告](RESEARCH_REPORT.md)

```bash
python scripts/run_selective_ablation.py --output work/NEW_ABLATION.json
python scripts/render_ablation_report.py work/NEW_ABLATION.json
```

Python 3.12.2; Apple M1 Pro; one benchmark thread.
