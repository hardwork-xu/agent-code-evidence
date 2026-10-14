# 研究状态与声明验收

**现状：可复现的窄范围工程研究；尚未建立成熟研究结论。**

此页由固定原始记录生成。新增状态账本与检查器不算新的实验、科研贡献或独立评审。

通过检查只表示记录和声明状态一致。是否有实质贡献需结合已有工作与独立检视；不把发表或学术首创等同于研究质量。

| ID | 声明 | 状态 |
|---|---|---|
| C1-source-identity | 固定源码与产物身份可核查 | `supported_artifact_identity` |
| C2-replay-parity | 固定留出样本中的有界解析器回放一致 | `supported_frozen_sample` |
| C3-replay-performance | 强基线下固定样本回放耗时下降 | `supported_frozen_sample` |
| C4-semantic-freshness | 有用的自然代码语义fresh证书 | `not_established_zero_complete_coverage` |
| C5-execution-witness | 九个开发样本中的执行见证覆盖 | `supported_development_diagnostic` |
| C6-agent-task-benefit | 独立任务上下文质量及智能体收益 | `not_established` |
| C7-novelty | 超出已有增量依赖原理的研究新颖性 | `scoped_engineering_contribution_only` |
| C8-external-validation | 独立外部复现与人工学术评议 | `not_done` |

## 已记录的性能结果

四个便利抽样仓库、各8修订和24固定锚点、5计时重复，单台M1 Pro。基线为持久索引+整库相等复用；候选增加读取集合复用。单位为仓库，重复不是独立数据集。

| Repository | Baseline ms | Candidate ms | Replay reduction |
|---|---|---|---|
| Python-Markdown/markdown | 641.98 | 427.87 | 33.35% |
| agronholm/anyio | 481.03 | 290.42 | 39.63% |
| encode/starlette | 2011.70 | 888.80 | 55.82% |
| pallets/jinja | 1959.32 | 1279.66 | 34.69% |

完整参考图 0/768；回放摘要不一致 0。保留未知状态不产生fresh语义。Anyio RSS增加2.6%；内存门槛通过不表示内存下降。

## 补充：同一9题记录的覆盖代价分析

这是同数据回算，不是新运行或独立留出。3个已知开发仓库、72个子进程；没有LLM运行或人工gold标签。执行密度=覆盖见证行/携带源码行，不是任务相关性precision；源码比例=携带行/语料行。

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

宏平均：Graph覆盖 53.92%；BM25覆盖 37.45%；执行密度 18.85%；源码比例 23.26%。

高覆盖可能来自很宽的声明范围。packaging-metadata只覆盖13条执行见证却携带3484行。Pluggy注册案例BM25更好。历史模型任务图、fresh锚点和BM25均24/25；没有证明图带来下游收益。

## 尚缺的实质证据

- 独立语义标签和非零有效接受覆盖；当前完整图0/768。
- 未使用任务的独立上下文标签、固定预算和强词法/普通展开对照。执行见证不是相关性gold。
- 若声称智能体收益，需要真实下游任务结果；历史图与简单fresh基线均24/25。
- 更广泛或前瞻工作负载及独立环境复现；重复轨迹不是独立数据集。
- 相对已有工作的可辩护贡献及独立检视；不把发表或学术首创本身作为必要条件，检查器不能判定新颖性。

下一项优先实验：在许可、源码版本与标签核验完成后，固定预算盲测新仓库的外部任务相关性标签；只用issue正文自动定位，比较强词法检索、普通上下文展开和图展开。失败应保留并收窄主张。此实验尚未运行；即使成功，也不自动证明智能体修复收益。

另见39任务编辑定位先导实验：[实测及负面结果](EXTERNAL_PILOT_RESULTS.md)。它使用补丁代理标签，不能填补专家必要上下文或下游收益证据。

## 复核命令与证据

```bash
python scripts/check_research_claims.py
# Expected exit 2: current evidence does not establish maturity / 当前证据不足，预期退出2
python scripts/check_research_claims.py --require-mature
# Regenerate this page only / 仅重建此页
python scripts/check_research_claims.py --write-docs
```

[Claim ledger / 声明账本](../../research/claims.json) · [Full study / 完整研究](MATURATION_REPORT.md) · [Prior work / 相关工作](RELATED_WORK.md)

[Holdout raw](../../benchmarks/incremental_holdout/results/primary-20261004.json) · [Task raw](../../benchmarks/task_evidence/results/primary-20261004/runs.json)

[English](../en/RESEARCH_STATUS.md)
