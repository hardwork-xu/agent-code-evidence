# 探索性消融：缓存并保留 unknown 图

本实验在严格完整性主实验自然复用为零**之后**设计，使用同一固定数据，
不是留出验证，也不把失败主假设改写成成功。仅移除完整性门槛，保留文件
读取集、目录、出处校验及所有 unknown/missing/truncated 状态。三种方法
在同一轮重新测量，每种一次预热、五条完整轨迹重复。

每轮候选策略复用 **364/480** 个自然锚点转换。所有所选图仍不完整，
这是少做重复计算，不是新增可认证为 fresh 的证据。规范序列化后的全部图输出与重建一致。
表格为毫秒中位数，正百分比表示更快、负值表示更慢。

## 全部转换

| Repository | Rebuild ms | Whole-corpus ms | Any-status ms | vs rebuild | vs whole corpus |
|---|---:|---:|---:|---:|---:|
| PyCQA/pyflakes | 5462.68 | 5470.93 | 5130.30 | +6.1% | +6.2% |
| Textualize/rich | 10261.46 | 6565.84 | 1115.28 | +89.1% | +83.0% |
| more-itertools/more-itertools | 647.73 | 645.71 | 524.19 | +19.1% | +18.8% |
| python-humanize/humanize | 393.32 | 269.34 | 190.30 | +51.6% | +29.3% |

## 仅源码改变的转换

| Repository | Rebuild ms | Whole-corpus ms | Any-status ms | vs rebuild | vs whole corpus |
|---|---:|---:|---:|---:|---:|
| PyCQA/pyflakes | 5462.68 | 5470.93 | 5130.30 | +6.1% | +6.2% |
| Textualize/rich | 6168.40 | 6156.81 | 652.75 | +89.4% | +89.4% |
| more-itertools/more-itertools | 647.73 | 645.71 | 524.19 | +19.1% | +18.8% |
| python-humanize/humanize | 237.84 | 236.80 | 158.74 | +33.3% | +33.0% |

## 首次捕获加完整回放

| Repository | Rebuild capture + replay ms | Whole corpus ms | Any status ms |
|---|---:|---:|---:|
| Textualize/rich | 12428.00 | 8752.27 | 3291.36 |
| python-humanize/humanize | 474.31 | 350.50 | 270.93 |
| more-itertools/more-itertools | 783.96 | 783.32 | 664.26 |
| PyCQA/pyflakes | 6550.06 | 6557.47 | 6223.23 |

这是同数据上的探索性机制消融，不能证明样本外性能、一般Python输入
登记完备性、语义安全、任务相关性、代码Agent收益或新的缓存理论。
本次消融尚未测量逐模块绑定摘要增量基线、驻留内存/RSS；后续见
[独立后续报告](MATURATION_REPORT.md)。仍哈希全部输入，读取集
与目录失效规则仍较粗。末表包含首次捕获，但不包含进程启动与会话构造。
主报告的零覆盖结果和未达效用目标保持原样。


- run_id: `ablation-20261004T200446Z`
- source commit: `67701873e42b6fbb79d60757ebc83cd1125de104`
- protocol SHA256: `a34c033ff773fcf9673ff60d21426fb9854073844110a6fad2f7e14911af58e7`
- [Raw / 原始数据](../../benchmarks/selective_reuse/results/ablation-20261004.json)
- [Protocol / 协议](../../benchmarks/selective_reuse/ablation-protocol.json)
- [Primary report / 主报告](RESEARCH_REPORT.md)

```bash
python scripts/run_selective_ablation.py --output work/NEW_ABLATION.json
python scripts/render_ablation_report.py work/NEW_ABLATION.json
```

Python 3.12.2; Apple M1 Pro; one benchmark thread.
