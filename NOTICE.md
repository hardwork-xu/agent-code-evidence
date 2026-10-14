# Third-party source attribution / 第三方源码归属

ContextProof's own implementation is distributed under the root MIT license.
That license does **not** replace the licenses on upstream source excerpts,
adapted probes, or the HumanEval material distributed with the benchmark records.
ContextProof 自主实现采用根目录 MIT 许可；该许可不替代随实验记录分发的
上游源码片段、改编探针及 HumanEval 材料各自的许可。

The historical corpus license texts are retained unchanged in `third_party/licenses/`.
The later metadata-only study retains its licenses in
`benchmarks/selective_reuse/licenses/` (including the original `LICENCE` spelling).
`third_party/manifest.json` identifies each original repository, full commit,
license path, retrieval URL and byte digest. `third_party/inventory.json` indexes
published source spans, adapted probes, task IDs and the records containing them.
历史语料的未修改许可原文位于 `third_party/licenses/`；后续元数据研究的许可
位于 `benchmarks/selective_reuse/licenses/`，保留原始 `LICENCE` 拼写。两个 JSON 清单记录
固定提交、来源、原文字节哈希，以及源码片段、探针、题目和实验记录的位置。

| Upstream / 上游 | Material / 材料 | License / 许可 |
| --- | --- | --- |
| [attrs](https://github.com/python-attrs/attrs) | Source excerpts and adapted behavior probes / 源码片段及改编行为探针 | MIT |
| [HTTPX](https://github.com/encode/httpx) | Source excerpts and adapted behavior probes / 源码片段及改编行为探针 | BSD-3-Clause |
| [packaging](https://github.com/pypa/packaging) | Source excerpts and adapted behavior probes / 源码片段及改编行为探针 | Apache-2.0 OR BSD-2-Clause; both texts retained / 保留两种许可原文 |
| [pluggy](https://github.com/pytest-dev/pluggy) | Source excerpts and adapted behavior probes / 源码片段及改编行为探针 | MIT |
| [HumanEval](https://github.com/openai/human-eval) | First 20 task prompts/tests and derived API-drift inputs / 前 20 题的提示、测试及改编 API 漂移输入 | MIT |
| [Click](https://github.com/pallets/click), [ItsDangerous](https://github.com/pallets/itsdangerous), [MarkupSafe](https://github.com/pallets/markupsafe) | Earlier corpus source references and hashes / 早期语料的源码引用及哈希 | BSD-3-Clause |
| [Requests](https://github.com/psf/requests) | Earlier corpus and history source references/hashes / 早期语料和历史源码引用及哈希 | Apache-2.0; original ext copyright notice retained / 保留 ext 原始版权声明 |
| [urllib3](https://github.com/urllib3/urllib3), [Pydantic](https://github.com/pydantic/pydantic) | Earlier corpus source references/hashes / 早期语料源码引用及哈希 | MIT |
| [Babel](https://github.com/python-babel/babel) | Earlier corpus source references/hashes / 早期语料源码引用及哈希 | BSD-3-Clause |
| [filelock](https://github.com/tox-dev/filelock) | Earlier corpus source references/hashes / 早期语料源码引用及哈希 | Unlicense |
| [python-dateutil](https://github.com/dateutil/dateutil) | Earlier corpus source references/hashes / 早期语料源码引用及哈希 | Apache-2.0 OR BSD-3-Clause; upstream file states BSD applies to all code / 上游声明 BSD 适用于全部代码 |

The source excerpts belong to their upstream copyright holders, identified in
the retained license files. Excerpts were selected and rendered with source paths
and line spans; JSON/XML/Markdown escaping, budget truncation and selection do not
transfer authorship. Revision behavior probes are adaptations of identified
upstream tests/changelog behavior, not verbatim upstream tests or original
algorithm inventions. The HumanEval API-drift workload changes the calling
interface; it is not an official HumanEval score.
源码片段版权归保留许可中列明的上游权利人。片段经过选择并以 JSON/XML/Markdown
呈现，转义、预算裁剪与选择不改变作者归属。revision 行为探针改编自明确引用的
上游测试或更新行为，不是逐字上游测试，也不是原创算法。HumanEval API 漂移
实验改动了调用接口，其分数不等于官方 HumanEval 分数。

The old natural drift/graph studies distribute references, hashes and statistics,
not complete upstream source trees; their synthetic scope-audit fixtures are
ContextProof-authored. Their upstream license texts are nevertheless retained for
traceability and source-distribution completeness. Dependency hash inventories
are not vendored dependency source, and must not be treated as license texts.
旧自然漂移和图研究分发的是引用、哈希与统计，并未分发完整上游源码树；其中
合成作用域审计夹具由 ContextProof 编写。仍保留这些来源的许可原文以便追溯。
依赖哈希清单不是依赖源码，也不能代替许可原文。

See [third_party/README.md](third_party/README.md) for the precise scope and checks.
详见 [third_party/README.md](third_party/README.md) 的范围与检查说明。

The selective static reuse study adds [Rich](https://github.com/Textualize/rich),
[humanize](https://github.com/python-humanize/humanize),
[more-itertools](https://github.com/more-itertools/more-itertools) and
[Pyflakes](https://github.com/PyCQA/pyflakes): six fixed revisions each. Their
natural-source outputs contain paths, hashes, anchors and measured statistics,
not upstream source bodies. Original license files and source/archive digests
are retained in that study's `natural-manifest.json` and `licenses/` tree.
选择性静态复用研究增加 Rich、humanize、more-itertools 和 Pyflakes，各固定六个
版本。自然源码产物只含路径、哈希、锚点与实测统计，不含上游源码正文；原始
许可文件、源码和归档哈希保存在该研究的清单与 `licenses/` 目录中。

The repository holdout adds [Jinja](https://github.com/pallets/jinja),
[Starlette](https://github.com/encode/starlette), [AnyIO](https://github.com/agronholm/anyio)
and [Python-Markdown](https://github.com/Python-Markdown/markdown), eight pinned
revisions each. Jinja, Starlette and Python-Markdown use BSD-3-Clause; AnyIO uses
MIT. The 32 original license
files remain byte-exact under `benchmarks/incremental_holdout/licenses/`;
current and initial manifests preserve the unchanged source/anchor selection.
Only source metadata, graph hashes and measured statistics are published.
仓库留出研究新增 Jinja、Starlette、AnyIO 和 Python-Markdown，各固定八个版本。
32 份原始许可位于 `benchmarks/incremental_holdout/licenses/`，字节保持原样；
当前与初始清单保存未改变的源码及锚点选择。公开内容仅含源码元数据、图哈希与统计。

The execution-witness audit reuses six development-source revisions of attrs,
packaging and pluggy. Nine reviewed upstream tests are identified by pinned
paths, symbols, spans and hashes. Distributed records contain test parameters,
source locations and scored execution witnesses; the upstream test bodies and
source trees are kept outside the distribution. Ten exact root license files
are retained under `benchmarks/task_evidence/licenses/`, including packaging's
Apache and BSD texts. The project-authored extractor/worker is not an upstream
test implementation. The invalid pilot remains explicitly labeled and excluded
from the corrected primary evidence.
执行见证审计复用 attrs、packaging、pluggy 的六个开发来源版本，以固定路径、
符号、范围及哈希标明九项上游测试。公开记录含参数、源码位置及执行见证评分，
不含上游测试正文和源码树；十份完整许可原文位于 `benchmarks/task_evidence/licenses/`。
自行编写的提取器和执行器不等于上游测试实现。无效试运行保留明确说明，并排除在
修正后的主要证据之外。

These license trees accompany the source distribution. The wheel contains only
the ContextProof implementation and its own root license/notice, not benchmark
corpora or upstream test bodies.
以上许可目录随源码包分发；wheel 只含 ContextProof 实现及根许可与说明，不含实验语料。

The external edit-localization pilot uses AmazonScience/SWE-PolyBench_500 at
`546075b4b05d17ba914e72b8f4c6d5b1ea150c1d` (data card: MIT). Coordinate-only
reference-edit targets and measured statistics retain this attribution; original
issues, patches and repository source are not redistributed. The exact official
Amazon Science MIT text and39 exact-base root licenses are preserved under
`benchmarks/external_context/licenses/`. See `LICENSE_SOURCES.md` and `sources.json`
there for pins/hashes and the distinction between edit labels and necessary context.
外部先导实验使用固定SWE-PolyBench_500数据版本，公开参考编辑坐标及统计并保留原归属；
原始题目、补丁与源码不重新分发。MIT原文及39份固定base根许可保留在上述目录。
