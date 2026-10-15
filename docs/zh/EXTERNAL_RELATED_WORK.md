# 外部定位：已有机制与贡献边界

官方来源核查日期为2026-10-14。这是定向比较，未穷尽文献。下列外部实现均未实际运行，其论文数字不进入本地实测表。

| 工作 | 固定源码版本 | 已有机制 | 对照边界 |
|---|---|---|---|
| [Agentless](https://arxiv.org/html/2407.01489v2) | `5ce5888b9f149beaace393957a55ea8ee46c9f71` | 文件/符号/编辑位置分层定位、LibCST骨架、修复与验证 | 本静态适配器没有复现其LLM、嵌入与修复系统 |
| [Aider repo map](https://aider.chat/docs/repomap.html) | `5dc9490bb35f9729ef2c95d00a19ccd30c26339c` | tree-sitter定义/引用、依赖图和个性化PageRank、预算化源码图、mtime缓存/刷新 | 符号摘要与确切声明文本输出不同，严格UTF-8字节不等于其近似token额度 |
| [SWE-bench](https://arxiv.org/html/2310.06770v3) | `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e` | 问题→Lucene/Pyserini BM25、上下文上限、参考编辑文件召回 | 官方排除tests、采用文件/top20；本内部BM25包含全部Python/tests并使用窗口/声明 |
| [ContextBench](https://arxiv.org/html/2602.05892v3) | `1436c28a8eb95496da4ea69ad458b9f8a8eb7d61` | 文件/定义/行覆盖与精度、区间并集、过程上下文评估 | 专家标注的紧凑充分参考上下文与补丁编辑不同；数据许可链未核清，因此未使用其gold数据 |

固定源码位置见[来源登记](../../benchmarks/external_context/related-work-pins.json)。研究公开设计与源码不构成严格clean-room证明；适配器没有复制上述项目的第三方实现。

图/AST检索、字节/token预算、缓存和重叠指标均已有先例。既有研究分支更窄的工程贡献是显式版本源码证据约定、可观察未知、保守read-set失效及经验证的回放开销。依赖追踪本身也有先例，见[增量相关工作分析](RELATED_WORK.md)。

39任务pilot只观察每项一个base版本，可评估当前实现和预算下的静态编辑定位，并在这些条件下否定宽泛的图收益声明；不能证明跨版本恢复、语义新鲜性、智能体修复收益、学术首创或成熟研究。更强对照需实际运行固定外部适配器、公平的原生/共享语料协议和未触碰验证输入。

[English](../en/EXTERNAL_RELATED_WORK.md)
