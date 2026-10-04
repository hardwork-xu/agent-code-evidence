# Related-work positioning / 相关工作与贡献边界

核查日期：2026-10-04。以下仅保留5个高相关来源，均回到作者、项目官方或arXiv原始页面。不是系统性文献综述，也不构成“首次提出”的证明。

## 1. Build Systems à la Carte

**作者/年份：** Andrey Mokhov、Neil Mitchell、Simon Peyton Jones；2018，PACMPL 2 (ICFP), Article 79，DOI `10.1145/3236774`。作者机构的[出版记录](https://www.microsoft.com/en-us/research/publication/build-systems-la-carte/)与[正式论文PDF](https://www.microsoft.com/en-us/research/wp-content/uploads/2018/03/build-systems.pdf)可访问。核对的是2018论文，不把2020扩展期刊版混入同一版本。

**直接定位：** §4.2.2（PDF第14–15页）、§5.3（第20–21页）。Verifying traces已经记录先前依赖及其hash，并据此决定是否重建；scheduler与rebuilder分离。

**中文差异：** 当前read-set guard是已有增量思想在有界源码证据图上的工程适配，不能声称首次依赖证书、首次按hash复用或新的通用增量构建算法。可能有价值的是明确源码证据契约、保守失效、独立反例与实际工作量边界。

**EN:** Dependency-hash traces and rebuild decisions are established. Our defensible scope is a reproducible adaptation to bounded source-evidence graphs, with explicit uncertainty and separate replay/semantic evaluations. No general incremental-computation novelty follows from naming the stored read set a certificate.

## 2. Tup manual — observed reads and ghost nodes

**作者/年份：** Tup项目官方手册；该页面没有个人作者署名或发布日期，记为 **n.d.，accessed 2026-10-04**。不要借用相关2009论文的年份冒充本手册日期。[官方手册](https://gittup.org/tup/manual.html)可访问。

**直接定位：** `graph --ghosts`、`graph.ghosts`，以及Tupfile `command`描述。手册明确保留尝试读取但不存在的文件节点，并追踪命令实际读取的输入。这为负依赖提供直接先例。

**中文差异：** “未找到”会受未来文件/绑定变化影响，不是本项目新发现。当前方案观察静态名称解析查询，以既有候选文件读集和保守目录集合检查防止错误复用；Tup观察实际构建命令的文件访问，两者对象不同。这里没有运行或比较Tup。

**EN:** Failed lookups are established dependencies. Our candidate-file tracking addresses static module resolution, whereas Tup monitors command accesses. The current catalog guard is deliberately coarse; it does not establish minimal invalidation or a new negative-dependency algorithm.

## 3. Bazel Skyframe documentation

**作者/年份：** Bazel项目官方文档；页面未列个人作者或发布/更新日期，记为 **n.d.，accessed 2026-10-04**。[官方说明](https://bazel.build/reference/skyframe)可访问。

**直接定位：** “Evaluation”“Incrementality”“Mapping to Bazel concepts”。未注册输入读取可能破坏增量正确性；文件内容、文件状态和目录列表分别进入依赖图。文档还区分重建与对旧结果原地增量修改。

**中文差异：** 本项目必须证明所有影响解析结果的读都被登记；仅追踪图中成功解析到的node文件不够。`package/__init__.py`从无属性变成遮蔽子模块、目录新增歧义module均需失效。逐字节fresh-build比较只验证当前解析器输出，不证明程序语义。

**EN:** Complete dependency registration and clean-rebuild equivalence are prior engineering principles. This package can contribute inspectable guards and regression evidence for its narrower resolver. A few successful fixtures are not a proof of complete dependency tracking, hermeticity, or optimal invalidation.

## 4. ContextBench: A Benchmark for Context Retrieval in Coding Agents

**作者/年份：** Han Li、Letian Zhu、Bohan Zhang、Rili Feng、Jiaming Wang、Yue Pan、Earl T. Barr、Federica Sarro、Zhaoyang Chu、He Ye；2026。[arXiv v3](https://arxiv.org/abs/2602.05892v3)，2026-02-11；v1为2026-02-05。[正文](https://arxiv.org/html/2602.05892v3)可访问。

**直接定位：** §2.3–2.5与附录D/H。它提供人工标注的任务上下文与分粒度、过程层面的检索评估。它已经超出仅看最终任务成功率的评估方式。

**中文差异：** 本项目研究跨版本源码证据是否可复用，ContextBench主要评估任务所需上下文的检索/利用。两者互补，但当前合成oracle没有任务gold context，不能冒称ContextBench复现或检索质量提升。后续需另外验证task-conditioned coverage，避免“所有静态依赖都够用”的假设。

**EN:** Context relevance and temporal source validity are distinct. The proposed package focuses on reuse decisions across revisions; ContextBench supplies a model for task-context evaluation. No ContextBench score or task benefit has been measured in the current oracle study.

## 5. When Retrieval Hurts Code Completion: A Diagnostic Study of Stale Repository Context

**作者/年份：** Haojun Weng、Qianqian Yang、Hao Fu、Haobin Pan、Xinwei Lv；2026。[arXiv v1](https://arxiv.org/abs/2605.14478v1)，2026-05-14；[正文](https://arxiv.org/html/2605.14478v1)可访问。页面写“Submitted to Information and Software Technology”，不能改称已获该期刊接收。

**直接定位：** 摘要、实验设计与validity讨论。作者用5个Python仓库中17个helper签名变更样本，比较current/stale/no-retrieval/mixed条件，说明旧上下文可能引导错误，而非只有缺少上下文的问题。该小诊断集不等于自然总体错误率。

**中文差异：** “旧上下文有害”已有实验证据，不应包装成当前贡献。可研究的是何时能有条件认证复用、何时必须拒绝或更新，以及风险/覆盖率/成本取舍；需要模型任务实验后才能声称改善代码生成。本轮没有重跑该论文实验。

**EN:** Stale-context harm is established diagnostic evidence. A defensible next question is conditional reuse versus abstention under revision changes, not rediscovering harm. Resolver regression results and replay equality alone cannot establish better completions or task success.

## 可守住的当前表述 / Defensible present claim

**中文：** 本研究包实现并评估了一个有界Python源码证据图的保守复用策略：记录解析所咨询的来源，目录或读集变化时重建，对不完整闭包保留不确定性，并将增量输出一致性与有限静态契约、运行时契约外压力分别检验。它是已有增量技术的明确领域适配与可复核实验包；现阶段尚未证明新的通用算法、自然数据风险降低或模型任务收益。

**EN:** This package implements and evaluates conservative reuse for bounded Python source-evidence graphs. It tracks consulted sources, invalidates on catalog/read-set changes, retains incomplete frontiers, and separates byte-equivalent replay from static-contract and out-of-scope runtime tests. This is a scoped engineering adaptation and research artifact, not an established new general algorithm or demonstrated model-task improvement.

## 最应避免的比较缺口 / Critical comparison gaps

- 不能只与每个anchor重新解析全部源码的弱基线比较。所有mode应共享同快照corpus和跨版本ASTcache，并计入hash、目录检查、图复制/封装与峰值内存。/ Share fair parsing/indexing work and include guard/output costs.
- 当前实现每次hash全部输入；文件级读集及全目录失效也较粗。不能宣称更新总成本与仓库大小无关或最小失效。/ Full-input hashing and coarse invalidation limit scalability claims.
- 必须同时报告字节等价、契约内false-fresh/unknown/coverage和契约外压力；不以同一解析器自洽替代独立预期。/ Separate replay equivalence, scoped validity, and out-of-contract stress.
- 72例只含24个自写合成模板，含已知失败的开发回归。自然源码回放与自然语义标注不同；任务上下文充分性和端到端模型实验仍需独立验证。/ The authored corpus is not natural-history or task-effectiveness evidence.

这些差异判断基于上述来源与本实现，不代表论文作者对本项目的评价。
