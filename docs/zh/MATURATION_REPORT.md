# 增量代码证据复用与任务执行见证

**状态：可复核的工程研究报告；不声称投稿成熟度、SOTA、独立人工评审或代码 Agent 收益。** 表格与达标判断由已完成且通过校验的记录生成，无效任务试运行不提供结论证据。

## 摘要

本研究将既有依赖追踪思想用于进程内、有界 Python 源码证据图。仓库层面的留出便利样本包含 4 个仓库、每库 8 个固定版本及共 96 个固定锚点。候选方法与 “持久模块索引＋全语料相等复用”比较。4/4 个仓库达到 20.0% 的回放降时阈值；时间目标**达到**，RSS 门槛**达到**。完整记录相对无跨版本缓存的重建共有 0 个规范图不一致。768/768 个参照图仍有不完整边界：缓存保留 unknown，并不认证语义 fresh。另一项经修正的 9 案例开发研究，按已审查的 fixture 适配方式执行上游原始断言函数体。图与等行数 BM25 的任务执行见证宏平均召回率分别为 53.9% 和 37.4%。回放成本与任务相关源码覆盖是不同结论；二者均不能证明上下文充分性、语义可靠性或模型任务收益。

## 1. 研究问题与贡献边界

RQ1：在披露完整输入处理成本与内存成本的条件下，选择性读集复用能否超越持久索引和廉价全语料判断的组合？RQ2：特定上游断言真正执行过的源码行，有多少出现在各类提供的上下文中？第二类标签来自 Python 实际执行，独立于静态依赖提取，但并非人工标注的金标准上下文。源码身份、解析器等价、执行覆盖与 Agent 成功分别讨论。

模块摘要按路径和源码哈希缓存 AST 与带约束的绑定；跨文件解析始终使用当前目录。读集保留失败候选查找；目录变化保守失效，不完整边界继续保持不完整。输出图复制并重新封装，旧摘要被清理，全部锚点成功后才发布新状态。仍需哈希全部源码；少做索引不能消除归档 I/O、解码及图输出成本。[具体机制与假设](INCREMENTAL_DESIGN.md)。

## 2. 固定设计与比较方法

四个仓库均不在历史及开发源码语料中。图结果观察前，固定最新稳定 release 及其前七个相邻 first-parent 提交；在最旧版本按 SHA 排序选每库 24 个顶层函数身份，后续不重选。重复定义、缺失或含糊锚点以及全部转换都保留。这是本地预先声明，不是公开预注册。

仅检查输入字节时发现 15/28 次转换源码相同。尚未观察任何留出图或计时结果时，明确修订加入 IWCG，并将主比较从 IDX 加强为 IWCG。原协议与清单完整留存，源码、锚点、阈值不变。各方法均在同一快照内共享索引语料。公开默认模式的严格完整性门槛未变；此处评估明确命名的实验模式。

| 缩写 | 模式 | 行为 |
|---|---|---|
| AST | `warm_ast_rebuild` | 缓存 AST；重建绑定及图 |
| WCG | `whole_corpus_guard` | 缓存 AST；仅全源码相等时复用图 |
| RS | `read_set_any_status` | 缓存 AST；选择性复用并保留边界 |
| IDX | `incremental_index_rebuild` | 持久模块摘要；每次重建图 |
| IWCG | `incremental_whole_corpus_guard` | 持久摘要＋全语料复用；主基线 |
| IRS | `incremental_read_set` | 持久摘要＋读集复用；候选方法 |

[最终协议](../../benchmarks/incremental_holdout/protocol.json) · [原协议](../../benchmarks/incremental_holdout/initial-protocol.json) · [固定源码与锚点清单](../../benchmarks/incremental_holdout/manifest.json)。

## 3. 工作负载与测量边界

| 仓库 | Release | 首版文件数 | 最大源码字节数 | 锚点 | 源码改变转换 | 源码相同转换 |
|---|---|---|---|---|---|---|
| pallets/jinja | 3.1.6 | 25 | 490070 | 24 | 4 | 3 |
| encode/starlette | 1.7.0 | 36 | 257955 | 24 | 6 | 1 |
| agronholm/anyio | 4.15.1 | 46 | 529017 | 24 | 2 | 5 |
| Python-Markdown/markdown | 3.11.0 | 32 | 327320 | 24 | 1 | 6 |

各方法先完整预热一条轨迹，再记录 5 条轨迹，按整条方法轨迹轮换顺序。每次使用新 GraphSession。主要观察值是每条轨迹七次回放转换的耗时总和；表格给出其中位数及最小/最大值，不把转换或锚点混合当作独立观测。本地归档读取、哈希、解压、解码、源码校验、索引、检查、复制/封装及回退全部计时；下载、规范图比较与结果写出不计入。首次捕获单列，捕获加回放是必报次要指标；这些耗时总和不包括进程启动及会话构造。仅源码改变的分层结果属于描述性分析，不替换固定主指标。未控制操作系统背景活动。

## 4. 主结果与达标判断

预定时间标准是在至少 3/4 个仓库中，中位回放时间降低不少于 20.0%。同时每个仓库的未启用追踪器 RSS 峰值中位数不得超过基线 2 倍或 512 MiB。**时间：达到；内存：达到；联合门槛：达到。** 降时为正表示更快，负值表示退步。

| 仓库 | IWCG ms [min,max] | IRS ms [min,max] | 降时 | 时间门槛 | RSS IRS/IWCG | 内存门槛 |
|---|---|---|---|---|---|---|
| pallets/jinja | 1959.32 [1939.14, 1991.39] | 1279.66 [1250.61, 1374.68] | +34.7% | 达到 | 0.995× | 达到 |
| encode/starlette | 2011.70 [1985.94, 2029.13] | 888.80 [879.42, 954.00] | +55.8% | 达到 | 0.895× | 达到 |
| agronholm/anyio | 481.03 [477.37, 507.64] | 290.42 [269.12, 297.37] | +39.6% | 达到 | 1.026× | 达到 |
| Python-Markdown/markdown | 641.98 [631.89, 678.15] | 427.87 [408.17, 501.84] | +33.4% | 达到 | 0.998× | 达到 |

校验将 768 个不同快照/锚点参照、计时中的 23040 个图摘要和内存运行中的 27648 个图摘要与逐快照重新解析的参照比较，规范图不一致为零。这些重复输出不是独立语义测试案例。

## 5. 全部方法、分层与首次捕获成本

所有数值为轨迹耗时总和的 ms 中位数 [最小值，最大值]。各仓库仅源码改变的转换数不同，应在同一仓库内比较方法，不应直接横比该分层总耗时。

| 仓库 | 方法 | 回放 | 仅源码改变回放 | 捕获 | 捕获＋回放 |
|---|---|---|---|---|---|
| pallets/jinja | AST | 3763.34 [3759.55, 3864.95] | 2141.36 [2137.95, 2175.38] | 584.75 [579.73, 622.33] | 4346.09 [4343.80, 4487.28] |
| pallets/jinja | WCG | 2252.88 [2226.34, 2295.13] | 2162.98 [2136.10, 2200.37] | 585.71 [579.09, 603.50] | 2838.60 [2823.11, 2898.63] |
| pallets/jinja | RS | 1560.49 [1528.33, 1571.16] | 1457.34 [1436.24, 1480.33] | 585.92 [577.13, 599.19] | 2146.22 [2123.98, 2170.35] |
| pallets/jinja | IDX | 3239.05 [3199.60, 3285.30] | 1860.98 [1842.43, 1924.91] | 585.05 [578.93, 623.15] | 3829.40 [3809.94, 3864.23] |
| pallets/jinja | IWCG | 1959.32 [1939.14, 1991.39] | 1867.39 [1824.66, 1878.68] | 579.15 [574.05, 590.71] | 2548.13 [2518.28, 2565.44] |
| pallets/jinja | IRS | 1279.66 [1250.61, 1374.68] | 1167.56 [1156.46, 1250.33] | 588.15 [580.20, 639.64] | 1862.71 [1838.35, 2014.31] |
| encode/starlette | AST | 2616.25 [2587.77, 2825.43] | 2252.28 [2219.09, 2444.05] | 402.48 [394.40, 406.63] | 3018.73 [2994.40, 3219.83] |
| encode/starlette | WCG | 2299.66 [2273.17, 2325.24] | 2248.66 [2221.99, 2271.71] | 397.62 [393.75, 417.39] | 2693.41 [2678.84, 2742.64] |
| encode/starlette | RS | 1031.87 [1022.98, 1041.67] | 971.52 [969.49, 980.91] | 395.63 [394.88, 398.44] | 1426.75 [1421.42, 1437.30] |
| encode/starlette | IDX | 2279.73 [2268.15, 2315.07] | 1953.53 [1949.17, 1998.41] | 409.97 [403.53, 422.71] | 2698.03 [2675.12, 2718.61] |
| encode/starlette | IWCG | 2011.70 [1985.94, 2029.13] | 1959.78 [1933.95, 1976.57] | 395.93 [393.07, 403.29] | 2414.33 [2383.02, 2425.06] |
| encode/starlette | IRS | 888.80 [879.42, 954.00] | 836.52 [827.26, 902.66] | 405.20 [391.26, 413.32] | 1296.28 [1283.93, 1345.25] |
| agronholm/anyio | AST | 1827.06 [1818.13, 1849.68] | 516.50 [514.93, 543.60] | 310.14 [307.81, 327.28] | 2134.87 [2127.95, 2176.96] |
| agronholm/anyio | WCG | 677.73 [649.00, 683.19] | 513.99 [510.10, 544.58] | 314.76 [313.86, 325.24] | 992.49 [963.07, 999.64] |
| agronholm/anyio | RS | 463.51 [437.56, 465.06] | 301.84 [300.08, 324.98] | 314.20 [309.03, 328.31] | 774.08 [759.73, 777.72] |
| agronholm/anyio | IDX | 1197.58 [1177.55, 1209.24] | 341.13 [337.43, 343.96] | 313.84 [305.05, 321.87] | 1508.17 [1499.41, 1523.08] |
| agronholm/anyio | IWCG | 481.03 [477.37, 507.64] | 341.15 [339.88, 368.96] | 313.51 [308.52, 331.48] | 810.22 [792.40, 821.15] |
| agronholm/anyio | IRS | 290.42 [269.12, 297.37] | 131.49 [128.03, 153.22] | 313.45 [310.91, 331.66] | 601.63 [593.93, 610.82] |
| Python-Markdown/markdown | AST | 2577.57 [2563.66, 2759.55] | 364.96 [360.16, 546.08] | 392.13 [385.25, 413.75] | 2972.32 [2950.15, 3151.68] |
| Python-Markdown/markdown | WCG | 690.87 [685.41, 701.91] | 371.93 [361.88, 380.10] | 396.48 [395.83, 403.97] | 1092.20 [1081.24, 1101.88] |
| Python-Markdown/markdown | RS | 462.87 [454.02, 469.31] | 135.81 [134.27, 138.70] | 395.70 [384.43, 397.24] | 852.76 [842.84, 866.55] |
| Python-Markdown/markdown | IDX | 2292.58 [2245.57, 2425.46] | 338.74 [317.42, 352.86] | 402.12 [394.68, 421.56] | 2694.70 [2640.25, 2847.02] |
| Python-Markdown/markdown | IWCG | 641.98 [631.89, 678.15] | 320.03 [317.80, 345.87] | 392.52 [384.08, 403.56] | 1030.75 [1015.97, 1081.71] |
| Python-Markdown/markdown | IRS | 427.87 [408.17, 501.84] | 98.72 [92.97, 106.63] | 396.11 [388.47, 408.03] | 822.70 [800.87, 903.46] |

## 6. 未启用追踪器的驻留内存

每格为 3 个新进程执行完整 8 版本轨迹后的 MiB 中位数 [最小值，最大值]，不预热、不启用 tracemalloc。RSS 门槛只使用这些进程。RSS 包含解释器/导入、源码映射、临时对象、索引与图，不能解释为缓存自身大小。原生高水位单位由 [macOS 的字节（Apple XNU 手册）](https://raw.githubusercontent.com/apple-oss-distributions/xnu/main/bsd/man/man2/getrusage.2) 及 [Linux 的 KiB（getrusage 手册）](https://man7.org/linux/man-pages/man2/getrusage.2.html) 归一化。

| 仓库 | 方法 | RSS peak MiB [min,max] |
|---|---|---|
| pallets/jinja | AST | 68.22 [67.94, 69.88] |
| pallets/jinja | WCG | 70.11 [66.94, 70.47] |
| pallets/jinja | RS | 68.12 [65.83, 71.61] |
| pallets/jinja | IDX | 69.05 [67.38, 72.17] |
| pallets/jinja | IWCG | 70.59 [70.58, 73.11] |
| pallets/jinja | IRS | 70.25 [67.81, 70.73] |
| encode/starlette | AST | 66.98 [62.95, 73.45] |
| encode/starlette | WCG | 75.88 [72.17, 78.19] |
| encode/starlette | RS | 71.41 [70.86, 72.75] |
| encode/starlette | IDX | 76.12 [72.08, 77.05] |
| encode/starlette | IWCG | 75.55 [62.16, 77.78] |
| encode/starlette | IRS | 67.64 [63.25, 71.27] |
| agronholm/anyio | AST | 63.69 [63.28, 65.03] |
| agronholm/anyio | WCG | 63.98 [63.28, 65.14] |
| agronholm/anyio | RS | 63.86 [63.00, 64.27] |
| agronholm/anyio | IDX | 63.53 [62.61, 66.11] |
| agronholm/anyio | IWCG | 63.00 [62.97, 63.45] |
| agronholm/anyio | IRS | 64.64 [64.58, 65.88] |
| Python-Markdown/markdown | AST | 51.14 [49.86, 57.50] |
| Python-Markdown/markdown | WCG | 55.81 [55.33, 57.06] |
| Python-Markdown/markdown | RS | 51.47 [51.38, 56.73] |
| Python-Markdown/markdown | IDX | 52.47 [51.48, 57.72] |
| Python-Markdown/markdown | IWCG | 56.45 [55.27, 57.36] |
| Python-Markdown/markdown | IRS | 56.31 [55.69, 56.34] |

相对 IWCG，候选方法 RSS 峰值中位数增加的仓库：agronholm/anyio +2.6%。通过内存预算不等于内存使用下降。

## 7. 单独追踪的 Python 分配

此组新进程在首次读取源码前启用 tracemalloc，与计时及 RSS 门槛进程分开。释放返回图并执行 GC 后记录当前追踪保留量，此时会话与当前源码映射仍存活。追踪峰值/当前字节量只描述启动追踪以来观察到的分配，不是全部进程内存；追踪本身也改变成本。[Python 3.12 tracemalloc 文档](https://docs.python.org/3.12/library/tracemalloc.html)。

| 仓库 | 方法 | Python peak MiB [min,max] | 末版保留 MiB [最小,最大] |
|---|---|---|---|
| pallets/jinja | AST | 22.71 [22.71, 22.71] | 18.67 [18.67, 18.67] |
| pallets/jinja | WCG | 22.71 [22.71, 22.71] | 18.66 [18.66, 18.66] |
| pallets/jinja | RS | 22.28 [22.28, 22.28] | 18.66 [18.66, 18.66] |
| pallets/jinja | IDX | 22.72 [22.72, 22.72] | 19.00 [19.00, 19.00] |
| pallets/jinja | IWCG | 22.71 [22.71, 22.71] | 19.00 [19.00, 19.00] |
| pallets/jinja | IRS | 22.46 [22.46, 22.46] | 19.00 [19.00, 19.00] |
| encode/starlette | AST | 17.09 [17.09, 17.09] | 12.56 [12.56, 12.56] |
| encode/starlette | WCG | 17.09 [17.09, 17.09] | 12.56 [12.56, 12.56] |
| encode/starlette | RS | 16.97 [16.97, 16.97] | 12.55 [12.55, 12.55] |
| encode/starlette | IDX | 17.09 [17.09, 17.09] | 12.89 [12.89, 12.89] |
| encode/starlette | IWCG | 17.09 [17.09, 17.09] | 12.89 [12.89, 12.89] |
| encode/starlette | IRS | 16.97 [16.97, 16.98] | 12.88 [12.88, 12.88] |
| agronholm/anyio | AST | 22.11 [22.11, 22.12] | 18.87 [18.87, 18.87] |
| agronholm/anyio | WCG | 22.11 [22.11, 22.11] | 18.86 [18.86, 18.86] |
| agronholm/anyio | RS | 21.23 [21.23, 21.23] | 18.85 [18.85, 18.85] |
| agronholm/anyio | IDX | 22.09 [22.09, 22.09] | 19.47 [19.47, 19.47] |
| agronholm/anyio | IWCG | 22.08 [22.08, 22.08] | 19.46 [19.46, 19.46] |
| agronholm/anyio | IRS | 21.23 [21.23, 21.23] | 19.46 [19.46, 19.46] |
| Python-Markdown/markdown | AST | 15.43 [15.43, 15.43] | 12.39 [12.39, 12.39] |
| Python-Markdown/markdown | WCG | 15.43 [15.42, 15.43] | 12.39 [12.39, 12.39] |
| Python-Markdown/markdown | RS | 14.50 [14.50, 14.50] | 12.39 [12.38, 12.39] |
| Python-Markdown/markdown | IDX | 15.42 [15.42, 15.42] | 12.62 [12.62, 12.62] |
| Python-Markdown/markdown | IWCG | 15.41 [15.41, 15.41] | 12.61 [12.61, 12.61] |
| Python-Markdown/markdown | IRS | 14.54 [14.54, 14.54] | 12.61 [12.61, 12.61] |

主比较方法逐版本 GC 后保留量（MiB）；八个版本不能证明长期运行的内存上界：

| 仓库 | 版本 | Commit | IWCG [min,max] | IRS [min,max] |
|---|---|---|---|---|
| pallets/jinja | 0 | eda8fe86fd | 18.97 [18.97, 18.97] | 18.97 [18.97, 18.97] |
| pallets/jinja | 1 | 8d58859265 | 18.97 [18.97, 18.97] | 18.97 [18.97, 18.97] |
| pallets/jinja | 2 | b4ffc8ff29 | 18.98 [18.98, 18.98] | 18.98 [18.98, 18.98] |
| pallets/jinja | 3 | ab8218c7a1 | 18.99 [18.99, 18.99] | 18.99 [18.99, 18.99] |
| pallets/jinja | 4 | bc68d4efa9 | 18.99 [18.99, 18.99] | 18.99 [18.99, 18.99] |
| pallets/jinja | 5 | 033c20015c | 19.00 [19.00, 19.00] | 19.00 [19.00, 19.00] |
| pallets/jinja | 6 | 90457bbf33 | 18.99 [18.99, 18.99] | 18.99 [18.99, 18.99] |
| pallets/jinja | 7 | 15206881c0 | 19.00 [19.00, 19.00] | 19.00 [19.00, 19.00] |
| encode/starlette | 0 | 485aca4e79 | 12.84 [12.84, 12.84] | 12.84 [12.84, 12.84] |
| encode/starlette | 1 | f03f65c2f9 | 12.82 [12.82, 12.82] | 12.82 [12.82, 12.82] |
| encode/starlette | 2 | 76fd00f1e2 | 12.83 [12.83, 12.83] | 12.53 [12.53, 12.53] |
| encode/starlette | 3 | 03f12b7fcf | 12.84 [12.83, 12.84] | 12.83 [12.83, 12.83] |
| encode/starlette | 4 | 57de5fa9c2 | 12.87 [12.87, 12.87] | 12.87 [12.87, 12.87] |
| encode/starlette | 5 | 1f08daf162 | 12.88 [12.88, 12.88] | 12.69 [12.69, 12.69] |
| encode/starlette | 6 | 4fe55eb264 | 12.88 [12.88, 12.88] | 12.88 [12.88, 12.88] |
| encode/starlette | 7 | 2269e9a08c | 12.89 [12.89, 12.89] | 12.88 [12.88, 12.88] |
| agronholm/anyio | 0 | 9727dc5046 | 19.46 [19.46, 19.46] | 19.46 [19.46, 19.46] |
| agronholm/anyio | 1 | b825c3be7c | 19.43 [19.43, 19.43] | 19.43 [19.43, 19.43] |
| agronholm/anyio | 2 | 942e9a6552 | 19.44 [19.44, 19.44] | 19.44 [19.44, 19.44] |
| agronholm/anyio | 3 | 033fc52b8f | 19.45 [19.44, 19.45] | 19.44 [19.44, 19.44] |
| agronholm/anyio | 4 | d137692a90 | 19.45 [19.45, 19.45] | 19.45 [19.45, 19.45] |
| agronholm/anyio | 5 | 9283662595 | 19.45 [19.45, 19.45] | 19.45 [19.45, 19.45] |
| agronholm/anyio | 6 | 0ecf5ed98d | 19.46 [19.46, 19.46] | 19.45 [19.45, 19.45] |
| agronholm/anyio | 7 | ffcd1542cd | 19.46 [19.46, 19.46] | 19.46 [19.46, 19.46] |
| Python-Markdown/markdown | 0 | 5d1363ce4b | 12.61 [12.61, 12.61] | 12.61 [12.61, 12.61] |
| Python-Markdown/markdown | 1 | 8a96db59e3 | 12.59 [12.59, 12.59] | 12.59 [12.59, 12.59] |
| Python-Markdown/markdown | 2 | 36cdbd3c7e | 12.59 [12.59, 12.59] | 12.59 [12.59, 12.59] |
| Python-Markdown/markdown | 3 | 819fff96b0 | 12.59 [12.59, 12.59] | 12.59 [12.59, 12.59] |
| Python-Markdown/markdown | 4 | a5176b06f2 | 12.60 [12.60, 12.60] | 12.60 [12.60, 12.60] |
| Python-Markdown/markdown | 5 | 571f050f0c | 12.60 [12.60, 12.60] | 12.60 [12.60, 12.60] |
| Python-Markdown/markdown | 6 | 547a9349d4 | 12.61 [12.61, 12.61] | 12.61 [12.61, 12.61] |
| Python-Markdown/markdown | 7 | 0ffbf00cf6 | 12.61 [12.61, 12.61] | 12.61 [12.61, 12.61] |

## 8. 复用与不完整输出覆盖

768/768 个参照图含有不完整边界。复用次数表示少做的计算，不表示新认证的语义 fresh。每个固定版本的完整图数由无跨版本缓存参照给出；各方法必须保持相同计数及规范边界。计时文件保存完整性计数和图摘要，没有边界类别直方图，因此不推测未记录的直方图。

| 仓库 | 方法 | 重复 1–5 的复用数 | 锚点×转换 | 版本 0–7 完整图数 |
|---|---|---|---|---|
| pallets/jinja | AST | 0, 0, 0, 0, 0 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| pallets/jinja | WCG | 72, 72, 72, 72, 72 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| pallets/jinja | RS | 149, 149, 149, 149, 149 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| pallets/jinja | IDX | 0, 0, 0, 0, 0 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| pallets/jinja | IWCG | 72, 72, 72, 72, 72 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| pallets/jinja | IRS | 149, 149, 149, 149, 149 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| encode/starlette | AST | 0, 0, 0, 0, 0 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| encode/starlette | WCG | 24, 24, 24, 24, 24 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| encode/starlette | RS | 159, 159, 159, 159, 159 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| encode/starlette | IDX | 0, 0, 0, 0, 0 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| encode/starlette | IWCG | 24, 24, 24, 24, 24 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| encode/starlette | IRS | 159, 159, 159, 159, 159 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| agronholm/anyio | AST | 0, 0, 0, 0, 0 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| agronholm/anyio | WCG | 120, 120, 120, 120, 120 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| agronholm/anyio | RS | 164, 164, 164, 164, 164 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| agronholm/anyio | IDX | 0, 0, 0, 0, 0 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| agronholm/anyio | IWCG | 120, 120, 120, 120, 120 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| agronholm/anyio | IRS | 164, 164, 164, 164, 164 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| Python-Markdown/markdown | AST | 0, 0, 0, 0, 0 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| Python-Markdown/markdown | WCG | 144, 144, 144, 144, 144 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| Python-Markdown/markdown | RS | 167, 167, 167, 167, 167 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| Python-Markdown/markdown | IDX | 0, 0, 0, 0, 0 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| Python-Markdown/markdown | IWCG | 144, 144, 144, 144, 144 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| Python-Markdown/markdown | IRS | 167, 167, 167, 167, 167 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |

## 9. 任务相关执行见证方法

独立任务集含 packaging、attrs、pluggy 的 9 个断言案例，使用已有开发版本对，不是留出集。将 after 版上游原始函数体应用到前后两个版本，使用经审查的导入、参数及 fixture 适配设置；不执行完整 pytest/conftest/setup 钩子。通过 dont_inherit=True 保留原始 future 标志。fixture 会影响准备、作用域和参数，所以提取函数体并不等于完整 pytest 环境。[官方 fixture 语义](https://docs.pytest.org/en/stable/how-to/fixtures.html)。

每个版本在独立受限 macOS 进程中追踪两次、不追踪两次，共 72 个子进程。重复结果及逐调用断言结果必须一致；9/9 案例通过追踪/不追踪一致性检查。导入与 fixture 准备先于追踪窗口。见证是 after 版本断言各次调用实际执行的包源码物理行并集；before 版结果提供变化或稳定对照信息。attrs 动态生成代码另计。Python 追踪属于线程局部机制，这些经审查的进程内调用不提供一般多线程执行 oracle。[Python 3.12 追踪文档](https://docs.python.org/3.12/library/sys.html#sys.settrace)。

各方法使用相同固定源码和入口提示。BM25 用上游测试文字加提示，对 20 行窗口检索，并严格匹配图的唯一物理行预算。完整源码是不限预算的上界。旧图的全部提供行数均计费，只有当前同文件中唯一且完全相同的片段才获得当前源码覆盖信用。该指标是执行行召回率，不是金标准上下文精确率、token 成本或修复成功率。7/9 案例前版失败、后版通过；版本对差异不能归因于单个补丁。

| 案例 | 前版 → 后版 release | 上游后版原始测试 | 每子进程调用数 |
|---|---|---|---|
| packaging-prereleases | 23.2 → 24.2 | [TestSpecifier.test_specifier_prereleases_detection](https://github.com/pypa/packaging/blob/d8e3b31b734926ebbcaff654279f6855a73e052f/tests/test_specifiers.py#L517) | 14 |
| packaging-specifier-iterable | 23.2 → 24.2 | [TestSpecifierSet.test_create_from_specifiers](https://github.com/pypa/packaging/blob/d8e3b31b734926ebbcaff654279f6855a73e052f/tests/test_specifiers.py#L659) | 1 |
| packaging-metadata-keywords | 23.2 → 24.2 | [TestMetadata.test_optional_defaults_to_none](https://github.com/pypa/packaging/blob/d8e3b31b734926ebbcaff654279f6855a73e052f/tests/test_metadata.py#L620) | 1 |
| attrs-makeclass-annotations | 23.2.0 → 24.3.0 | [TestMakeClass.test_annotations](https://github.com/python-attrs/attrs/blob/598494a618410490cfbe0c896b7a544f6d23e0d9/tests/test_make.py#L1187) | 1 |
| attrs-preinit-default | 23.2.0 → 24.3.0 | [TestAttributes.test_pre_init_kw_only_work_with_defaults](https://github.com/python-attrs/attrs/blob/598494a618410490cfbe0c896b7a544f6d23e0d9/tests/test_make.py#L698) | 2 |
| attrs-init-subclass | 23.2.0 → 24.3.0 | [TestFunctional.test_init_subclass](https://github.com/python-attrs/attrs/blob/598494a618410490cfbe0c896b7a544f6d23e0d9/tests/test_functional.py#L754) | 2 |
| pluggy-set-blocked | 1.3.0 → 1.5.0 | [test_set_blocked](https://github.com/pytest-dev/pluggy/blob/f8aa4a009716a7994f2f6c1947d9fa69feccbdd5/testing/test_pluginmanager.py#L95) | 1 |
| pluggy-registration-name | 1.3.0 → 1.5.0 | [test_pm_name](https://github.com/pytest-dev/pluggy/blob/f8aa4a009716a7994f2f6c1947d9fa69feccbdd5/testing/test_pluginmanager.py#L76) | 1 |
| pluggy-call-extra | 1.3.0 → 1.5.0 | [test_call_extra](https://github.com/pytest-dev/pluggy/blob/f8aa4a009716a7994f2f6c1947d9fa69feccbdd5/testing/test_pluginmanager.py#L400) | 1 |

[固定测试与源码清单](../../benchmarks/task_evidence/manifest.json) · [任务执行与 fixture 适配协议](../../benchmarks/task_evidence/PROTOCOL.md) · [源码获取、隔离预检及复现命令](../../benchmarks/task_evidence/README.md)。

## 10. 逐案例与逐仓库任务结果

下表每格为召回率 / 提供的物理行数。图召回率在 7 个案例高于 BM25，1 个较低，1 个相同。这些相关的便利案例不能支持显著性或普遍优越性判断。图较低案例：pluggy-registration-name。

图召回率还在 packaging-prereleases 中低于直接锚点上下文。按仓库宏平均，pluggy 的图召回率低于 BM25。这些覆盖比较本身不能确定因果原因。

| 案例 | Full source | Anchors | Graph | BM25 | Old graph |
|---|---|---|---|---|---|
| packaging-prereleases | 100.0% / 5653 | 23.0% / 50 | 9.8% / 34 | 0.0% / 34 | 0.0% / 34 |
| packaging-specifier-iterable | 100.0% / 5653 | 4.1% / 37 | 94.5% / 1179 | 21.9% / 1179 | 0.0% / 1168 |
| packaging-metadata-keywords | 100.0% / 5653 | 30.8% / 56 | 100.0% / 3484 | 100.0% / 3484 | 0.0% / 127 |
| attrs-makeclass-annotations | 100.0% / 5823 | 7.1% / 163 | 28.7% / 755 | 3.6% / 755 | 4.5% / 996 |
| attrs-preinit-default | 100.0% / 5823 | 5.7% / 387 | 82.6% / 2326 | 43.3% / 2326 | 12.6% / 2313 |
| attrs-init-subclass | 100.0% / 5823 | 15.0% / 222 | 99.8% / 2129 | 66.2% / 2129 | 17.2% / 2372 |
| pluggy-set-blocked | 100.0% / 1666 | 4.2% / 4 | 4.2% / 4 | 2.1% / 4 | 4.2% / 4 |
| pluggy-registration-name | 100.0% / 1666 | 20.5% / 50 | 20.5% / 437 | 87.2% / 437 | 20.5% / 420 |
| pluggy-call-extra | 100.0% / 1666 | 13.5% / 33 | 45.2% / 171 | 12.7% / 171 | 31.7% / 170 |

| 组 | 方法 | 案例数 | 宏平均召回 | 平均提供行数 |
|---|---|---|---|---|
| all | Anchors | 9 | 13.8% | 111.33 |
| all | Full source | 9 | 100.0% | 4380.67 |
| all | Graph | 9 | 53.9% | 1168.78 |
| all | BM25 | 9 | 37.4% | 1168.78 |
| all | Old graph | 9 | 10.1% | 844.89 |
| attrs | Anchors | 3 | 9.3% | 257.33 |
| attrs | Full source | 3 | 100.0% | 5823.00 |
| attrs | Graph | 3 | 70.3% | 1736.67 |
| attrs | BM25 | 3 | 37.7% | 1736.67 |
| attrs | Old graph | 3 | 11.5% | 1893.67 |
| packaging | Anchors | 3 | 19.3% | 47.67 |
| packaging | Full source | 3 | 100.0% | 5653.00 |
| packaging | Graph | 3 | 68.1% | 1565.67 |
| packaging | BM25 | 3 | 40.6% | 1565.67 |
| packaging | Old graph | 3 | 0.0% | 443.00 |
| pluggy | Anchors | 3 | 12.7% | 29.00 |
| pluggy | Full source | 3 | 100.0% | 1666.00 |
| pluggy | Graph | 3 | 23.3% | 204.00 |
| pluggy | BM25 | 3 | 34.0% | 204.00 |
| pluggy | Old graph | 3 | 18.8% | 198.00 |

## 11. 全部已记录任务边界与负面状态

9/9 个当前任务图含有边界。缓存命中或覆盖已执行行都不会将 unknown 升级为 fresh。下表保留每个案例的锚点状态、全部边界类别计数、缺失锚点、旧片段状态和旧图校验结果，包括前版失败及动态生成代码位置。

| 案例 | Before → after | 见证行 | 生成代码位置 | 锚点状态 | 全部边界计数 | 缺失锚点 | 旧片段状态 | 旧图校验 |
|---|---|---|---|---|---|---|---|---|
| packaging-prereleases | False → True | 61 | 0 | unresolved=3 | unresolved=5 | {"after": [], "before": []} | changed_or_missing_spans=1, uniquely_unchanged_spans=1 | {"fresh": false, "status": "changed"} |
| packaging-specifier-iterable | False → True | 73 | 0 | unresolved=1 | unresolved=57 | {"after": [], "before": []} | changed_or_missing_spans=14, uniquely_unchanged_spans=6 | {"fresh": false, "status": "changed"} |
| packaging-metadata-keywords | False → True | 13 | 0 | unresolved=1 | truncated=17, unresolved=109 | {"after": [], "before": []} | changed_or_missing_spans=2, uniquely_unchanged_spans=1 | {"fresh": false, "status": "changed"} |
| attrs-makeclass-annotations | False → True | 533 | 3 | unresolved=2 | truncated=1, unresolved=37 | {"after": [], "before": []} | changed_or_missing_spans=11, uniquely_unchanged_spans=6 | {"fresh": false, "status": "changed"} |
| attrs-preinit-default | False → True | 609 | 5 | unresolved=1 | truncated=10, unresolved=65 | {"after": [], "before": []} | changed_or_missing_spans=19, uniquely_unchanged_spans=17 | {"fresh": false, "status": "changed"} |
| attrs-init-subclass | False → True | 400 | 6 | unresolved=1 | truncated=8, unresolved=87 | {"after": [], "before": []} | changed_or_missing_spans=28, uniquely_unchanged_spans=18 | {"fresh": false, "status": "changed"} |
| pluggy-set-blocked | False → True | 48 | 0 | unresolved=1 | unresolved=2 | {"after": [], "before": []} | uniquely_unchanged_spans=1 | {"fresh": false, "status": "unresolved"} |
| pluggy-registration-name | True → True | 39 | 0 | unresolved=1 | unresolved=26 | {"after": [], "before": []} | changed_or_missing_spans=2, uniquely_unchanged_spans=9 | {"fresh": false, "status": "changed"} |
| pluggy-call-extra | True → True | 126 | 0 | unresolved=1 | unresolved=15 | {"after": [], "before": []} | changed_or_missing_spans=1, uniquely_unchanged_spans=3 | {"fresh": false, "status": "changed"} |

## 12. 历史证据不改写

此前仅允许完整图复用的主实验，在 0/4 个开发仓库达到时间阈值，每轮自然锚点转换复用 0/480。该失败目标继续作为负结果保留。此后同数据 any-status 消融复用 364/480 次转换，但设计发生在主结果之后，属于探索性结果，不能作为留出确认。两者都不与新仓库留出数据混合统计。[历史主实验](RESEARCH_REPORT.md) · [探索性消融](ABLATION_REPORT.md)。

首次任务试运行因强制延迟注解改变上游执行语义，以及读取隔离不完整而失效。原始记录保留，但本报告不使用其任何覆盖指标。修正版本保留原始编译标志、限制读取、拒绝未验证字节码/原生模块、校验全部案例/重复/行身份、保存中断记录，并核对追踪/不追踪结果。这是公开说明的同样本修正，不是独立复现或新任务留出集。[无效试运行状态](../../benchmarks/task_evidence/results/initial/STATUS.md) · [执行修订](../../benchmarks/task_evidence/EXECUTION_AMENDMENT.md)。

## 13. 解释、局限与后续证据

固定样本上的狭义联合性能目标达到。逐仓库结果、源码改变分层、捕获成本及已观察到的 RSS 增加均属于结果。15/28 次源码相同转换有利于简单复用，围绕 release 的短历史并不代表一般编辑流。四个便利仓库、固定顶层锚点和有界解析器不足以推断总体效应。五条重复轨迹只描述时间波动，不是五个独立数据集；本报告不作置信或显著性宣称。

任务见证遗漏未执行分支及范围外的原生/生成行为。高召回可能来自宽泛类或模块片段，不能证明上下文最小或充分。等行数 BM25 不等于 token 或检索延迟相同。已有开发仓库、版本对选择和经审查的 fixture 替代限制外部有效性。内存记录包含新旧状态短时重叠及进程开销；八个版本不能证明无限运行稳定。

后续仍需独立人工任务上下文评审、更多仓库/时间留出、对照当前检索与失效方法的端到端编码任务、外部复现和独立新颖性论证。本报告提供可检查的工程实验，不是成熟论文、SOTA 结果或已部署系统。

## 14. 相关工作与官方方法来源

[Mokhov、Mitchell 与 Peyton Jones 的 Build Systems à la Carte（2018）](https://www.microsoft.com/en-us/research/publication/build-systems-la-carte/) 已建立依赖哈希轨迹与重建判断；[Tup ghost nodes](https://gittup.org/tup/manual.html) 已处理失败查找，[Bazel Skyframe](https://bazel.build/reference/skyframe) 说明输入登记和增量求值。本项目主张是有界领域的工程适配与评估，不是新的缓存或负依赖理论。

[ContextBench v3](https://arxiv.org/abs/2602.05892v3) 评估编码任务相关上下文，而此处执行见证并非人工相关性标签。[When Retrieval Hurts v1](https://arxiv.org/abs/2605.14478v1) 研究过期仓库上下文，此处不将过期上下文有害包装为新发现。本报告未复现两篇论文的模型实验。这些区别是本项目的审慎解释，不是论文作者对本项目的评价。[详细定位](RELATED_WORK.md)。官方 Python 3.12 追踪/tracemalloc 与 pytest fixture 文档已在相应测量边界引用。

## 15. 出处与离线再生成

留出环境：Python 3.12.2；Darwin；Apple M1 Pro；arm64；16.0 GiB RAM；单基准线程。任务环境：Python 3.12.2；Darwin；arm64。留出 source_dirty=True；任务 measured_inputs_dirty=False。运行时/辅助文件哈希及实际顺序保留在原始出处中。全工作树 dirty 标志与实测实现文件摘要描述不同范围。再生成报告前再次校验固定输入身份及保存结果的一致性。离线校验检查记录一致性和算术，不是新的源码执行或独立复现。

| 记录 | 身份 | Commit |
|---|---|---|
| Holdout run | holdout-20261004T211414735263Z | a0070ea71cea3c8944c004559602616114011b76 |
| Task run | bcebd88f-0906-4040-b3d3-e228f3f1a1df | a0070ea71cea3c8944c004559602616114011b76 |
| Holdout protocol SHA256 | a7eeb619d4e76c763bacc809f753135c3240544d82fc224e45b11a7d1121992d |  |
| Holdout manifest SHA256 | 126df30f4d69aa667b951ba1856dcb9b2ae03fba8d23e4a358e7127e936b7bc5 |  |
| Task manifest SHA256 | 4653503c6b5208f1c07c2535a97c76aaadfc08dc102f3beb5fc9b8463bfba2a4 |  |
| Task amendment SHA256 | 2d39a533f59a0ddf20448569ed24ba158877f5184659dbf87f1dddf2ca31c11c |  |

[Holdout raw / 留出原始数据](../../benchmarks/incremental_holdout/results/primary-20261004.json) · [Task raw / 任务原始数据](../../benchmarks/task_evidence/results/primary-20261004/runs.json) · [Task cases / 逐案例](../../benchmarks/task_evidence/results/primary-20261004/cases.json) · [Task provenance / 任务出处](../../benchmarks/task_evidence/results/primary-20261004/provenance.json).

```bash
python scripts/render_maturation_report.py
python scripts/render_maturation_report.py --check
```

这些命令只进行离线校验与文档生成。原始测量命令保存在输入记录中；新执行必须使用新的结果路径。精确第三方许可字节及源码固定版本保存在仓库归属记录中。

## 16. 在新环境与新结果路径复现

在仓库根目录使用新的 Python 3.12 环境。测量不要求开发依赖，运行测试套件时再安装。公开归档获取器需要使用正常 TLS 校验的 curl，按固定 URL、SHA-256 和字节数获取，不需要认证。已验证缓存可以复用；不一致归档会被拒绝。获取及解包都不执行上游代码。

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
# Optional integrity-test dependencies / 可选的完整性测试依赖
python -m pip install -e ".[dev]"
```

留出 all-suite 包括计时和两类内存测量。内存测量支持 macOS/Linux；运行时间取决于硬件和系统负载。prepare 使用现有固定清单填充仓库外缓存。必须使用新输出文件，不能覆盖保留的主结果：

```bash
python scripts/prepare_incremental_holdout.py --cache-dir ../holdout-inputs
python scripts/run_incremental_holdout.py run --suite all \
  --cache-dir ../holdout-inputs --output work/NEW_HOLDOUT.json
python scripts/run_incremental_holdout.py analyze --output work/NEW_HOLDOUT.json
```

适配后的上游断言执行器要求 macOS sandbox-exec，不能落实隔离预检时会拒绝运行。获取六个固定归档、验证并解包，再执行到新结果目录：

```bash
python scripts/fetch_task_inputs.py --cache ../task-inputs
python scripts/run_task_evidence.py --sources ../task-inputs --extract
python scripts/run_task_evidence.py --sources ../task-inputs --output work/NEW_TASK
```

两个实验执行器均保留失败或中断记录，不能将失败发布成完整成功汇总。这些是复现操作说明，不表示第二台机器已复现本报告测量。

[English](../en/MATURATION_REPORT.md)
