## 追加：四个任务的确定性回放诊断

在上述 raw-only 审计后，主任务明确授权仅回放已发现缺行的任务，以查清原因。实际为4个独立任务、5个预算组合；不是5个任务。使用原提交 `2451b574856048f3d9dded1fc1f55f209241cdc2` 的未改动源码、Python3.12.2、同一封存issue哈希和源archive哈希，以及固定80/3/2/128与三预算。通过只读Python追踪观察原 `_pack` 的实际分支，不修改算法或返回值。

四个任务的全部72份上下文均与原预测的 payload SHA-256、blocks坐标顺序、consumed、status、delivered_lines、frontier_count一致。只在这四个任务中，复核了跨18组合的anchor ID/hash/坐标完全相同，且 graph候选包含所有anchors_only候选物理行。这里证明了这四个任务的候选不丢锚点；不是对其他35个任务候选侧车的独立复核。

五处缺行都在同一此前已接受源码块、同一将加入源码块下，因图元数据更长而触发整段拒绝；每处字段字节差相加均等于trial总字节差。没有实际改写元数据、提高预算或重测另一政策。

| 任务 | 预算 | 被跳过行数 | anchors trial | graph trial | 元数据增加 |
|---|---:|---:|---:|---:|---|
| huggingface__transformers-13865 | 8000 | 80 | 7970 | 8034 | frontier_summary +64 |
| huggingface__transformers-13989 | 16000 | 80 | 15976 | 16042 | candidate_span_count +1, frontier_summary +64, omitted_source_lines +1 |
| huggingface__transformers-13989 | 32000 | 2 | 31979 | 32046 | candidate_span_count +1, frontier_summary +64, omitted_source_lines +2 |
| huggingface__transformers-15913 | 16000 | 2 | 15963 | 16031 | candidate_span_count +2, frontier_summary +65, omitted_source_lines +1 |
| yt-dlp__yt-dlp-8917 | 8000 | 13 | 7992 | 8057 | frontier_count +1, frontier_summary +64 |

因此，候选层的“同锚点再展开”与最终交付层的包含关系需要区分。本轮包含全部实际元数据的预算是诚实的，但不同诊断长度与整段打包共同影响了源码交付；不能把两种payload的差异解释为纯粹图边带来的效应。此诊断解释了5处已观察到的缺行，不意味着图召回下降都由64–68字节的诊断造成；16KB的anchors_only recall本身已只有0.087563，graph为0.088981，而强词法基线为0.182344/0.186208，主要召回缺口已存在于三锚点限制后的输出。

修订下一问题：这五个案例的机制原因现在已经查清，不再写作“待确认是否元数据导致”。未来独立试验应预先冻结等价的元数据处理或显式将其作为机制消融，同时完整计费，并检验图的内容增量是否仍优于强同文件控制；不能在当前39例上改动表示后选择较好的结果。预算表示敏感性本身首先是评估有效性的限制，不应单独包装为原创成熟成果。

本追加是 **post-hoc deterministic replay diagnostics, not new holdout/independent validation**。读取了这四个现有问题与源文本用于原版本回放，CSV只投影 instance_id/problem_statement，从未使用patch标签或据此调参；保存的sidecar不含问题、源码或补丁正文。计时未作为新性能证据。所有封存prediction哈希在回放结束后重新核对不变。

产物：`postrun-packing-replay.py`（预检固定源码/数据/源manifest、逐任务串行回放、输出只允许新建）；`postrun-packing-replay-20261014/manifest.json`、4份任务诊断、`summary.json`。首次预检误选本地 `sources.json` 时立即停在哈希门，尚未读取issue或source；随后定位到与原manifest哈希精确匹配的既有 `public-source-manifest.json`。该过程保存在 `postrun-replay-preflight-note.json`，没有改动任何来源manifest。

