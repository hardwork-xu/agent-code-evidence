# 已知39项任务的保留观测

这是已观测开发集的固定回归验收，不是新留出集、生成修复评测或成熟研究成果。

Snapshot UTC: `2026-10-15T04:55:22.063650+00:00`. INDEX SHA256: `06020b127bb16d3b8c2b28438ea3b613d683d550d35b8a3401f36eae695ec45b`.

原分母始终为39项任务、87个F2P标签和5842个P2P标签。标签及重试不是独立任务。

| 指标 | 数量 |
|---|---:|
| 保留的完整双侧条件 | 51 |
| 有双侧记录的不同任务 | 39/39 |
| 最新条件固定标签通过 | 30/39 |
| 保留的逐阶段观测 | 36008 |
| 不完整条件 | 1 |

最新完整双侧条件按协议冻结时间排序，不能挑选最好结果。完整双侧记录可能包含崩溃、缺失调用或跳过，不等于断言验证完成。F2P列为真实行为失败→通过数；P2P列为两侧实际通过数。

| 任务 | F2P | P2P | 最新状态 | Run ID |
|---|---:|---:|---|---|
| `Significant-Gravitas__AutoGPT-4652` | 1/1 | 0/0 | 固定标签通过 | `autogpt4652-v3-20261015T034214Z` |
| `huggingface__transformers-13865` | 1/1 | 8/8 | 固定标签通过 | `hf13865-v2-20261015T031813Z` |
| `huggingface__transformers-13989` | 0/5 | 0/29 | 未观测到测试调用 | `hf13989-minimum-offline-20261015` |
| `huggingface__transformers-15913` | 2/2 | 4/4 | 固定标签通过 | `hf15913-tokenizers0133-20261015` |
| `huggingface__transformers-19219` | 2/2 | 11/11 | 固定标签通过 | `hf19219-20261014T161318Z` |
| `huggingface__transformers-20136` | 1/1 | 124/124 | 固定标签通过 | `hf20136-numpy126-20261015` |
| `huggingface__transformers-27561` | 2/2 | 48/53 | 已调用但未通过验收 | `hf6-initial-20261015` |
| `huggingface__transformers-27717` | 0/1 | 11/87 | 已调用但未通过验收 | `hf6-initial-20261015` |
| `huggingface__transformers-31095` | 1/1 | 7/7 | 固定标签通过 | `hf31095-torch251-20261015` |
| `huggingface__transformers-3198` | 0/6 | 0/18 | 未观测到测试调用 | `hf6-initial-20261015` |
| `huggingface__transformers-7075` | 0/11 | 0/0 | 已调用但未通过验收 | `hf7075-six-configs-20261015` |
| `keras-team__keras-1767` | 1/1 | 11/11 | 固定标签通过 | `legacy-keras-20261015T032206Z` |
| `keras-team__keras-19284` | 1/1 | 23/23 | 固定标签通过 | `keras8-protocol-v1-20261015` |
| `keras-team__keras-19466` | 1/1 | 2330/2330 | 固定标签通过 | `keras8-protocol-v1-20261015` |
| `keras-team__keras-19826` | 2/2 | 2396/2396 | 固定标签通过 | `keras8-protocol-v1-20261015` |
| `keras-team__keras-19863` | 1/1 | 2/2 | 固定标签通过 | `keras8-protocol-v1-20261015` |
| `keras-team__keras-19915` | 3/3 | 38/38 | 固定标签通过 | `keras8-protocol-v1-20261015` |
| `keras-team__keras-19955` | 5/5 | 92/92 | 固定标签通过 | `keras8-protocol-v1-20261015` |
| `keras-team__keras-20002` | 2/2 | 13/13 | 固定标签通过 | `keras8-protocol-v1-20261015` |
| `keras-team__keras-20008` | 6/6 | 230/230 | 固定标签通过 | `keras8-protocol-v1-20261015` |
| `keras-team__keras-3983` | 1/1 | 12/18 | 已调用但未通过验收 | `legacy-keras-20261015T032206Z` |
| `langchain-ai__langchain-19331` | 4/4 | 0/0 | 固定标签通过 | `lang19331-v2-20261015T023445Z` |
| `langchain-ai__langchain-21201` | 1/1 | 9/9 | 固定标签通过 | `lang21201-20261015T031759Z` |
| `langchain-ai__langchain-4420` | 1/1 | 0/0 | 固定标签通过 | `lang4420-v2-20261015T033117Z` |
| `langchain-ai__langchain-5432` | 1/1 | 10/10 | 固定标签通过 | `lang5432-v4-20261015T033704Z` |
| `langchain-ai__langchain-5450` | 1/1 | 4/4 | 固定标签通过 | `lang5450-originalmodels-v2-20261015` |
| `langchain-ai__langchain-5625` | 1/1 | 26/26 | 固定标签通过 | `lang5625-v3-20261015T031913Z` |
| `langchain-ai__langchain-6456` | 2/2 | 9/9 | 固定标签通过 | `lang6456-20261015T031611Z` |
| `langchain-ai__langchain-6483` | 1/1 | 36/36 | 固定标签通过 | `lang6483-20261015T031647Z` |
| `langchain-ai__langchain-6765` | 1/1 | 0/0 | 固定标签通过 | `lang6765-20261015T031723Z` |
| `langchain-ai__langchain-7653` | 1/1 | 9/9 | 固定标签通过 | `lang7653-20261015T024859Z` |
| `tensorflow__models-2727` | 0/3 | 0/8 | 未观测到测试调用 | `tf2727-20261015T035839Z` |
| `tensorflow__models-4628` | 2/2 | 1/1 | 固定标签通过 | `tf4628-20261014T154926Z` |
| `yt-dlp__yt-dlp-1649` | 0/1 | 0/0 | 已调用但未通过验收 | `ytdlp-20261014T154046Z` |
| `yt-dlp__yt-dlp-3435` | 4/4 | 3/3 | 固定标签通过 | `ytdlp-20261014T154046Z` |
| `yt-dlp__yt-dlp-4524` | 1/1 | 102/102 | 固定标签通过 | `ytdlp-20261014T154046Z` |
| `yt-dlp__yt-dlp-4841` | 1/1 | 103/103 | 固定标签通过 | `ytdlp-20261014T154046Z` |
| `yt-dlp__yt-dlp-5933` | 4/4 | 4/4 | 固定标签通过 | `ytdlp-20261014T154046Z` |
| `yt-dlp__yt-dlp-8917` | 0/1 | 24/24 | 已调用但未通过验收 | `ytdlp-20261014T154046Z` |

0个P2P表示未提供保留测试，不代表全面无回归。测试call通过也不保证执行到目标断言；原测试的提前返回、模拟与结构性弱断言仍保留。逐阶段、逐标签、环境指纹和所有较早条件见公开gzip记录。

公开检查器重算记录与判据的一致性，不重新执行上游程序，也不独立认证私有原始日志或完整环境。

[Protocol / 协议](KNOWN_TASK_EXECUTION.md)
