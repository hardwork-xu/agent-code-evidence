# 固定已知任务的执行验收

外部上下文 pilot 使用过的 39 个任务已经属于见过的开发输入。本阶段通过
真实上游程序验证原始回归标签，不能证明自主生成修复成功、必要上下文、
新的未见样本效果，也不能将 pilot 升格为成熟研究成果。

数据为 `AmazonScience/SWE-PolyBench_500`，固定版本
`546075b4b05d17ba914e72b8f4c6d5b1ea150c1d`，原始 CSV SHA256 为
`20961b616b404875adead16dd456adc4cf583035436fc0d7e9c3f2adf8322e0c`。
原 39 个任务全部保留：87 个 F2P、5,842 个 P2P 元数据标签。标签是断言标识，
不是相互独立的任务。

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

首个原生批次在源码、依赖、helper 和测试素材审查后冻结六个 yt-dlp 任务，
共 12 个 F2P、236 个 P2P 标签。其他原任务仍待真实运行验证；准备好源码
不等同执行完成。解释器、依赖文件、协议和失败单独保留，不混入旧定位
pilot。适配器单元测试通过不能推出任务效果或研究成熟度。

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
