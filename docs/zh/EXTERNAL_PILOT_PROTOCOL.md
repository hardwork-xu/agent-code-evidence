# 仅问题描述的外部编辑定位先导实验

冻结研究从 AmazonScience/SWE-PolyBench_500 的六个此前未使用的 Python 仓库选出39个真实任务。只使用仓库、语言、任务ID等元数据：每仓库按 SHA256(`external-context-20261013:` + instance ID) 升序取前10项。最终分布为1/10/10/10/2/6，少于原拟60任务，因此明确属于 pilot。

[协议](../../benchmarks/external_context/protocol.json) 在预测和标签评分前提交为 `aefdf06fc34f7c74434c67640e80128df350260a`。[预测前修订](../../benchmarks/external_context/amendments.json) 记录下载重试和 macOS RSS 监控。查询只含完整问题描述；提示、参考补丁、数据集test_patch参考测试补丁、修改节点元数据及人工锚点均不进入检索子进程。

## 输入与范围

数据卡明确声明MIT，固定数据版本为 `546075b4b05d17ba914e72b8f4c6d5b1ea150c1d`。每项使用确切 base commit，并校验根许可证。原始问题、补丁和上游源码保留在Git之外的本地缓存；公开结果只含任务ID、源码坐标、哈希和数值。由于仅本地作为数据读取且不重新分发源码，未穷尽核查所有文件内的第三方许可。

只评估文本补丁中旧版本Python删除/替换行以及被编辑的既有文件。实际补丁是一种真实修改，不表示全部必要上下文、语义充分性或本项目修复成功。纯插入没有删除行标签，行指标记为`null`；新增文件没有旧版本源码。无法读入语料的目标仍保留在分母中。预测失败在有目标时按空上下文保守计零分，语料是否可用的诊断仍标未知。

## 方法与公平预算

| 方法 | 候选源码 |
|---|---|
| bm25_windows | 固定、不重叠的80行窗口 |
| bm25_declarations | 既有最内层声明80行块 |
| anchors_only | 排名最高的三个不同声明锚点 |
| graph_expand | 相同锚点加可解析依赖图源码，深度2、节点上限128 |
| window_expand | 相同锚点及各锚点前后80行 |
| file_expand | 相同锚点及其文件中按BM25排序的窗口 |

全部方法共用确定性JSON打包器，预算为8000/16000/32000 UTF-8字节。完整问题、交付元数据和确切源码均计费；重叠物理源码行只发送一次。大声明先分段，预先确定的整段放不下时整段跳过。payload外诊断仅供审计，若额外送入模型必须计入字节预算。

主要终点为16000字节下按仓库宏平均的删除行F1，分别比较图扩展与两种词法基线。召回率、精确率、既有文件指标、每项实际字节开销和未解析边界为次要指标。观察单位是任务/仓库，不能把18个方法预算记录或计时样本当独立样本。不报告p值或显著性。

## 执行与核验

单工作进程只读校验过的源码包，不解压、导入或执行上游代码。冻结上限为5000个Python文件、32MiB Python总字节、单文件1MiB和每任务300秒。Linux采用4GiB地址空间硬限制；macOS每250ms采样RSS与4GiB比较，可能在采样间短暂超限，监控失效则显式失败。两种限制不能视为等价硬件条件。

预测要求干净的源码提交；真实渲染块逐一校验源码、字节和物理行去重。每项只写一次，全部预测先按哈希封存，独立评分命令随后读取补丁。评分校验全部冻结任务、六方法乘三预算的完整组合及仓库/base身份。所有失败和无目标案例保留。

```bash
python -m pip install -e '.[dev]'
python -m benchmarks.external_context.fetch --cache work/external-inputs
PYTHONPATH=src python -m benchmarks.external_context.runner predict \
  --dataset work/external-inputs/test.csv --sources work/external-inputs/sources.json \
  --output work/external-runs/my-new-run
PYTHONPATH=src python -m benchmarks.external_context.runner score \
  --dataset work/external-inputs/test.csv --run work/external-runs/my-new-run \
  --output work/external-runs/my-new-run/scores.json
PYTHONPATH=src python -m benchmarks.external_context.analyze \
  --scores work/external-runs/my-new-run/scores.json \
  --output work/external-runs/my-new-run/summary.json
python -m pytest -q tests/test_external_context_*.py
```

从干净Git检出运行；每次结果路径必须全新。压缩源码下载约1.24GB，另需本地工作空间；无需模型、API或GPU。复用匹配缓存，错误缓存字节直接拒绝。

预先规定的后续规划门槛：无完整性失败，至少4/6仓库图F1正向，分别相对两词法基线的宏F1绝对增益至少0.03、召回下降不超过0.02。达到只支持开展更大、未触碰的确认性研究，不证明智能体收益、新颖性或研究成熟度。失败则缩小声明；在这39项上调参后不能再称新留出集。

[English](../en/EXTERNAL_PILOT_PROTOCOL.md)
