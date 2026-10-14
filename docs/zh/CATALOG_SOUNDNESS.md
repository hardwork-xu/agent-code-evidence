# 目录查询图回放的条件性正确性

本文审查
[`contextproof.reuse.GraphSession`](../../src/contextproof/reuse.py)
中的实验性目录模式，当前 `CATALOG_TRACE_VERSION = 1`。论证对象是缓存结果与这个
有界解析器的新建结果相同；它不证明 Python 运行时语义、agent 上下文的有效性、新的
增量计算原理或性能收益。基础 checkout 是
`ce6e36de7f6860296d66dadcb3105a8bbda9eb9a`；目录实现是其后的开发改动，不属于该
固定版本原有代码。源码和一手资料审查日期：2026-10-14。

## 假设与主张

用 `Build(S, id, A, P)` 表示从源码映射 `S`、提供方快照标识 `id`、固定锚点 `A`
及固定图策略 `P` 新建图。条件性主张是：获准复用后的完整 `canonical_graph_bytes`
应与当前源码、当前快照标识的 `Build` 相同。比较包括图标识、源码标识、策略、节点、
边、bindings、原因、unknown/truncated frontier 和最终 seal。

这个论证需要以下前提：

1. 调用方提供一致的源码快照。API 防御性复制并验证映射；复制混合时间的输入不会使它
   变成原子快照。
2. 会话期间解析器代码及版本、路径/别名规则、Python 解析行为、锚点、预算和确定性
   排序固定。在存活进程中更新解析器代码不属于这个契约。
3. 所有影响图的源码读取都被该图的源码集合覆盖，所有目录查询都经过两个记录入口。
4. 此用途中的源码 SHA256 相同意味着相关源码字节相同；论证排除相关哈希碰撞。比较
   哈希时，缺失源码路径有独立的不存在状态。
5. 缓存摘要只依赖自己的 `(path, source SHA256)`，保留既有静态守卫，并在回放时只读。
   AST 是私有且按只读约定使用的对象，并不是深度不可变的 Python 对象。
6. 调用顺序执行，内部状态可信。该会话不提供并发 API，也不接受或验证外部序列化证书。

完整读取覆盖是需要持续维护的前提，源码审查与反例为它提供支持；它不是形式化验证结果。

## 代码事实：两个可观察的目录操作

[`ModuleCatalog`](../../src/contextproof/catalog.py) 对去重后的排序路径应用原解析器的
字面规则：识别大小写不敏感的 `.py`、`.pyi` 后缀；把 `__init__` 折叠为包；
`src/pkg/x.py` 同时贡献 `src.pkg.x` 与 `pkg.x`；排除空模块名。候选成员在解析之前
独立构建，因此语法错误候选仍可造成歧义。精确答案保留路径身份和顺序，不只记录数量
或源码哈希。

| 操作 | 记录答案 | 保护的分支 |
|---|---|---|
| `_Corpus.module_candidates(name)` | 完整有序 tuple，包含 `()` | 包不确定性检查、缺失导入、歧义、解析失败、显式 binding 与 namespace fallback |
| `_Corpus.module_subtree_exists(name)` | Boolean，包含 `False` | 精确模块或任一带点边界后代是否存在，以及是否尝试 namespace 递归 |

子树谓词等价于旧表达式
`name in modules or any(key.startswith(name + '.') for key in modules)`。
点边界区分 `pkg.a` 与 `pkg.ab`。它不枚举整个子树：若答案持续为 `True`，且后续精确
查询不变，未读兄弟成员可以改变。未来若代码枚举后代，就必须记录枚举结果，不能继续
沿用这个 Boolean 契约。

审查在 [`dependencies.py`](../../src/contextproof/dependencies.py) 和
[`static_scope.py`](../../src/contextproof/static_scope.py) 找到以下消费位置：

- `resolve_module` 获取已记录候选，把所有候选路径加入源码读取，并在 fallback 前调用
  `module_lookup_uncertainty`。候选还决定歧义、解析状态和包 binding 分支。
- `module_lookup_uncertainty` 同样获取已记录候选，保留包 wildcard 与 `__getattr__`
  守卫。
- namespace 递归分支在规范化实际导入名之后调用 `module_subtree_exists`。所以 `src`
  内相对导入记录实际查询的规范别名，不记录原始 `.worker` 字符串。
- 源码包中剩余的 `.modules` 访问只有 `_load_texts` 创建防御性兼容副本；没有图解析
  分支直接消费它。审查测试还补充静态检查，禁止 resolver 与不确定性守卫绕过入口。

查询字典为每个不同 `(kind, name)` 保存一个答案。同一个不可变目录内，重复查询答案
相同，因此记录一次足以用于回放；它不是按执行顺序保存的轨迹。

如果原解析器在返回 module value、超出 qualified depth、词法/动态不确定性或 depth
budget 分支中尚未查询目录就退出，新实现保留这个顺序。真实空查询轨迹可以存在；缓存
不会为未执行的分支虚构查询。

## 代码事实：源码守卫与状态发布

[`build_graph`](../../src/contextproof/graph.py) 用 `lookup_paths`、所有给定锚点路径和
所有图节点路径完成源码读取集合。`resolve_name` 在失败 binding 检查前记录当前源码
路径；`resolve_module` 在不确定性、解析失败或 node-budget 退出前记录候选路径。
因此源码守卫也覆盖：

- 为负属性查找读取、但没有成为节点的包文件。
- 可能阻止 submodule fallback 的 wildcard、`__getattr__`、显式/动态 binding 和
  class-body `global` 守卫。
- 无法解析的候选，或已解析却被 node budget 排除的目标。
- 缺失锚点路径；该文件后续出现会改变源码状态。

目录相同不能代替这些读取。空 namespace 新增空 `__init__.py` 时，即使图字节暂时
相同也必须重建，以便在后续 `__getattr__` 或 wildcard 编辑前取得新包文件的读取依赖。
相反，depth-zero 图可以没有模块查询，并保留原来的 truncated frontier。命中不会把
unknown 图升级为 complete。

`GraphSession` 在构造时复制锚点，并持有自己的 depth/node 策略。每次更新仍复制和
验证完整源码映射，哈希所有给定源码字符串，并为新的目录模式构建当前目录。各守卫的
区别仅在目录接受条件：

| 模式 | 除 consulted-source 哈希不变之外的目录条件 |
|---|---|
| `incremental_read_set` | 历史规则：全部源码路径 key 相同 |
| `incremental_catalog_coarse_guard` | 有效空查询轨迹，或全部源码路径 key 相同 |
| `incremental_catalog_root_guard` | 每个实际查询的规范 root 下，完整 module/candidate 成员相同 |
| `incremental_catalog_read_set` | 每个已记录 exact/subtree 查询的答案相同 |

全部路径 key 相同时，目录模式可以跳过逐查询比较，因为目录是这些 key 的确定性函数；
源码哈希和轨迹有效性仍要核对。缺失轨迹、非字典轨迹或 root guard、缺失版本或不支持的
版本触发重建，不当作合法零查询证书。版本字段保护的是轨迹格式，不允许会话期间改变
解析器语义。

每个重建锚点先清空 `lookup_paths` 和 `catalog_queries`，结束后复制自己的观察。
复用图则复制先前的读取和观察。因此固定锚点可共用一个 corpus，却不共享观察字典。
候选答案与 root membership 值是 tuple；轨迹容器是私有复制字典，不是对外暴露的不可变
证明对象。

[`ModuleCache.for_snapshot`](../../src/contextproof/module_cache.py) 创建候选缓存，只
保留匹配当前哈希的摘要，包含解析失败摘要。所有锚点成功后，会话才发布哈希、图、源码
集合、查询轨迹、root guards、版本和候选模块缓存。第二个锚点失败时，上一已提交状态
仍可使用。返回图是深拷贝；回放修改副本的提供方快照标识并重新 seal。查询元数据和审计
计数位于 sealed graph payload 之外。

## 条件性回放论证

按上一成功构建实际发生的顺序考察读取。第一次读取时，固定局部输入及相同的 consulted
源码字节或目录答案产生同一 resolver 分支。归纳地，先前答案相同会产生同一局部状态、
下一查询及下一答案。重复查询由同一个已保存答案覆盖。源码局部摘要提供相同的已守卫
语法事实，所以递归、队列顺序、预算决定和错误/unknown 原因也相同。最终在提供方
标识与 seal 处理之前得到相同图内容。

细粒度守卫直接要求归纳需要的目录答案相同。粗守卫在全部源码路径 key 相同时蕴含这些
答案相同；真正零查询的执行不需要目录前提。root 守卫蕴含每个受保护规范 root 内 exact
与 subtree 答案相同，包含别名和负答案；empty-root 情况保守保护整个 module map。
三种模式都保留相同的 consulted-source 前提。

所以在这些前提下，复制旧图、替换 snapshot ID 并重新 seal，所得 canonical bytes 与
fresh reconstruction 相同。这甚至会保留解析器错误或不完整结果，不表示解析器描述了
所有 Python 运行时行为。

## 测试与尚未建立的证据

实现前验收规范包含 C01–C24。其可执行输入位于
[`test_catalog_reuse_review.py`](../../tests/test_catalog_reuse_review.py)：固定 fresh
预期、四模式守卫决定、别名/歧义、缺失 exact/subtree 答案、两次更新的 empty-init
读取依赖获取、解析失败、unknown/truncated 保留、多锚点隔离、mutation 隔离、证书
回退和失败回滚。C04/C05 检查实际查询 root 内的目录变更；C01/C02/C22 是零查询对照。

开发期间已成功执行独立审查测试。测试还识别了故意不健全的仅测试版本：忽略空 exact
答案、忽略 false/true subtree 答案、忽略包源码读取哈希或绕过不确定性守卫。守卫绕过
测试与事先保存的 guarded fresh graph 比较，避免 candidate 与 oracle 一起默默采用
注入的错误。这些版本只证明测试敏感性，不是支持模式或性能对照。

[`test_module_catalog.py`](../../tests/test_module_catalog.py) 另用历史字面 alias/subtree
表达式核对新索引；已有 reuse/index/oracle 测试提供兼容性覆盖。最终累计测试数应来自
完成的验证记录，本文不把部分运行相加。有限测试和源码审查支持上述假设，但不证明未来
resolver 改动全部被覆盖。新增目录消费必须扩展观察契约，或使用保守目录守卫。

相同 resolver 的 fresh reconstruction 是回放 oracle。独立运行时/语义标签、agent
任务结果及泛化能力需要另外的证据。本文不报告性能结果，也不主张已具科学研究成熟度。

## 已知思想与有限工程适配

以下一手资料于 2026-10-14 阅读。关系判断是本项目的解读，上游项目没有评价本实现。

- [TypeScript v5.9.3 `resolutionCache.ts`](https://github.com/microsoft/TypeScript/blob/v5.9.3/src/compiler/resolutionCache.ts#L89-L169)
  保留 failed lookup 与 affecting locations，配置目录/文件 watcher，并进行
  [失效处理](https://github.com/microsoft/TypeScript/blob/v5.9.3/src/compiler/resolutionCache.ts#L1535-L1588)。
  负查询失效已存在；本项目的有界 source-map 图 API 不复现其完整模块解析或 watch 服务。
- [mypy v1.18.2 `server/deps.py`](https://github.com/python/mypy/blob/v1.18.2/mypy/server/deps.py#L1-L71)
  用 trigger 连接受影响位置，并处理模块创建/删除。它也
  [记录缺失模块属性和 logical dependencies](https://github.com/python/mypy/blob/v1.18.2/mypy/server/deps.py#L626-L657)。
  先前不存在的名字后来出现，是 Python 工具已有的处理对象。
- [Bazel Skyframe](https://bazel.build/reference/skyframe) 要求登记依赖以维护增量正确性，
  区分 file state、contents 和 directory-listing values。这支持区分源码读取与目录
  观察，但不把 Bazel 的保证转移给本项目。
- [Tup 官方手册](https://gittup.org/tup/manual.html) 描述访问不存在文件的 ghost nodes，
  并把构建命令实际读取的文件登记为依赖。本项目的静态名字解析观察对象不同，但遵循已有
  的负依赖原则。

这次阅读没有产生编译器/构建系统 benchmark，也不是穷尽性的优先权检索。这里考虑的
贡献是带可审查观察覆盖和反例的有限工程适配，不是发明依赖轨迹、负依赖或细粒度失效。

[English](../en/CATALOG_SOUNDNESS.md) · [模块摘要设计](INCREMENTAL_DESIGN.md)
