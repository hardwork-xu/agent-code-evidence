# 智能体代码证据校验 · Agent Code Evidence

仓库原名 `contextproof`；Python 包名与命令仍为 `contextproof`。

[English](README.md) · [图接口与契约](docs/GRAPH.md) ·
[实测报告](docs/GRAPH_REPORT.md) · [模型实验协议](docs/REVISION_STUDY_PROTOCOL.md)

代码库修改后，编程助手保存的调用者可能一字未变，但它依赖的函数已经变了。
ContextProof 保存源码及其支持解析的 Python 依赖，指出哪条依赖路径发生变化，
并把当前代码放进有明确字节预算的模型输入。

图工作流包含 Git 不可变版本读取、有限深度的依赖图、精确可重建的差量、
本地保存的证据句柄，以及 CLI 和 MCP 接口。动态调用、外部引用、同名歧义、
缺失源码和预算不足都会显式保留。默认工具只依赖 Python 标准库，支持
Python 3.11+、macOS/Linux；日常使用不需要模型、GPU 或 API Key。

## 独立绑定观测（2026-10-15）

[冻结八任务实验](docs/zh/SEMANTIC_OBSERVER.md)的32条件已全部闭合：保留原21条件，
在相同协议和封存预测下续跑11条件。当前源码重建、整库相等复用、读取集复用在八任务上平局。
**6/8任务具执行资格，3/8有可计分primitive站点**；28个接受的站点×源码角色观测一致，
却仅来自2/8任务，预设有限效用主门槛未通过。零接受的准确率未定义。

[自动生成双语表](benchmarks/semantic_observer/results/prospective8-20261015/REPORT_zh.md)与
[输入重建](benchmarks/semantic_observer/inputs/prospective8-20261015/REPRODUCING.md)保留不支持值、
零观测、子测试资格失败和完整成本。这些执行前绑定假设不证明完整语义、必要上下文、
智能体修复收益或成熟研究。

## 外部真实任务先导实验（2026-10-14）

[冻结的仅问题描述研究](docs/zh/EXTERNAL_PILOT_RESULTS.md) 完整尝试了六个未使用仓库的
**39个真实任务**：34项生成预测，5项触发32 MiB Python源码总量上限。全部任务和失败
保留；7项没有删除行目标，其行指标记为未知而非编造零分或完美召回。

两个预设推进门槛均未达到。16000 UTF-8字节下，图扩展按仓库宏平均的删除行F1为
0.881158%，召回为8.898059%；声明BM25分别为1.140966%和18.620775%。这些指标只对应
参考补丁编辑，不证明必要上下文或智能体修复成功。[原始结果、来源核验与限制](docs/zh/EXTERNAL_PILOT_RESULTS.md) 保留负面和混合pilot，不声称成熟或优于未运行的外部工具。

[协议与命令](docs/zh/EXTERNAL_PILOT_PROTOCOL.md) · [已有工作边界](docs/zh/EXTERNAL_RELATED_WORK.md)

[原样上游测试的后续执行](docs/zh/KNOWN_TASK_EXECUTION.md)保留相同39个已见任务及
所有早期失败条件。[自动生成状态表](docs/zh/KNOWN_TASK_EXECUTION_RESULTS.md)区分
固定标签实际通过、崩溃、跳过和缺失调用。最终保留51完整条件和1闭合不完整条件：
**30/39固定标签有限合格，9项仍未合格**。源码角色准备与公开观测检查器可独立
运行；检查记录不等同重跑上游测试。gold为已有参考修复，不是自主生成修复；
本阶段不改变pilot的失败门槛，也不证明研究成熟度。

[事后敏感性分析](docs/zh/KNOWN_TASK_SENSITIVITY.md)单列执行有限合格子集。
16000字节下，其F1相对声明BM25的排序翻转，召回仍低于两种BM25基线。
原all39主样本和全部负面结果保持不变。

## 显式全局绑定可靠性（2026-10-14）

[解析器 4](docs/zh/FUNCTION_GLOBAL_BINDINGS.md)将可能的延迟函数 global 写入保留为未知，
不再选择模块初始字面量。32 个受控夹具中，20 个可能写入绑定从 resolved 改为 unresolved，
12 个无写入控制保持支持；其中一个不可达写入体现保守代价。**自然面板没有新增观察绑定
收益**：十个锚点闭包仍全部未知，三个 Pyparsing 键原本就 unresolved。四个上游修复提供
43 个断言，不是 43 个修复任务；这些执行预检不能衡量候选收益。

[设计、命令与限制](docs/zh/FUNCTION_GLOBAL_BINDINGS.md) ·
[配对开发结果](benchmarks/global_bindings/results/development-20261014/REPORT_zh.md)
两次协议修订与首轮基线均保留，最后修订发生在已观察基线之后。这是开发证据，不是 blind
评估、性能提升或成熟研究。

## 运行三跳依赖演示

```sh
git clone https://github.com/hardwork-xu/agent-code-evidence.git
cd agent-code-evidence
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python scripts/demo_graph.py
```

用浏览器打开 `docs/assets/graph-demo.html`。这是明确标注的合成演示：脚本
创建真实 Git 提交，把第三跳依赖从 `0.05` 改成 `0.20`，调用实际实现，
检查新源码是否进入模型正文、差量能否精确恢复完整图，以及不相关改动、
无法解析的引用和极小预算分别如何处理。示例源码不会被执行。

## 用在自己的仓库中

把下面三个大写占位符替换为真实仓库路径与提交：

```sh
contextproof graph-capture REPOSITORY "invoice_total" \
  --ref BEFORE_COMMIT --budget 16000 \
  --output work/before.json --payload work/before-context.json

contextproof graph-refresh REPOSITORY work/before.json \
  --ref AFTER_COMMIT --view full --budget 16000 \
  --output work/after.json --payload work/current-context.json \
  --delta work/change.json

contextproof graph-apply work/before.json work/change.json \
  --output work/reconstructed.json
```

`--view full` 给出当前源码；`--view update` 用于客户端保留了指定旧图的场景，
不能把增量正文当作独立的完整上下文。**预算统计 `--payload` 文件中的全部
UTF-8 字节**，包含代码、引用和摘要诊断；完整图、CLI 回执、模型会话封装与
工具定义另算。退出码 `1` 表示覆盖不完整，`2` 表示输入或操作错误。

不指定 `--ref` 时会读取并计算工作树文件哈希，但不承诺多个文件的原子快照。
Git 版本读取只使用本地对象，不联网补取缺失对象，也不执行仓库代码。

## 四个需要区分的结果

| 结果 | 实际含义 | 边界 |
|---|---|---|
| 源码指纹相同 | 记录的源码身份与文本相同 | 不证明行为相同，也不是作者签名 |
| 静态依赖未变 | 在声明范围内的定义、导入绑定和路径未变 | unresolved 或达到限制时不能报告新鲜 |
| 模型正文完整 | 所需源码及范围内信息都装入了预算 | 不保证足以完成任务 |
| 差量精确恢复 | 对指定旧图应用差量后，结果与目标图一致 | 文件体积减少不等于模型 token 或费用减少 |

默认扩展深度为 4，最多 256 个节点。完整函数或类放不下时会明确报告省略，
不会从中间截断代码。模型侧诊断使用有计数和截断标记的摘要，完整证据保留
在本地。节点身份与源码指纹分开，因此只移动行号时可以只更新引用位置。

MCP 服务在请求之间复用内存 AST，同时重新检查源码和解析目录。落盘 AST
方案在公平对照中出现额外开销，因此改为显式可选，不宣传未经证实的加速。

## MCP 与旧接口

按 [examples/mcp.json](examples/mcp.json) 配置固定源码根目录。
`contextproof serve ROOT` 提供 10 个工具；新增的
`contextproof_graph_capture` 保存完整图并返回有预算的源码与句柄，
`contextproof_graph_refresh` 用句柄刷新到当前版本。

原有 `bundle/verify/repair` 仍用于精确片段校验和迁移；v1 的
`capture/check/refresh` 仍保留直接依赖诊断。但旧接口的源码正文不保证包含
发生变化的依赖代码，模型需要这些代码时应使用图工作流。旧实验不会因新接口
上线而被改写成正结果。

## 实验记录

[图重放研究](benchmarks/graph/README.md)检查重建一致性、传递依赖观察、
正文覆盖与缓存代价。最初诊断元数据挤占代码预算的失败、落盘缓存更慢的
结果，以及词法作用域审查发现的错误，都保留为带版本的记录。

[真实版本行为研究](docs/REVISION_STUDY_PROTOCOL.md)使用四个开源库的 30 个
上游回归测试衍生任务，其中 5 个开发任务、25 个留出任务。所有方法共享
源码定位提示和 16,000 字节证据预算，对照包括无源码、旧源码、新源码、
BM25、传递图和真实运行的 Archex 0.31.2。最终运行配置先通过了 5/5 开发
任务能力检查，再开始留出实验；协议与输入已提前提交到公开仓库。
这是带源码提示的 API 输出预测，不是完整软件问题修复或通用 agent 排名。

首次冻结的 150 次对照中，旧源码组 **8/25**；图上下文、直接提供当前源码、
BM25 都是 **24/25**；Archex 为 **21/25**。图方案与相同定位提示下的简化
基线打平，而且使用了更多输入 token。因此项目聚焦于版本证据与可核验刷新，
没有把这个结果宣传成检索方法更强。修正版另跑的 25 次结果仍为 24/25，
逐题答案与首轮一致，两轮记录均保留。完整配对结果和修正版记录见[实测报告](docs/GRAPH_REPORT.md)。

![首轮六组对照与修正版图上下文结果](docs/assets/revision-results.svg)

历史材料继续保留：[300 条精确文本漂移样本](docs/DRIFT_STUDY.md)、
[34 项直接依赖控制案例](docs/DEPENDENCIES.md)，以及
[三组均为 0/20 的 60 次 Qwen 生成](docs/DOWNSTREAM.md)。同一仓库、版本对和实现区域内的
任务存在相关性；测试数量、源码校验一致性和差量体积不能替代模型效果证据。

## 复现与发布

```sh
python -m pip install -e '.[dev]'
ruff check .
pytest -q tests benchmarks/graph/test_scope_audit.py benchmarks/revision_baselines/test_baselines.py
python scripts/check_publication.py
python -m build
```

安装 `.[integration]` 后可运行 `python scripts/check_mcp_sdk.py`，通过官方
MCP SDK 验证实际 stdio 调用。模型推理不在 CI 中自动运行。

公开仓库保留技术实现、实验输入、脱敏后的答案、失败记录和原始/公开文件哈希。
个人规划、账号信息、原始本机日志与完整备份保存在 Git 仓库之外。
[发布政策](docs/PUBLISHING.md)说明脱敏规则；脱敏不会改变实验分数或隐藏失败。

项目由 **hardwork-xu** 维护，使用 AI 辅助设计、实现、实验与写作。
采用 [MIT 许可证](LICENSE)，上游来源与许可证保留在各实验 manifest 中。

## 目录依赖实验（2026-10-14）

[新增类型化目录守卫](docs/zh/CATALOG_RESULTS.md)追踪正/负模块查询，并保留读取源码哈希及全部
未知前沿。四个真实仓库提供64个八转移批次与全部23个目录变化事件对。相对完整查询根守卫，
预设20%回放成本目标仅 **0/4** 库达成，整体失败；实测中位减少0.46%–5.10%，这种单机小幅
差异不能建立稳健加速结论。机制相对根守卫在1536次锚点更新中多复用95次，表示减少不必要
重建，不证明语义fresh或代码任务收益。

首轮1536项回放输出仅15项无前沿，其余未知状态均保留。
1816条步骤记录均与fresh图canonical一致；未修改的旧解析器也在107唯一快照/2568图上匹配。
48个fresh RSS子进程完成，预设内存门槛通过。[完整成本、负面与边界](docs/zh/CATALOG_RESULTS.md)保留
初始捕获、回放、总成本与缺失RQ锚点；不宣称成熟研究，也不新增Release。

以下前三条目录复现命令须在实测提交 `affa59024f70cde86d2549b690204aa73ddccc7d` 的独立检出中运行。
当前解析器会明确拒绝旧测量指纹。最后一条则在当前研究检出中运行，按只读源码归档核验保留记录。

```sh
PYTHONPATH=src python examples/catalog_reuse.py
python scripts/prepare_catalog_sources.py --output /tmp/catalog-study-inputs
PYTHONPATH=src python scripts/run_catalog_study.py --inputs /tmp/catalog-study-inputs/ready-manifest.json --protocol benchmarks/catalog_reuse/protocol.json --output /tmp/catalog-study-results
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m benchmarks.catalog_reuse.report --check
```

## 研究分支（1.2.0a1）

解析器 4 加入延迟函数 global 守卫，解析器 3 曾引入类体 global 修复；旧图需要重新捕获。
下面的历史测量保留其原记录的解析器版本。
[读取集回放研究](docs/zh/RESEARCH_REPORT.md) 保留否定结果：只允许完整图的策略
在自然锚点转换中复用 **0/480**，四库均未达到预设加速目标；所选自然图
都有未解析前沿。这不代表成熟论文或普遍加速结论。

后续[研究稿与完整结果](docs/zh/MATURATION_REPORT.md) 在四个按仓库隔离的新样本上
比较六种方法，测量持久模块摘要、选择性图复用，以及独立进程 RSS 和 Python
内存。另有九案例、72 次隔离执行的上游测试证据研究，保留 BM25 覆盖优于图的
案例。[设计与条件保证](docs/zh/INCREMENTAL_DESIGN.md) 解释缓存和失效机制。
这些证据不能等同于模型任务提升或已经通过同行评审的成熟成果。
[逐项研究状态](docs/zh/RESEARCH_STATUS.md)将可支持的结论绑定到固定记录，并列出
语义、任务收益和外部验证方面的缺口；自动检查验证记录一致性，不能判定科研价值。

复现实验分支请使用：
`git clone --branch research/evidence-risk-20261004 https://github.com/hardwork-xu/agent-code-evidence.git`。
研究稿记录实际测量提交、固定来源和原始运行；上面的常规安装和稳定图示例仍可在 main 使用。

[研究 API 与示例](docs/zh/SELECTIVE_REUSE.md) 可离线运行，无需模型密钥。
探索性 `read_set_any_status` 模式只研究保留 unknown 输出的缓存，不认证
它为 fresh。[第三方归属](third_party/README.md) 补齐许可原文，并披露
17 项历史摘录定位限制。


[结果后的消融](docs/zh/ABLATION_REPORT.md) 保留未知状态，复用 364/480 个自然图转换；相对同期整体缓存基线，回放耗时分别降低 83.0%（Rich）、29.3%（Humanize）、18.8%（More Itertools）、6.2%（Pyflakes）。这是同数据上的探索性 CPU 结果，不是任务质量收益。
