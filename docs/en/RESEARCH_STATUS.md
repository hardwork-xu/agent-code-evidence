# Research status and claim acceptance

**Status: reproducible, narrowly scoped engineering research; mature research is not established.**

This page is generated from frozen records. A new ledger/checker is not a new experiment, research contribution or independent review.

Passing verifies record/claim consistency only. Substantive contribution needs comparison with prior work and independent scrutiny; publication or academic firstness is not a substitute for research quality.

| ID | Claim | State |
|---|---|---|
| C1-source-identity | Pinned source text and artifact identity are auditable | `supported_artifact_identity` |
| C2-replay-parity | Incremental replay matches uncached bounded resolver on frozen holdout | `supported_frozen_sample` |
| C3-replay-performance | Selective replay reduces measured cost versus persistent indexing plus whole-corpus reuse | `supported_frozen_sample` |
| C4-semantic-freshness | Natural-code semantic freshness can be certified with useful coverage | `not_established_zero_complete_coverage` |
| C5-execution-witness | Graph context covers more executed source on the nine adapted assertion cases in macro average | `supported_development_diagnostic` |
| C6-agent-task-benefit | Graph evidence improves task success or task-relevant context over simpler fresh retrieval | `not_established` |
| C7-novelty | Distinct research contribution beyond established incremental dependency tracking | `scoped_engineering_contribution_only` |
| C8-external-validation | Independent external reproduction or independent human scholarly evaluation occurred | `not_done` |

## Recorded performance results

Four convenience repositories, 8 revisions and 24 fixed anchors each, 5 timing repeats on one M1 Pro. Baseline: persistent indexing plus whole-corpus reuse. Candidate: additional read-set reuse. Repository is the unit; repetitions are not independent datasets.

| Repository | Baseline ms | Candidate ms | Replay reduction |
|---|---|---|---|
| Python-Markdown/markdown | 641.98 | 427.87 | 33.35% |
| agronholm/anyio | 481.03 | 290.42 | 39.63% |
| encode/starlette | 2011.70 | 888.80 | 55.82% |
| pallets/jinja | 1959.32 | 1279.66 | 34.69% |

Complete reference graphs: 0/768; replay digest mismatches: 0. Preserving unknowns does not certify fresh semantics. Anyio RSS increased 2.6%; passing its memory gate does not mean reduced memory.

## Supplement: coverage costs on the same nine saved cases

This is same-data reanalysis, not a new run or independent holdout. Three known development repositories, 72 children; no LLM run or human gold labels. Execution density = covered witness lines / supplied source lines, not task-relevance precision. Context fraction = supplied lines / corpus lines.

| Case | Graph recall | BM25 recall | Execution density | Context fraction | Supplied lines |
|---|---|---|---|---|---|
| packaging-prereleases | 9.84% | 0.00% | 17.65% | 0.60% | 34 |
| packaging-specifier-iterable | 94.52% | 21.92% | 5.85% | 20.86% | 1179 |
| packaging-metadata-keywords | 100.00% | 100.00% | 0.37% | 61.63% | 3484 |
| attrs-makeclass-annotations | 28.71% | 3.56% | 20.26% | 12.97% | 755 |
| attrs-preinit-default | 82.59% | 43.35% | 21.63% | 39.95% | 2326 |
| attrs-init-subclass | 99.75% | 66.25% | 18.74% | 36.56% | 2129 |
| pluggy-set-blocked | 4.17% | 2.08% | 50.00% | 0.24% | 4 |
| pluggy-registration-name | 20.51% | 87.18% | 1.83% | 26.23% | 437 |
| pluggy-call-extra | 45.24% | 12.70% | 33.33% | 10.26% | 171 |

Macro averages: graph recall 53.92%; BM25 recall 37.45%; execution density 18.85%; context fraction 23.26%.

High recall may result from broad declaration spans: packaging-metadata covers 13 executed witness lines while supplying 3,484 lines. BM25 wins the Pluggy registration case. Historical model tasks tie at 24/25 for graph, fresh anchors and BM25; graph-specific downstream benefit is unproven.

## Substantive evidence still missing

- Independent semantic labels and nonzero useful acceptance coverage; current 0/768 complete graphs.
- Untouched task-context labels with fixed budgets and strong lexical/context-expansion controls. Execution witnesses are not relevance gold.
- Actual downstream task outcomes if agent improvement remains a claim. Historical graph and simpler fresh baselines tie 24/25.
- Broader or prospective workloads and independent environment replication; repeated trajectories are not independent datasets.
- A defensible contribution relative to prior work, with independent scrutiny. Publication or academic firstness is not itself required, and this checker cannot judge novelty.

Next priority: after license/source/label verification, compare graph expansion with strong lexical retrieval and ordinary context expansion on unseen repositories with external task-relevance labels, fixed budgets and issue-only automatic localization. Retain failures and narrow claims when needed. This experiment has not run; even success would not establish agent repair benefit.

## Checks and evidence

```bash
python scripts/check_research_claims.py
# Expected exit 2: current evidence does not establish maturity / 当前证据不足，预期退出2
python scripts/check_research_claims.py --require-mature
# Regenerate this page only / 仅重建此页
python scripts/check_research_claims.py --write-docs
```

[Claim ledger / 声明账本](../../research/claims.json) · [Full study / 完整研究](MATURATION_REPORT.md) · [Prior work / 相关工作](RELATED_WORK.md)

[Holdout raw](../../benchmarks/incremental_holdout/results/primary-20261004.json) · [Task raw](../../benchmarks/task_evidence/results/primary-20261004/runs.json)

[中文](../zh/RESEARCH_STATUS.md)
