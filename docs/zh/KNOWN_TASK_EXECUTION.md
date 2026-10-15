# 固定已知任务的执行验收

外部上下文 pilot 使用过的 39 个任务已经属于见过的开发输入。本阶段通过
真实上游程序验证原始回归标签，不能证明自主生成修复成功、必要上下文、
新的未见样本效果，也不能将 pilot 升格为成熟研究成果。

数据为 `AmazonScience/SWE-PolyBench_500`，固定版本
`546075b4b05d17ba914e72b8f4c6d5b1ea150c1d`，原始 CSV SHA256 为
`20961b616b404875adead16dd456adc4cf583035436fc0d7e9c3f2adf8322e0c`。
原39个任务全部保留：87个F2P、5,842个P2P元数据标签。标签是测试节点标识，
不是独立断言或任务；一个测试可能有多个断言，也可能在目标断言前返回。

每组使用数据集基线加原测试补丁，gold 组再应用原代码补丁。两组测试和
环境一致。独立 `git apply --check`/`git apply` 核验与另一字节解析器在全部
39 个变换上相等。两个 yt-dlp 数据集代码补丁未涵盖对应官方 PR head 的
其他改动，因此保留数据集衍生源码，不将整个 head 偷换成实验版本。

`benchmarks/known_task_execution/worker.py` 记录真实框架收集，只运行冻结的
元数据子集，保留各阶段报告，执行前后核验完整准备源码树，并核验实际
导入生产文件。已审查的套接字路径禁止出网或只允许 loopback。本程序是
环境适配器，不是操作系统安全沙箱或官方容器。原始堆栈和本地路径保留在
Git 之外。

`contract.py` 要求 F2P 在基线实际调用阶段发生行为失败、gold 实际通过；
全部 P2P 两组都必须在调用阶段实际通过。收集错误、缺失结果、skip、XFAIL、
XPASS、资源失败和未结束进程均不能证明合格。固定的无路径标签可以使用
显式绑定源码的别名；普通标签和参数后缀不能猜测。别名必须保持原方法名、
绑定源码字节，并在真实收集中精确存在。

这比固定官方 harness 仅检查不存在 P2P 失败的判据更严，属于非官方有限
回归验收，不等同官方 benchmark 分数。已阅读、未执行或复制官方源码
`amazon-science/SWE-PolyBench@9c836c5d7f3cb991934132b77d29e6941d912a07`。
其根 MIT 许可证与 Python 文件 CC-BY-NC-4.0 标头存在不一致；独立编写的
适配器不分发这些源码。数据集命令、Dockerfile 和安装脚本只是参考材料，
不能直接当作授权指令运行。

[自动生成的结果表](KNOWN_TASK_EXECUTION_RESULTS.md)记录全部原任务与保留的
完整双侧条件，包括收集失败和原生崩溃，区分“双侧记录完成”和“断言验证完成”。
最新条件按协议冻结时间排序，不选择最好分数；更早的失败和不完整条件仍保留。
解释器版本、依赖指纹、协议摘要和各阶段报告单独保存，不混入旧定位pilot。
适配器单元测试通过不能推出上游任务效果或研究成熟度。

适配器检查：

```sh
python -m pytest -q tests/test_known_task_execution_contract.py tests/test_known_task_execution_worker.py
python -m benchmarks.known_task_execution.contract --help
```

来源：[固定数据集](https://huggingface.co/datasets/AmazonScience/SWE-PolyBench_500/tree/546075b4b05d17ba914e72b8f4c6d5b1ea150c1d)、
[固定官方 harness](https://github.com/amazon-science/SWE-PolyBench/tree/9c836c5d7f3cb991934132b77d29e6941d912a07)。


源码旁的运行日志必须有固定源码哈希对应的具体文件许可清单，合计不超过
1 MiB。AutoGPT 原摘要测试还会间接调用周期日志；源码支持的
`OVERWRITE_DEBUG=1` 只固定输出目录。额外许可限于两批摘要的四个指定文件，
并绑定调用方、日志模块及测试源码证明。其他新文件、源码修改、符号链接、
硬链接或超限均使执行无效。日志正文留在私有目录。暴露遗漏日志路径的原
不完整条件保留，不重新解释为合格；自编适配器素材通过也不证明上游任务通过。


源码准备工具可在私有任务目录之外独立运行：

```sh
WORK="$(mktemp -d)"
CACHE="$WORK/cache"
python -m benchmarks.external_context.fetch --cache "$CACHE"
python -m benchmarks.known_task_execution.prepare --csv "$CACHE/test.csv" --cache "$CACHE" --task yt-dlp__yt-dlp-1649 --output "$WORK/yt-1649"
```

将CACHE和WORK设为Git之外的新私有目录。首命令下载固定公开输入，两条命令
都不执行数据集指令或上游程序。第二条生成只读base_tests、fixed_tests及完整
文件哈希。39任务的源码重建与原78份角色索引全部相同，覆盖137283文件、
2461434350字节；真实CLI也成功准备yt-dlp1649。这只验证源码重建，不是第二次
回归执行。31任务通用范围显式记录超过5MiB的未修改素材与非普通条目的省略；
TensorFlow使用已声明子系统Python/proto范围。全部补丁文件必须存在，缺失
必要测试素材仍使实际执行失败。

## 如何解释真实观测

每个条件内源码、运行环境和标签固定；更换兼容依赖必须另存明确冻结的新条件。
不能将有利子集混入39项原分母。运行使用Apple M1 Pro CPU或明确标记的x86_64
Rosetta、16 GiB macOS；没有可用Docker和CUDA。上游测试及CPU依赖门控串行
执行。冷热加载与环境差异使耗时仅具诊断意义，不能据此比较基线和改进性能。

即使标签通过，仍有下列解释边界：

- LangChain5450基线因`encode_kwargs`构造校验失败，没有执行归一化断言。
  gold使用真实预训练模型并通过原5项测试；只能说明接口行为，不能宣称归一化
  质量或嵌入质量提高。执行后更正将冻结文本的“原始锁”收窄为含原选定直接
  依赖的已审最小锁；原记录与更正同时保留。
- AutoGPT4652使用原测试的模拟摘要调用，真实执行消息历史源码及分词资源，
  不是真实商业模型调用。
- DINOv2包含跨框架skip；离线资源缺失时，部分源码分支可能提前返回。raw pass
  不能证明这些分支执行模型推理；未声称取得分支跟踪证据。
- 旧Keras3983显式用Theano、Python linker和`FAST_COMPILE`替代原TensorFlow
  后端；虽复现目标失败→通过，仍有5个P2P失败及1个原始skip，整项不合格。
- TensorFlow1.15 x86_64在Rosetta下于本机AVX检查中止，未观测目标断言；这是环境失败，不是
  F2P行为失败。
- 两项yt-dlp目标测试在声明的原生条件中基线已经通过；gold通过不代表复现F2P。
- OWL-ViT20136新兼容条件解决观测到的NumPy/Torch桥接失败，但bootstrap pip也
  发生变化，不是完全隔离的单变量因果实验；更早失败全部保留。

## 检查记录与重新执行不同

最新9项未合格任务均明确保留：

| 任务 | 保留的限制或负面观测 |
|---|---|
| yt-dlp1649、8917 | base目标已通过，未复现数据提供的F2P。 |
| Keras3983 | 目标复现，但明确的Theano替代条件仍有5项P2P失败、1项原跳过。 |
| Transformers27561 | 2项F2P复现，但5项原跨框架跳过阻止全部P2P合格；部分pipeline原始通过可提前返回而未推理。 |
| Transformers27717 | 未复现F2P；仍有protobuf/资源错误、IndexError和TF跳过。空进程拒绝记录不证明实际拒绝创建进程。 |
| Transformers7075 | base有11项TypeError，gold有11项原采样器pickle AttributeError；无数值内存性能结果。另有进程拒绝记录，不认定其导致pickle错误。 |
| Transformers13989 | 两侧实际源码进程中止且捕获日志为空，未观测到测试调用；AVX归因来自另一个可信TF门控失败的推断。 |
| Transformers3198 | 两侧缺boto3导致收集失败，完整Torch+TF运行时尚未验证。 |
| TensorFlow2727 | x86 TF1.15/Rosetta下两侧中止、零调用；生成proto也尚未准备完毕。 |

这些是实测失败或明确未验证条件，没有从分母中悄悄移除任务。本研究没有确立
原生源码构建替代方案可行或不可能。

在源码checkout中执行`python -m pip install -e '.[dev]'`后可运行上方源码准备
命令。控制端需要Python3.11+；独立目标worker支持明确测试过的Python3.7+
条件，3.7需要锁定元数据backport。worker只接受一个已审JSON配置文件路径，
必需字段和失败情形见`tests/test_known_task_execution_worker.py`。这是底层
适配器，不是自动安装器，也不执行数据集shell字段。真实重跑前必须另行审查并
冻结目标环境、源码清单、精确selector、插件、资源和限制。

公开传输检查器要求来自另一个可信提交的INDEX摘要，核对gzip、规范JSON身份、
两侧来源字段、逐阶段聚合及原判据。它不会重建私有清单、认证原始执行或重跑
模型与测试程序。包版本及已安装哈希不等于可移植wheel锁。本版本不宣称完整
历史容器复现或一条命令重跑全部39项；原源码、资源字节、私有日志和平台环境
准备保留在Git之外。公开CI不下载模型或执行这39项上游程序。

在源码检出目录可离线核验保留的公开观测及自动生成表格（Python3.11+，仅标准库）：

```sh
python -m benchmarks.known_task_execution.report --check \
  --bundle benchmarks/known_task_execution/results/known39-20261015 \
  --expected-index-sha256 06020b127bb16d3b8c2b28438ea3b613d683d550d35b8a3401f36eae695ec45b
python -m benchmarks.known_task_execution.secondary_report --check
```

53文件传输包及其捕获时`candidate`分类保持原样；该字段表示导出审核时的本地状态，
不表示当前GitHub发布或CI状态。[次级敏感性报告](KNOWN_TASK_SENSITIVITY.md)始终将
all39原主结果与事后筛选的30任务合格子集分开。

TF2.13.1 Rosetta依赖门控明确报告AVX限制；13989实际源码进程中止时捕获日志
为空。将源码中止归于同一原因是推断，不是引用源码日志。官方PyPI元数据也有
原生ARM TensorFlow替代轮子，但13989运行时要求`tokenizers>=0.10.1,<0.11`，
3198的setup固定0.5.2；可接受的旧版本没有适配现有原生解释器的官方ARM/
universal2轮子。源码构建未验证，不能仅因TensorFlow轮子可下载就称完整环境
可运行。[TF-macos2.13.1元数据](https://pypi.org/pypi/tensorflow-macos/2.13.1/json)、
[Tokenizers0.10.3](https://pypi.org/pypi/tokenizers/0.10.3/json)、
[Tokenizers0.5.2](https://pypi.org/pypi/tokenizers/0.5.2/json)。

## 根据证据推进研究

Keras提供5153/5842个P2P标签（88.2061%），仅两项Keras任务就占80.8970%；
6项任务没有P2P标签。39项来自6个便利抽样仓库，不是数千个独立研究样本。
汇总节点会掩盖此失衡，因此不以节点相互独立为假设报告置信区间。

本阶段检查测量工具和标签可移植性，不检验检索方法的收益。旧定位pilot的门槛
仍失败，global-binding自然样本仍为零覆盖增益。可检验的后续问题是：版本感知
证据能否在具有可观测下游行为的任务中改善成本与弃权的权衡。确认性实验前，
需冻结未见仓库/时间分割、源码兼容环境、强fresh-retrieval与全语料失效基线、
总成本和语义/下游指标。同时报告全选分母和单独标记的可运行子集，不将重试或
测试节点当新样本。这些是尚未完成的研究要求，不是已取得的研究成果。
