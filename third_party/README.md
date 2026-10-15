# Retained licenses and source index / 保留许可与源码索引

The historical inventory in this directory records 14 upstream projects at 42 fixed commits,
with 63 original
license/notice files. Files under `licenses/` were fetched at full commit SHAs on
2026-10-04 UTC and preserved byte for byte; existing frozen license hashes were
checked where available. No source tree, model, dependency runtime or personal
material is stored here.
本目录的历史清单记录 14 个上游项目、42 个固定提交与 63 份原始许可或声明文件。
`licenses/` 文件于 2026-10-04 UTC 按完整提交 SHA 获取，字节原样保留；旧语料中
已有许可哈希时同时核验。这里不存放源码树、模型、依赖运行时或私人材料。

## What is distributed / 实际分发内容

- `benchmarks/revision_tasks/frozen/tasks.json` contains selected before/after
  source anchors from attrs, HTTPX, packaging and pluggy, plus 30 adapted behavior
  probes. `tasks.py` defines those probes. Their upstream test paths and exact
  after-commit links appear in the index.
  该冻结文件包含四库修改前后的源码锚点及 30 个改编行为探针；`tasks.py` 定义探针。
  索引保留其上游测试位置与修改后固定提交链接。
- The two published `contexts.json` files contain selected source spans. Prompt
  replicas under `model-results/` repeat the source and probes; model outputs may
  quote them. Their file hashes and source scopes are indexed too.
  两份 `contexts.json` 含已选择的源码片段，`model-results/` 提示副本重复这些片段
  和探针，模型输出也可能引用。索引同时覆盖记录文件哈希与来源范围。
- `benchmarks/downstream/upstream/tasks.json` contains the first 20 HumanEval
  prompt/test records from commit `6d43fb980f9fee3c892a914eda09951f772ad10d`.
  `results/inputs.json` and downstream records contain adapted task material.
  The previously retained `upstream/LICENSE` matches the fixed upstream exactly.
  此文件含该固定提交前 20 道 HumanEval 题目的提示与测试；输入及结果含改编材料。
  原已保留的 `upstream/LICENSE` 与该固定上游字节一致。
- Earlier natural drift and graph reports publish source IDs, spans and hashes,
  rather than natural source bodies. All 13 library projects in those manifests,
  including 15 extra history revisions, are still covered by retained license
  text. The graph scope-audit code snippets are owned synthetic fixtures.
  更早的自然漂移与图报告发布源码标识、行范围、哈希，而非自然源码正文。
  其清单中全部 13 个库和额外 15 个历史提交也已保留许可原文；图作用域审计中的
  源码片段属于自行编写的合成夹具。

This is attribution for a source distribution. It does not claim all corpus
libraries were vendored, executed during this repair, or bundled in the wheel.
This is not an automatic legal compliance audit of arbitrary future material.
这是一份源码分发归属记录，不声称全部语料库均已被内嵌、在本次修补中执行，
或打包进 wheel；也不自动判定未来任意材料的法律状态。

## Reproduce the check / 复查

```sh
python scripts/check_attribution.py
python -m pytest tests/test_attribution.py -q
```

The checker works offline, verifies full license bytes and fixed URLs, reads
independent frozen manifest hashes, requires all declared source pins and license
files, and re-indexes the published excerpts and artifacts. A missing license,
new/changed covered artifact, unknown renderer, unsafe path or changed source pin
fails the check. It does not fetch or execute upstream code.
检查完全离线，验证完整许可字节与固定 URL，读取独立历史清单中的哈希，要求
所有声明来源和许可文件完整，再重建片段与制品索引。缺许可、覆盖范围内记录
新增或变化、未知渲染格式、不安全路径或来源提交改变均使检查失败；不会获取
或执行上游代码。

For a reviewed, intentional corpus change, inspect its source/license and then
run `python scripts/check_attribution.py --write-inventory`. Review the resulting
diff. Never add that flag to CI. The old raw files remain unchanged by this tool.
有意修改语料时，先审阅来源及许可，再执行上述 `--write-inventory` 并审查 diff。
不要在 CI 中启用该选项。此工具从不改写旧原始数据。

`inventory.json` lists rendered text hashes, upstream paths/ranges and artifact
locations. XML whitespace, Markdown fences and historical display escaping are
recorded explicitly; these hashes describe the distributed rendering, not a
claim that it equals the full original source file. A conservative source scope
on a record lists possible originating libraries; precise fragments are indexed
separately. Dependency hashes do not require bundling absent dependency code.
索引中的文本哈希对应分发时的呈现形式；XML 空白、Markdown 围栏和历史转义
会影响字节，不应把这些哈希当成完整上游文件哈希。记录的保守来源范围列出
可能涉及的库，准确片段另行索引。仅记录依赖哈希不等于分发了依赖源码。

`MANIFEST.in` includes this directory and `NOTICE.md` in the source distribution.
Source releases carrying benchmark excerpts must carry these files together.
The package wheel contains the ContextProof package, not the benchmark corpora.
`MANIFEST.in` 将本目录与 `NOTICE.md` 纳入源码包；含实验片段的源码分发必须同时
保留它们。wheel 包含 ContextProof 软件包，不含实验语料。

## Historical line-span limitation / 历史行号缺陷

Independent retrieval of 71 pinned source files checked 1,309 rendered excerpts:
748 matched the declared source span byte for byte and 544 differed only in
outer renderer whitespace. The remaining **17 Archex module-residue excerpts
are noncontiguous selections with misleading contiguous-looking `lines` values**.
Their nonempty lines were verified to occur in order in the original file;
they are not certified as exact contiguous source spans. Original experiment
records were preserved unchanged. The new index removes misleading range
anchors for these records and records their actual nonempty source-line groups.
独立获取 71 个固定原始文件并核验 1,309 个片段：748 个与声明行范围字节一致，
544 个仅有外层呈现空白差异；另有 **17 个 Archex 模块残余片段是非连续摘取，
但历史 `lines` 字段会误导读者以为是连续原始行范围**。其非空行已验证按顺序
出现在原文件中，但不能认定为精确连续出处。旧实验原始记录未改动；新索引
为这些记录取消误导性的 URL 行范围，并列出实际非空源码行组。

See `source-verification.json` for all source-file hashes and verification counts,
and `noncontiguous-excerpts.json` for each affected artifact, fixed revision,
reported lines, observed line groups and text digest. A successful offline
attribution check preserves this disclosure; it does not declare the 17 historical
citations correct.
全部源文件哈希与核验数量见 `source-verification.json`；逐项受影响制品、固定
提交、声明行号、实际行组与文本哈希见 `noncontiguous-excerpts.json`。离线归属
检查通过表示完整性和许可覆盖符合记录，不表示这 17 项历史引用行号正确。

## Later metadata-only study / 后续仅元数据研究

`benchmarks/selective_reuse/natural-manifest.json` adds four distinct source
projects and 24 revisions, with original license bytes under its `licenses/`
directory. The checker verifies source/archive hash formats, anchor-to-file
identity, adjacent first-parent commits and all 24 license texts, and scans the
study's JSON records for source bodies (including encoded JSON). Project-authored
`oracle_cases.py` is explicitly classified as a synthetic oracle. Unknown file
formats or source-body fields require a new review; performance result bytes are
not frozen by the historical attribution inventory.
此研究新增四个独立来源、24 个版本，其 `licenses/` 目录保留许可原文字节。
检查器验证源码与归档哈希格式、锚点文件一致性、连续第一父提交和 24 份完整
许可，并检查 JSON 记录（包括字符串内编码的 JSON）是否混入源码正文。
自写 `oracle_cases.py` 明确归类为合成判定器。未知格式或源码正文字段需要
重新审查；性能结果的字节不被历史归属索引锁死。

The natural source selection references an earlier protocol hash. Its later
pre-measurement amendments are explicitly listed in `protocol.json`, together
with `supersedes_protocol_sha256`. The checker reports both hashes and whether
the relationship is current or explicitly superseded; it never rewrites either.
This verifies the recorded relationship, not independent proof of amendment timing.
自然来源选择引用较早协议哈希；后续测量前修订在 `protocol.json` 中列明，
并保留被替代协议哈希。检查器输出两个哈希及关系状态，不改写其中任何一个。
这核验的是已记录的关系，不是修订发生时序的独立证明。

## Repository holdout and execution witnesses / 仓库留出与执行见证

The same checker also covers the 32 pinned Jinja/Starlette/AnyIO/Python-Markdown
revisions under `benchmarks/incremental_holdout`. It verifies all 32 exact license
files, pinned license URLs, and byte counts. Initial protocol/manifest hashes and
the unchanged repository objects must survive the recorded baseline amendment.
同一检查器覆盖新留出研究的 32 个固定版本及 32 份精确保留的许可，核验固定
许可 URL 与字节数。记录的基线修订必须保留初始协议、清单哈希以及未改变的
仓库、源码和锚点对象。

`benchmarks/task_evidence` uses nine reviewed upstream test identities from six
already-known attrs/packaging/pluggy revisions. The checker binds archive and
license declarations to their historical source pins, checks all ten full root
license files, and checks test URLs, spans, source hashes and anchor paths.
Ancillary documentation-license references in upstream metadata are not relabeled
as license bodies. Published parameters and witness locations are metadata;
upstream test/source bodies are not distributed. Its three Python support files
are explicitly reviewed project-authored extraction/scoring code.
任务见证研究使用来自六个已知 attrs/packaging/pluggy 版本的九项上游测试。
检查器将归档和许可声明绑定到历史固定来源，核验十份完整根许可、测试 URL、
范围、源码哈希和锚点路径。元数据中的许可文档引用不冒充许可正文；公开内容
是参数及见证位置，不分发上游测试或源码正文。三个 Python 支持文件是经过审阅
的项目自写提取与评分代码。

`task-evidence-pilot.json` records the five original JSON file hashes of the
invalid task pilot. Attribution validation rejects changed or missing pilot
bytes; its `STATUS.md` remains editable for explicit defect disclosures and must
retain the invalid-evidence label. There is no automatic inventory-update mode.
`task-evidence-pilot.json` 固定无效任务试运行的五份原始 JSON 文件哈希，归属
检查拒绝字节变化或缺失。`STATUS.md` 可继续明确披露缺陷，但须保留无效证据
标签；检查器不提供自动更新该索引的模式。

`python scripts/check_research_artifacts.py --require-results` additionally checks
the saved primary result grids, provenance, summaries and execution-control
records without downloads, source execution or measurements. It preserves failed
holdout attempts and the explicitly invalid task pilot without counting either
as successful primary evidence. These checks authenticate recorded relationships;
they do not rerun upstream tests or prove that archived measurements reproduce.
上述命令还离线核验主要结果的完整配对、来源、汇总及执行对照，不下载、不执行
上游代码、不重新测量。失败留出尝试与明确无效的任务试运行保留原样，但不计作
成功证据。记录一致性核验并不等于再次执行上游测试或复现实测结果。

## Prospective binding-observation inputs / 前瞻绑定观测输入

The eight-task study retains official source/test/version metadata and exact original
license/NOTICE text in `benchmarks/semantic_observer/inputs/prospective8-20261015`.
Original source/test bodies and dependency wheels are fetched independently. Four
small generated version-metadata outputs come from the actual declared upstream VCS
backend and retain their source/license provenance. Dependency alternatives, including
the offered Artistic License, are recorded as supplied and are not relabeled MIT.
The observer/comparison modules are project implementations; this is not a strict
clean-room claim or an attribution of upstream algorithms to the maintainer.

八任务保留官方版本、测试与许可来源；原源码/测试正文和wheel不重新分发。
四份实际后端生成版本元数据单列溯源，不作为手写替身；依赖原许可及其选项保留。
