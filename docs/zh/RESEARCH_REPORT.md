# 演进代码证据的读取集复用：实验研究报告

**状态：研究初稿，尚不具备投稿成熟度，也未经过同行评审。** 本报告分别
记录解析器修复、真实增量实验和成熟研究结论仍缺少的证据。

## 摘要与研究问题

问题是：在保持同一有界 Python 解析器输出的前提下，跨版本复用完整静态
证据，能否降低实际总开销？本实现修复类体 global 重绑定，并跟踪图节点
没有体现的负查找依赖。自写开发语料有 24 模板、72 实例；63 个在契约内，
旧版 12 个 false-fresh（四模板）变为显式 unknown；九个运行时副作用例
仍在保证范围外。新实验覆盖四个仓库、各六个固定提交、96 个去重函数锚点
及三种合成规模，9720 个图输出中配对比较无逐字节不一致。
预先声明的效用目标**未达到**。这不证明一般语义安全或模型任务收益。

## 实现、贡献与独立验证

`GraphSession` 固定锚点与策略，缓存解析结果和读取依赖。仅完整图可选择性
复用，完整路径目录和全部已咨询文件必须一致，否则完整重建。子模块回退
前检查的包文件即使没有成为图节点，也加入读取集。[设计与条件正确性论证](SELECTIVE_REUSE.md)。

这是已有依赖追踪思想的领域适配，不是通用新算法。源码身份、相关性、语义
行为和任务成功必须分别验证。历史模型实验中，图、新源码和 BM25 同为
24/25；本轮没有重跑或把它们混入新表格。

独立合成标签在解析器之外定义，并通过实际执行自写夹具检查；这是模型辅助
开发验证，不是人工专家标注或留出集。21 个契约内模板、三个契约外模板的
数值变体相互关联，不能当作自然总体错误率。
[旧新版矩阵](../../benchmarks/selective_reuse/results/v2-v3-matrix.json)。

## 实验协议

协议、方法和阈值在主要测量前本地固定，**不是公开预注册**。四个便利抽样
项目此前未进入自然语料，按最新 release 固定版本；Pyflakes 没有 release，
按明确记录的规则回退到 tag。每库六个相邻 first-parent 提交，共有
20 种不同的过滤后源码快照。最旧版本中按路径/符号哈希选最多
24 个顶层函数身份，不按图是否完整挑样本。重载身份去重，原始重复定义仍
保留在语料内，解析歧义不会被删除。

首次启动在计时前被重复重载锚点预检拦下；保留初始清单、失败记录及明确
修订。未替换源码提交、未更换性能目标。
[失败记录](../../benchmarks/selective_reuse/results/preflight-20261004.json)。

三种方法均在每版本共享已索引语料、跨版本共享 AST 缓存。整条版本轨迹的
方法顺序轮换，一次预热、五次记录，性能实验串行运行。总时间含本地归档
读取、UTF-8 解码、校验、哈希、复用检查、图复制/封装与回退。网络下载、
结果一致性检查和 JSON 写出单独处理。初次捕获另列，未计进程启动和会话
构造；操作系统背景活动未控制。

20 次自然转换中，16 次改变过滤后源码，4 次源码完全相同；
全部保留并分层报告。图、版本转换和重复试验相关，四个仓库不足以推断总体
显著性。逐次记录与 min/max 均保留。结果校验会拒绝不完整配对、失败、中断
或跨重复输入/输出漂移；输出文件不覆盖旧记录。

## 真实结果

表格为每轮五次转换耗时之和的中位数，单位毫秒；正百分比表示加快，负值
表示变慢。预设目标是相对共享索引的重建基线，至少三个仓库降低 20%，且
图无不一致。实际 **0/4 达到阈值**。

| Repository | Rebuild ms | Whole-corpus ms | Read-set ms | Read-set reduction vs rebuild | vs whole corpus |
|---|---:|---:|---:|---:|---:|
| PyCQA/pyflakes | 5578.47 | 5585.15 | 5584.74 | -0.1% | +0.0% |
| Textualize/rich | 10573.07 | 6811.07 | 10625.50 | -0.5% | -56.0% |
| more-itertools/more-itertools | 651.05 | 649.94 | 647.50 | +0.5% | +0.4% |
| python-humanize/humanize | 402.17 | 275.86 | 399.29 | +0.7% | -44.7% |

仅保留源码实际改变的转换重新汇总（同一冻结样本，没有重采样）：

| Repository | Rebuild ms | Whole-corpus ms | Read-set ms | Read-set reduction vs rebuild | vs whole corpus |
|---|---:|---:|---:|---:|---:|
| PyCQA/pyflakes | 5578.47 | 5585.15 | 5584.74 | -0.1% | +0.0% |
| Textualize/rich | 6359.48 | 6330.71 | 6329.43 | +0.5% | +0.0% |
| more-itertools/more-itertools | 651.05 | 649.94 | 647.50 | +0.5% | +0.4% |
| python-humanize/humanize | 242.91 | 242.38 | 242.31 | +0.2% | +0.0% |

24 个自然版本出现（20 种唯一源码快照）中，被选图的完整数量全部为零。这反映当前解析器和采样范围
的覆盖局限，不是说自然程序不安全。每轮选择性策略复用 0/480 个自然锚点转换图。这不是语义安全
数量。全语料相同的简单策略可保留不完整图及其 unknown 状态，选择性模式
则重建，因此只和重建比较会隐去更强的简单替代方案。

| Repository | Initial capture median ms |
|---|---:|
| PyCQA/pyflakes | 1110.46 |
| Textualize/rich | 2252.25 |
| more-itertools/more-itertools | 139.13 |
| python-humanize/humanize | 81.66 |

10、100、1000 模块的合成实验均有无关文件改动、被引用文件改动和目录新增。
原始数据保留不利回退、初次捕获及全部五轮，不把合成负载解释为自然分布。

## 来源勘误

已补齐并离线核对第三方许可原文。单独脚本核对 71 个原文件中的 1309 处已分发
摘录：748 字节完全一致、544 仅有呈现空白差异，17 处历史非连续摘录误标
连续行范围。17 项均单列定位勘误，不修改历史原始输出，也不冒称连续出处
全部正确。[核验数据](../../third_party/source-verification.json) ·
[17 项勘误](../../third_party/noncontiguous-excerpts.json)。

## 结论与成熟度边界

主要计时假设未达到预设目标。这个可复核的否定结果有价值，但不能据此宣传普遍加速。
成熟论文还缺：超出现有增量思想的明确贡献、独立于本解析器的任务上下文
标注、按仓库/时间隔离的自然验证，以及与新检索和简单失效基线的端到端
代码任务对照。尚未发生独立人工复核、外部复现、同行接收或论文发表。
也未实现逐模块绑定摘要的增量基线，未测缓存驻留内存/RSS，比较仅限三个已测方法。
这份初稿是技术研究记录，不是已经完成的论文，不宣称 SOTA、生产部署或
模型质量提升。

## 文献与复现

[Build Systems à la Carte (2018)](https://www.microsoft.com/en-us/research/wp-content/uploads/2018/03/build-systems.pdf)
已有依赖哈希追踪；[Tup](https://gittup.org/tup/manual.html) 与
[Skyframe](https://bazel.build/reference/skyframe) 已强调负依赖及完整输入登记。
[ContextBench v3](https://arxiv.org/abs/2602.05892v3) 关注任务相关上下文；
[When Retrieval Hurts v1](https://arxiv.org/abs/2605.14478v1) 研究过时上下文的危害。
本轮没有复现它们的模型实验。[详细差异与一手来源](RELATED_WORK.md)。

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python scripts/check_attribution.py
python scripts/run_selective_reuse.py prepare
python scripts/run_selective_reuse.py run --suite all
python scripts/run_selective_reuse.py analyze --output PATH_TO_NEW_RUN_JSON
python scripts/render_selective_report.py benchmarks/selective_reuse/results/primary-20261004.json
```

原始数据的命令是去掉本机缓存位置的可移植复现命令；源码与 runner 的哈希
另行固定。测量时文档/归属补充尚未提交，但列出的运行时源码及 runner 已
提交并记录哈希。

- run_id: `selective-20261004T195433Z`
- source commit: `b25b3d4ed20eb36f1e432dbd5d8ce4db9ad8bca8`
- protocol SHA256: `ca129aed54bda5e94eadd26929736ed906b2b74e87ca0469b43db7367f2a1e0e`
- manifest SHA256: `c9034cc9fae4e44ae395c9b0a3ad280ae2da17050ff88de4408b5d687d4a5ef0`
- Python 3.12.2, Apple M1 Pro, arm64, RAM 16 GiB; one benchmark thread.
- [Raw data / 原始数据](../../benchmarks/selective_reuse/results/primary-20261004.json); [protocol / 协议](../../benchmarks/selective_reuse/protocol.json); [pins / 版本](../../benchmarks/selective_reuse/natural-manifest.json).

