# 外部真实任务先导实验：负面与混合结果

**结论：预先规定的两个推进门槛均未达到。研究成熟度仍未建立。**

本轮冻结39任务、6个未使用仓库；34项生成预测，5项因32 MiB Python源码总量上限失败。全部39项保留：32项行指标可评分，7项无删除行目标。共有702个方法预算记录，不是702个独立任务。

Run: `pilot-20261014T081813Z`. Measured source: `2451b574856048f3d9dded1fc1f55f209241cdc2`. Protocol: `aefdf06fc34f7c74434c67640e80128df350260a`.

环境：Apple M1 Pro、16 GiB、10 CPU、macOS arm64，Python 3.12.2，单工作进程。无需模型或API；未执行上游源码。源码载入、索引和打包时间只作描述，不作性能优势结论。

## 主要终点：16000字节，按仓库宏平均

失败在有标签时计空预测零分；无目标不编造零分或完美召回。以下精度、召回和F1均为补丁编辑代理指标。

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

窗口基线对照出现微小F1正差，但低于预设0.03绝对增益；声明基线更高。两对照召回都退化，不能用微小正差掩盖门槛失败。

| Repository | Selected | Prediction failures | Line-scorable | No line target |
|---|---:|---:|---:|---:|
| Significant-Gravitas/AutoGPT | 1 | 0 | 1 | 0 |
| huggingface/transformers | 10 | 5 | 9 | 1 |
| keras-team/keras | 10 | 0 | 8 | 2 |
| langchain-ai/langchain | 10 | 0 | 8 | 2 |
| tensorflow/models | 2 | 0 | 2 | 0 |
| yt-dlp/yt-dlp | 6 | 0 | 4 | 2 |

## 三档预算与失败敏感性

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

下面仅成功预测条件下的统计使用同一原始结果，不能替代上面的全部样本分析，也不是新留出实验。

| Method (16000 bytes) | Conditional line F1 | Conditional line recall |
|---|---:|---:|
| bm25_windows | 1.175725% | 19.744867% |
| bm25_declarations | 1.419318% | 20.386199% |
| anchors_only | 1.401939% | 11.863303% |
| graph_expand | 1.248724% | 12.008006% |
| window_expand | 1.241316% | 12.504522% |
| file_expand | 1.274921% | 15.282300% |

## 来源与独立计算核对

本执行内部的独立解析器与Fraction计算重算39项/702格，无差异；没有调用研究scorer/analyzer。另对86个Python文件块核对1757删除行和1679旧侧上下文行出现次数，全部匹配固定base源码；10个非Python块仅分类，3个新文件没有旧侧。重复出现次数不是独立样本。

这些检查不是外部复现、独立人类同行评议或科研成熟证明。612个实际上下文含30个budget_too_small、492个partial及90个ready；ready仅指候选交付，不能当完整语义闭包。5个资源失败另贡献90个保守评分记录。

## 研究决策与边界

停止基于此pilot推进“图扩展提升任务上下文”的宽泛声明。保留既有版本证据、未知状态和选择性回放的条件性工程结果；这个单base实验没有检验跨版本恢复。下一研究应针对可审计版本变化与成本/拒判权衡提出独立可证伪问题，先冻结新任务与强原生基线，再收集语义或下游证据。不能在39项上调参后称确认研究。

补丁编辑不是必要上下文；仓库样本数不均衡、每项只有单base、数据与上游实现并未完整复现agent任务。包含测试、声明排名及预算打包均影响结果。连续同名声明可能产生no_anchor；初次原始记录未保存候选/锚点侧车，不能只凭原始输出推断候选身份或缺行原因。没有运行Agentless、Aider或官方SWE-bench检索，对它们不作性能/质量优越声明。

## 后验确定性打包诊断

4个任务的72个输出逐一精确复现原始hash、坐标、字节和状态。共同候选锚点一致；5处交付缺行已确认由64–68字节额外元数据使同一源码段超预算、整段拒绝。该机制不能解释全部召回劣势；这是针对已知失败的后验诊断，不是独立留出实验，原始结果与推进结论保持不变。

[Diagnostic records / 诊断记录](../../benchmarks/external_context/diagnostics/posthoc-packing-replay-20261014/) · [Interpretation / 解释](../../benchmarks/external_context/results/pilot-20261014T081813Z/postrun-retrieval-interpretation.json)

## 复现与原始证据

[Protocol / 协议](EXTERNAL_PILOT_PROTOCOL.md) · [Prior work / 已有工作](EXTERNAL_RELATED_WORK.md)

[Raw run / 原始运行](../../benchmarks/external_context/results/pilot-20261014T081813Z/manifest.json) · [Scores](../../benchmarks/external_context/results/pilot-20261014T081813Z/scores.json) · [Summary](../../benchmarks/external_context/results/pilot-20261014T081813Z/summary.json) · [Coordinate targets](../../benchmarks/external_context/results/pilot-20261014T081813Z/targets.json)

[Calculation audit](../../benchmarks/external_context/results/pilot-20261014T081813Z/postrun-score-audit.json) · [Label/source audit](../../benchmarks/external_context/results/pilot-20261014T081813Z/postrun-label-source-audit.json)

```bash
PYTHONPATH=src python -m benchmarks.external_context.check
PYTHONPATH=src python -m benchmarks.external_context.report --check
```

[English](../en/EXTERNAL_PILOT_RESULTS.md) · [中文](../zh/EXTERNAL_PILOT_RESULTS.md)
