# 显式函数全局绑定：设计与开发证据

解析器 **4** 在函数或类块可能通过 `global` 显式重绑定某个名字时，保守拒绝把它认定为固定模块绑定。这修复了一个单文件可靠性缺陷，不证明任意 Python 语义，也不证明解析加速或成熟研究成果。下面的自然面板中，**没有新增的受观察绑定改善**。

[English](../en/FUNCTION_GLOBAL_BINDINGS.md) · [自动生成结果](../../benchmarks/global_bindings/results/development-20261014/REPORT_zh.md) · [协议](../../benchmarks/global_bindings/protocol.json) · [固定输入](../../benchmarks/global_bindings/inputs.json)

## 问题与贡献边界

模块可以先定义 `x = 0`，让 `getter()` 返回 `x`，再由带有 `global x` 的 `writer()` 修改它。仅凭初始赋值，不能为任意后续调用建立固定绑定；旧解析器却可能选择该字面量声明。先前的 Scrapy 案例属于开发诊断，明确排除在新八仓库面板之外，不算独立确认样本。

单列的[已知 Scrapy 源码复核](../../benchmarks/global_bindings/development-diagnosis/scrapy-known-source-recheck.json)保留 `get_scrapy_root_handler` 的两个相关版本：受观察绑定从解析到初始值改为显式 global 不确定性，其他前沿仍存在。这是已知 getter 上的事后开发证据，不是两个新任务，也不是十锚点面板的收益。

修复检测**可能的显式 global 绑定写入**，保留原因为 `explicit function/class global write may rebind this name` 的 unresolved 边。只有 `global x` 声明、读取 `x` 或另一个词法块里的局部赋值，本身不会产生此标记。这是采用已有 [Python 名称绑定规则](https://docs.python.org/3.12/reference/executionmodel.html#naming-and-binding)的保守静态守卫，不宣称新的作用域分析原理。

## 遵循作用域的实现

调用链为 `_Corpus` 建索引 → `guard_module_bindings` → `_binding_scopes` / `_scope_global_writes` → `resolve_name`。见 [static_scope.py](../../src/contextproof/static_scope.py) 和 [dependencies.py](../../src/contextproof/dependencies.py)。

1. 枚举函数、异步函数与类块，记录所在类的名称改写上下文。
2. 在各块内收集 global 声明和可能的绑定写入；守卫覆盖的赋值、删除、导入、声明名称、循环/上下文管理器目标、异常目标、模式捕获及赋值表达式参与检查。
3. 分开处理嵌套函数/类体。默认值与被检查的其他定义时表达式按外围上下文访问；推导式迭代目标是局部名，推导式赋值表达式则可能写外围函数已声明的全局名。
4. 对声明和写入同时应用[私有名称改写](https://docs.python.org/3.12/reference/expressions.html#private-name-mangling)。在类 `C` 的支持场景中，`global __name` 对应 `_C__name`，不是模块中另一个 `__name`；类名前导下划线及不改写的双下划线结尾名称也有回归测试。
5. 在模块摘要入缓存前加入动态标记。直接证据与传递图共用绑定表，含缓存模块摘要。名字解析保留不确定性，不再选择初始字面量。

```mermaid
flowchart LR
  A[源文件与 AST] --> B[分离词法块与类上下文]
  B --> C[global 声明与可能写入取交集]
  C --> D[动态模块绑定标记]
  D --> E[直接证据与传递图查询]
  E --> F[各复用模式均保留 unresolved 边]
```

该处理限于单文件，不需要全仓库调用顺序模型。哈希/读取集复用可以保留这个 **unknown 输出**，不能将它升级成语义 freshness 证书。实现没有证明分支可达或函数会被调用，所以不可达写入夹具即使实测状态不变，也保持 unresolved；这是明确保留的精度代价。

## 版本与历史记录

| 对象 | 固定身份 | 含义 |
|---|---|---|
| 基线核心 | `09d6476ae5d42c9876d0df86b3b60dfa1c2ff048`，解析器 3 | 先前公开的研究核心 |
| 候选核心 | `99f09f4594e44fc0805b4d4a4599a0a6857490c3`，解析器 4 | 显式 global 写入修复 |
| 历史字节归档 | `affa59024f70cde86d2549b690204aa73ddccc7d` | 核心文件与基线指纹一致，不重标历史测量 |
| 最终基线运行 | `globals-20261014T134920Z-baseline` | 保留的开发记录 |
| 最终候选运行 | `globals-20261014T134921Z-candidate` | 相同输入与修订协议 |

[归档清单](../../research/frozen-catalog-20261014-source/SOURCE_MAP.json)把全部 23 个目录实验的核心/测量文件绑定到实测提交。历史目录报告显式核验该归档与封存运行；新目录测量仍要求**当前实现**匹配协议指纹，不能在核心改变后悄悄沿用旧实测标签。

解析器 4 拒绝旧图策略。升级后应重启进程内会话并重新捕获图。旧解析器 2/3 制品、原始协议与实测结果继续作为历史证据保留，不作为当前证书。

## 实际运行了什么

[配对原始记录](../../benchmarks/global_bindings/results/development-20261014/)包含每种引擎各 32 个自编夹具及 10 个固定自然锚点，运行环境为 Python 3.12.2 / macOS arm64。图运行器只执行固定自编夹具，上游源码仅按文本读取；选定的真实上游断言由另一审阅过的入口执行。

| 证据 | 实际结果 | 能支持的解释 |
|---|---|---|
| 20 个可能写入夹具 | 基线全部 resolved，候选全部保留 unresolved | 实测的保守绑定修复 |
| 12 个无写入控制 | 两引擎均保留支持的字面量绑定 | 此指定矩阵中不必要拒绝的控制 |
| 可能写入夹具的运行时检查 | 19 个发生变化，1 个不可达写入状态不变 | 运行行为与保留的精度代价 |
| 接口回归套件 | 跨公共接口和复用模式的 462 项参数化检查 | 派生案例，不是 462 项独立实验或准确率估计 |
| 八个新源码头 | 发现 1 个生产显式 global writer，保留 7 个零匹配仓库 | 零显式匹配不等于没有动态变更 |
| 十个自然锚点图 | 两引擎全部保持不完整/未知闭包 | 没有完整语义证书 |
| 三个 Pyparsing 受观察绑定键 | unresolved → unresolved，原本已受 wildcard 守卫保护 | 此面板**新增自然绑定收益为零** |
| 四个上游修复单位 | fixed 版本 43 断言通过，parent 15 通过、28 失败 | 四次改动，不是 43 个修复任务，也非候选效果 |
| Pyparsing 完整方法执行预检 | 23 个指定方法、200 次状态观察事件 | 已观察执行证据，不是候选收益或 200 次变更 |

43 项断言与 Pyparsing 预检结果在候选图测量前已经知道。两个 TrimArity 异常测试没有显式要求必须抛出异常，单凭通过不能证明异常行为正确。行/状态轨迹描述观察到的执行，不是必要上下文标签。初始执行失败保留在 [preflight-failures.json](../../benchmarks/global_bindings/upstream_execution/results/preflight-failures.json)。

## 协议修订与推断边界

两次修订都保留。[原 v1](../../benchmarks/global_bindings/protocol-original-v1.json)在两引擎图运行前修订，增加失败行保留、按源节点/表达式/操作配对观察边，以及拒绝不安全路径或错误引擎导入。[原 v2](../../benchmarks/global_bindings/protocol-original-v2.json)则在**首轮基线已运行后**修订：Unicode 分隔符不等于物理源码行，因此用物理 `source_lines` 替换 `splitlines()` 锚点切片。输入和锚点不变；[修订前首轮基线](../../benchmarks/global_bindings/results/development-20261014/amendments/first-baseline-before-line-fix.json)保留，随后两引擎都重跑。

最后修订前尚未运行候选自然面板图，但这仍不是 blind 或未见样本评估：基线和执行预检已被观察。自编案例属于开发回归；这个小型选择面板不能估计全仓库错误率、完整语义 soundness、下游代码收益或新颖性。本研究没有计时实验。

## 复现

按仓库常规说明安装项目及开发测试依赖。将固定上游文件准备在独立源码目录，并按固定输入定义逐项核验。以下 `sources` 是准备好的源码根；两个输出文件名都必须尚不存在。每个引擎角色须用**新进程**。

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m pytest -q tests/test_function_global_bindings.py
PYTHONDONTWRITEBYTECODE=1 python -m benchmarks.global_bindings.study --role baseline --source-root sources --output baseline-new.json
PYTHONDONTWRITEBYTECODE=1 python -m benchmarks.global_bindings.study --role candidate --source-root sources --output candidate-new.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m benchmarks.global_bindings.report --results benchmarks/global_bindings/results/development-20261014 --check
```

基线会导入固定字节归档，必须将归档当作只读目录。`PYTHONDONTWRITEBYTECODE=1` 防止生成 `__pycache__` 触发严格材料检查。输出以独占方式创建；不能把已发布文件指定为新输出。[上游执行输入](../../benchmarks/global_bindings/upstream_execution/inputs.json)和[审阅过的执行入口](../../benchmarks/global_bindings/upstream_execution/run.py)另行绑定来源、依赖、测试和许可证。


## 真实上游入口重放

独立入口已在九个新进程中实际重放：fixed43通过，parent15通过/28失败，
Pyparsing23通过并记录200个状态事件。这是已知执行预飞的复现，不是新增独立
任务，也不是归于图候选的收益。[可移植入口原始记录与索引](../../benchmarks/global_bindings/upstream_execution/results/portable-replay-20261014/)。

```sh
python3.12 scripts/prepare_global_execution_sources.py --source-root /tmp/contextproof-global-inputs --with-dependencies
python3.12 benchmarks/global_bindings/upstream_execution/run.py --source-root /tmp/contextproof-global-inputs --output /tmp/contextproof-global-execution-new
python3.12 benchmarks/global_bindings/upstream_execution/check.py
```

输入、输出必须位于Git之外，输出目录必须新建。准备脚本获取经过哈希固定的
免费公开源码和wheel；受审阅运行器实际导入上游源码并执行未修改断言。进程
隔离及路径、哈希检查不等于操作系统沙箱。原失败逐条保留。

## 尚存限制

该守卫没有建模任意 `exec`、`globals()` 改写、跨模块属性写入、别名、可变对象、原生扩展、monkeypatching 或完整调用顺序。支持的显式绑定写入不覆盖全部运行时副作用。新的注解/类型参数作用域及解释器差异需要独立覆盖，Python 3.12.2 的记录不能证明所有支持解释器上的行为。已有未知原因可能掩盖新守卫的增量作用，自然面板正体现了这个边界。

贡献是可测试修复及保留证据的评估工具。更广泛的独立语义验证、真实任务收益及外部复现仍是更强研究主张所需证据。CI 与完整包验收另外核验；生成本文本不证明它们已经完成。
