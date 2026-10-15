# Development log

This record describes actual work completed on 2026-09-21. ContextProof is maintained
by hardwork-xu with AI assistance for design, implementation, experiments, and writing.
It does not imply a longer development history, a separate engineering team, or an
independent human annotation study.

## 2026-09-21 — Initial prototype

**Problem and implementation.** Selected the problem of saved code evidence becoming
stale after repository changes. Implemented source scanning, Python AST chunks,
SQLite parsing cache, BM25, a small graph-expansion heuristic, complete-payload
budgeting, exact-text verification, conservative citation repair, CLI, and a
fixed-root MCP interface. The initial public milestone was v0.1.

**Contract decisions.** Used UTF-8 bytes as the default budget unit and counted
the complete rendered source payload. Whole chunks that did not fit were omitted.
Original exact locations took precedence over identical copies; displaced text
required a unique whole-line match for repair. Changed, missing, ambiguous, and
unsafe evidence was explicitly invalidated. Hashes were described as integrity
checks, never as signatures or semantic-equivalence proofs.

**Initial measurements.** Froze version pairs for Click, ItsDangerous, and MarkupSafe;
recorded 118 natural-drift observations, seven controlled transformations, and
84 retrieval runs from fourteen queries, two methods, and three budgets. Graph
expansion performed worse than BM25 at 2,000 bytes, tied at 4,000, and better at
8,000 on this small query set. The mixed result and limited Pallets-only sample
remain in the [earlier report](../benchmarks/results/latest.md).

## 2026-09-21 — Complete v1 project scope

**Scope correction.** A runnable prototype was an intermediate milestone. The
[completion contract](COMPLETION.md) expanded the deliverable to an end-to-end
capture/check/refresh workflow, direct dependency diagnostics, broader frozen
evaluation, executed downstream tasks, reporting, and reproducible documentation.
Positive experimental findings were not made a completion requirement.

**Product workflow.** Added bound context artifacts containing a source bundle and
separate dependency sidecar. Added `capture`, `check`, `refresh`, and offline `report`
commands, preserving the source-only API and expanding MCP to eight tools. A small
original demo changes a tax-rate helper while its caller remains text-identical;
its three reports show reuse, retrieval after the dependency edit, and reuse after
refresh. The report is self-contained and uses no external assets.

**Dependency contract.** Implemented supported direct Python definitions, literal
constants, and import-binding witnesses. Aliases and supported re-exports retain
binding identity; ambiguous, external, dynamic, or unsupported references abstain.
The resolver remains one hop. Sidecar bytes are measured as additional overhead,
not hidden inside the source bundle's stated budget. All 34 predeclared controlled
cases matched; none of the twelve stale or twelve unresolved cases was accepted
as fresh. Seven-repetition timing and source-scan scaling measurements were retained
in the [dependency report](../benchmarks/results/dependencies.md).

**Broader frozen study.** Recorded a protocol before source acquisition, sampling,
annotation, or predictions. Pinned two versions each of ten Python libraries from
ten GitHub owners. Selected thirty snippets per repository using before-version
information only, with seven development and three holdout repositories. Both
engine and a separately implemented byte-offset reference received the same frozen
source policy. The resulting 300/300 agreement is reported as scoped contract
agreement, not human-labeled accuracy. First-run predictions and all artifact
hashes are preserved.

**Blinded cross-check.** A separate AI reviewer inspected selected source evidence
without reference labels or engine predictions. A disclosed protocol amendment
increased coverage before predictions and review; the sealed 21-item check agreed
on every item. Its limited, purposive AI-review status is explicit in the
[comparison](../benchmarks/v1/review_comparison.json).

**Corpus-boundary correction.** Inspection of the first drift results found that
23 dateutil tests labeled deleted had moved outside the registered library prefixes,
while exact unique matches survived elsewhere in the newer archive. The primary
labels were retained as scoped outcomes and prominently identified as corpus exits.
A separate posthoc all-Python-scope sensitivity kept the same 300 samples and changed
exactly those 23 labels to relocated. Both primary and sensitivity results remain
available; the wider search was not presented as a new prospective holdout test.

**Natural dependency diagnostics.** Applied witness checks to the same frozen drift
samples and recorded repeated measurements and sidecar sizes. Interpretation keeps
source-anchor changes and moves separate from changes to a direct target or import
binding. The source reference does not label dependency behavior, so additional
flags are diagnostics rather than measured semantic detection accuracy.

**Executed model study.** Froze HumanEval IDs 0–19 with controlled request-decoder
API adaptations, three context policies, complete prompts, a native Qwen context
cap, one attempt per condition, and one pinned local 1.5B model. Downloaded the
model through a disclosed mirror after direct access failed, recorded every file
hash, and ran without a paid API or uploading source to a model service. The model
ran all sixty cells; every condition scored 0/20. Fifty-four outputs invented a
nonexistent module, while the remaining six had decoder/name/argument errors.
There were no hidden retries, replacement models, or selected favorable examples.

**Harness controls and publication hygiene.** macOS Seatbelt preflight checks
confirmed the execution boundary; AST/import restrictions and resource limits
provided additional controls. All sixty outcomes reproduced on replay. Post-run
known-good algorithms passed 20/20 using current APIs, while obsolete APIs passed
only the five unchanged tasks. Canonical algorithms never entered model inputs.
Local diagnostic paths were redacted in a separate publication step; unredacted
originals, raw/public checksum pairs, and byte-identical frozen prompts were preserved.
The [downstream report](DOWNSTREAM.md) states the null conclusion and its limits.

**Final documentation and verification.** Replaced the proposed-work roadmap with
an evidence-linked completion matrix. Added the technical report, bilingual v1
entry points, explicit budget boundaries, and a demonstration screenshot. Local
checks cover contracts, malformed inputs, source-policy boundaries, CLI/MCP flows,
packaging, and artifact integrity. Release verification and remote CI remain
observable in [GitHub Actions](https://github.com/hardwork-xu/agent-code-evidence/actions)
and [Releases](https://github.com/hardwork-xu/agent-code-evidence/releases); this log does
not freeze a changing test count or assert a remote status before it is recorded.

## 2026-09-21 — Versioned graph evidence and real revision evaluation

**Value audit and corrected scope.** The prior small-model study could not answer
whether useful source improved a capable model. Reviewing current primary sources
also showed that graph retrieval and incremental dependency reuse are established.
The project now focuses on source identity, explicit uncertainty, auditable version
transitions and exact transport contracts. No novelty or general-agent success is
inferred from test counts.

**Delivered source.** Added immutable Git-object reads, bounded transitive Python
evidence, durable full-graph handles, exact field deltas, and complete model-payload
budgeting through CLI and the official MCP SDK. A changed supported helper now
appears in delivered source when the allowance permits it. Reads verify blob IDs,
reject unsafe paths and deny lazy fetching or repository-configured remote commands.
The generated three-hop demonstration checks source delivery and reconstruction.

**Counterexamples and failed approaches.** An independent AI-assisted review found
eight concrete scope/binding cases incorrectly treated as fresh. Resolver v2 fixes
them conservatively in both graph and direct-witness APIs; old graph versions must
be recaptured. All fixtures and original outcomes remain public. The initial
renderer overflowed its budget with diagnostics, and persisted JSON ASTs lost to a
fair shared-cache baseline. Compact bounded diagnostics and default in-memory reuse
replace those designs; original measurements remain separately versioned.

**Capable-model comparison.** Froze 30 real upstream-derived API probes, 5 for
development and 25 held out, with executed version-specific oracles. After a 5/5
development gate, published inputs preceded all 150 held-out completions across
six context conditions. Stale source scored 8/25; graph, current supplied source
and BM25 each scored 24/25; Archex scored 21/25. The graph tied the same-anchor
source comparator while using more input tokens. Its advantage over stale source
does not establish a unique retrieval benefit.

**Versioned sensitivity and publication.** Corrected graph contexts were separately
frozen and all 25 rerun; all answers matched the original graph run, still 24/25.
This post-freeze sensitivity is exploratory, with 125 original comparator results
reused. Public exports retain every answer, failure, timing and usage record. Raw
local logs and personal records stay outside Git. Release building now checks
archive ownership, public maintainer metadata, content hashes and personal paths.
See the [measured report](GRAPH_REPORT.md) for final engineering replay and paired
model results, methodological limits and reproduction records.

## 2026-10-04 — static contract correction / 静态契约修正

An independently reproduced class-body `global` rebinding counterexample returned
`fresh=true` under resolver 2 despite changed runtime output. Resolver 3 retains
uncertainty for explicit writes paired with a global declaration in the same
class scope. It rejects old graph versions and requires recapture. The new
regression suite checks assignments, imports, deletion, nested scopes and
unrelated class controls. This is a bounded static-contract correction, not a
claim of general Python semantic soundness.

独立复现的类体 `global` 重绑定反例在解析器 2 中误判为 fresh。解析器 3
保留显式写入的不确定性，并要求旧图重新捕获；不宣称一般 Python 语义安全。

Source inspection also identified resolver reads that do not appear as graph
nodes: package files checked before submodule fallback. Optional read-set
collection now records these files for the subsequent experimental reuse path.
路径查找依赖还包括未成为图节点的包文件，读取集会记录这些依赖。

Validation: `pytest -q tests/test_static_scope_research.py` (41 passed), plus
independent frozen adversarial cases; full validation is recorded separately
against the final source hashes. No historical experiment results were replaced.

## 2026-10-04 — primary replay and exploratory extension / 主实验与探索扩展

Commits `b30d3e5`, `873c2ed`, `05c5312` and `b25b3d4` record the actual resolver,
certificate, validation and preflight corrections. Initial source preparation
failed to recognize the British license filename `LICENCE`; the downloader was
corrected. Initial primary startup rejected duplicate overload anchor IDs before
any timing; the original manifest and failure are retained. Neither case was
silently deleted. / 真实过程包括 LICENCE 文件名识别和重载锚点去重修复，保留失败。

The fixed primary run `selective-20261004T195433Z` emitted 630 timing records and
9720 graph outputs with matching bytes across methods. It did not meet its
utility target: 0/480 natural anchor transitions were selectively reused, with
zero complete sampled graphs in all 24 natural snapshots. The report is rendered
from raw results; no target or sample was changed after observing this result.
主实验未达到目标，完整性门槛在这些自然样本中没有覆盖；报告直接来自原始数据。

A separate `ablation-protocol.json` was then frozen for unknown-preserving graph
memoization. It is explicitly exploratory and uses the same data; it is not a
holdout or a rescued primary hypothesis. The default policy remains unchanged.
An independent 88-test suite checks retained unknown/truncated/missing states
and byte parity before timing this new mode. / 后续消融独立记录，不冒充主假设成功。

Attribution inspection found 17 historical noncontiguous excerpts with misleading
contiguous spans. New provenance indexes record them without changing old model
outputs or scores. Full license texts are included in source distributions.

The separate run `ablation-20261004T200446Z` retained 364/480 natural graph
transitions without changing their unknown states. Contemporaneous whole-corpus
baselines were rerun; the per-repository reductions are in the generated
`docs/en/ABLATION_REPORT.md` and Chinese counterpart. This exploratory result
is not substituted for the failed primary hypothesis. / 消融结果独立保留，未替换主结论。

Final local suite: 984 passed, 2 skipped because optional tiktoken was absent;
Ruff and source-attribution checks passed. Docker is unavailable on this host.
Remote CI for this research branch has not been run. / 本地检查与远端CI明确分开。

## 2026-10-04 21:02 UTC — incremental baseline and held-out protocol

The reviewed research branch was published as draft PR #4 at `41f8099`.
CI run `37233127334` passed all five jobs, including isolated builds and optional
tokenizer/MCP integration. Six public files were anonymously read back and matched
local hashes. / 草稿PR与远端CI已回读核验，未合并或发布正式版。

Added process-private guarded module summaries keyed by path/source hash,
transactional current-version retention, and three incremental replay modes.
The combined whole-corpus guard is the primary simple comparator; unchanged input
can reuse graphs without paying for graph reconstruction. Source-local guards and
negative-lookup invalidation remain part of correctness tests. The focused combined
baseline/historical-runner regression command passed 103 tests.
新增逐文件摘要和组合基线；保留已有模式与历史原始结果。

Before any held-out graph/timing measurement, four new repositories, eight
contiguous versions each and 24 anchors each were pinned. Source-only preparation
found 15/28 transitions with identical included source. The initial protocol and
manifest are retained; an explicit premeasurement amendment adds the incremental
whole-corpus comparator and makes it the primary timing/RSS baseline. No source
version, anchor, threshold or transition was removed.
源数据检查促成测量前基线加强，未按性能结果换样本。

Memory measurements use separate fresh subprocesses for uninstrumented RSS
and tracemalloc, never mixing profiler times with ordinary timing. Independent
harness review found and corrected group-label inconsistencies, weak provenance
binding, missing policy forwarding and unvalidated peak/worker identities before
any held-out measurement. / 计时与内存剖析分开，独立复核问题在正式测量前修复。

## 2026-10-04 21:13 UTC — committed task execution study / 固定版本任务执行研究

Commits `ad30815`, `0fd20c3` and `a0070ea` record uncached-reference parity,
pin-binding integrity checks, incremental design and the corrected task harness.
The heldout validator now binds decoded protocol/manifest objects to their hashed
files, rejects incomplete grids, and checks every cached output against a freshly
parsed per-snapshot corpus. A three-revision counterexample verifies that cached
module summaries still register negative reads when rebuilding a changed anchor.
The focused validation passed 283 tests. / 无缓存参照、版本绑定与负读取回归已验证。

A pre-commit task pilot incorrectly inherited postponed-annotation compiler flags.
Independent review also found insufficient sandbox read restrictions, possible
bytecode overrides, incomplete-grid acceptance and missing interruption records.
The pilot remains byte-preserved and explicitly invalid for research conclusions.
The corrected harness retains original future flags, rejects unverified import
artifacts, validates complete case identities and atomically records each child.
It adds independent traced/untraced controls before the corrected committed run.
首次试跑存在编译语义与执行完整性缺陷；原始记录保留并标记无效，没有静默覆盖。

The full local suite before the final provenance-only addition passed 1387 tests,
with 2 optional tokenizer skips. The final task-focused suite passed 35 tests.
The corrected run `bcebd88f-0906-4040-b3d3-e228f3f1a1df` at `a0070ea` completed
72 isolated child executions; all nine cases had repeatable outcomes and matching
traced/untraced assertions. Seven old-version cases failed while their new-version
assertions passed; two were stable. These are release-pair observations, not
causal attribution to individual patches. Source/runtime hashes remained unchanged.
The global worktree was dirty because attribution/CI files were being edited;
the measured-input dirty flag was false. / 实验源码已提交，非实验文件改动如实记录。

Witness recall is 53.9249% for graph context versus 37.4493% for matched-line BM25,
with the same mean 1168.78 supplied physical source lines. Pluggy reverses the
aggregate ordering. All nine graph closures remain incomplete. This is
task-conditioned execution coverage, not gold-context sufficiency or model benefit.
The corrected run's numerical recall happens to match the invalid pilot; this
does not retroactively validate the pilot or create an independent holdout.
任务指标来自实际执行行，不能解释成代码修复成功率或依赖闭包完整。

The next heldout timing/memory run starts from the same committed runtime, with
other task-owned tests/builds paused. Its outcomes are recorded separately.

## 2026-10-04 21:34 UTC — repository holdout completed / 仓库留出实验完成

Run `holdout-20261004T211414735263Z` completed at 21:34:24 UTC from measured
commit `a0070ea`, retaining 32 uncached snapshot references, 960 timing rows and
144 separate memory processes. All 23040 timed graph outputs and 27648 memory-run
outputs matched their uncached references; all 768 reference graphs remain
incomplete. Five trajectory repetitions per method/repository are retained.
144 个内存进程与计时分开；一致性不代表静态闭包完整或一般语义可靠。

Against incremental indexing plus whole-corpus-equality reuse, the candidate's
median replay reductions were 34.7% (Jinja), 55.8% (Starlette), 39.6% (AnyIO) and
33.4% (Markdown). All four met the fixed 20% threshold. Candidate uninstrumented
RSS medians ranged from 56.31 to 70.25 MiB and passed the 2x/512-MiB gates. AnyIO
used 1.026x baseline RSS; no across-the-board memory improvement is claimed.
Source-identical transitions, capture costs, all six methods and full min/max
ranges are reported. The previous failed strict-completeness hypothesis remains
unchanged. / 四库达到本次目标，不改写原严格完整性实验的失败结论。

The corrected task report also exposes a graph-under-anchor case and a Pluggy
case where BM25 covers substantially more executed lines. Original test URLs,
invocation counts, exact licenses and both execution modalities are linked.
A source downloader was independently exercised in a fresh external cache and
then reused offline; all six archive hashes/sizes matched, with no source execution.

Final local suite after publication integration: 1424 passed, 2 optional-tokenizer
skips. Ruff, source attribution, strict raw-result validation and deterministic
bilingual report checks passed. Package build and remote CI are separate gates
and are recorded after their actual outcomes. / 本地验收不替代构建和远端 CI。

## 2026-10-05 — offline summary portability correction / 离线汇总跨版本修正

The first CI attempt for `2b47129` passed four of five jobs; Ubuntu/Python 3.11
failed the offline task-summary comparison. The retained Pluggy BM25 macro recall
is `0.33987077737077737`, while left-to-right float summation on Python 3.11
recomputes `0.3398707773707774`: exactly one ULP apart. Python 3.12 changed the
[`sum` float algorithm](https://docs.python.org/3.12/library/functions.html#sum).
Local Python 3.11.3/3.12.2 readback isolated this single difference; integer counts,
per-case metrics, source records and experimental outcomes did not differ.
首轮远端 CI 的五项任务通过四项，Python 3.11 因浮点求和的最后一位差异拒绝
已保存汇总；不是实验结果或原始执行记录发生变化。

Only the offline reader now accepts either explicitly recomputed `math.fsum` mean
or explicitly recomputed left-to-right mean for each `macro_recall`. No tolerance
interval is used; even the next adjacent float outside those exact values is
rejected. Other summary structure, counts, context sizes and per-case arithmetic
remain exact checks. The measured aggregation writer, worker, resolver, protocols
and raw result bytes remain unchanged, including the original provenance hashes.
修正只作用于离线读取：接受两种明确求和算法各自导出的精确值，不采用宽松误差
范围；结构、整数、上下文行数及逐案例指标仍须精确相符。原实验代码路径与数据
不改写，也不以新检查器的文件哈希替换已记录的测量哈希。

All 48 focused task/portability tests passed, including both historical encodings,
adjacent-float tampering, nonfinite/bool values and unchanged strict fields. Ruff
passed. Strict artifact validation passed on local Python 3.11.3 and 3.12.2.
The new commit still requires its own remote CI; the failed first attempt remains
part of the record. / 本地修正验证通过，新提交的远端 CI 须另外确认。

## 2026-10-13 — research claim audit / 研究声明核验

Recomputed the frozen four-repository holdout and nine-case task records without
rerunning either experiment. The claim ledger distinguishes replay parity and
recorded cost reductions from natural-code semantic certification, task relevance,
agent benefit, novelty and external validation. Same-data supplementary analysis
reports executed-witness density and source-context fraction, not relevance
precision. All 768 reference graphs are incomplete, and historical graph/fresh
anchor/BM25 model-task results still tie at 24/25.
本次仅回算原始记录，未产生新的实验样本；将执行见证密度与真正任务相关性区分，
保留完整图为零及旧任务结果持平的限制。

Added source/evidence hash checks, explicit comparator and observation-unit checks,
negative tests for unsupported status promotion, and bilingual generated status
pages. The normal CLI validates this frozen study's record consistency;
`--require-mature` is expected to exit 2 because substantive evidence is missing.
It is not a universal or automatic scientific-maturity assessor.
新增检查不能作为新增研究贡献或独立评议；新的研究结论需要新的证据与人工核验。

Commands: `python scripts/check_research_claims.py`,
`python -m pytest -q tests/test_research_claims.py`, and the existing full
correctness/publication/build gates. Results are recorded after execution; no
new model or external-label experiment was conducted in this audit.

Local acceptance after integration: **1451 passed, 2 optional-tokenizer skips**;
Ruff, attribution and claim-record checks passed. The first suite invocation used
an environment without the editable package installed and stopped at import
collection; rerunning with this checkout's absolute `src` on `PYTHONPATH` passed.
`--require-mature` returned the expected status 2. Build and current remote CI
are separate gates; no prior CI result is treated as validating this change.
本地1451项通过、2项可选分词器跳过；首次调用因测试环境未加载本源码而收集失败，
明确指向当前源码后通过。成熟度拒绝码为预期的2，不能写成成熟研究验收通过。

## 2026-10-13–14: external issue-only pilot

- `aefdf06` froze39 metadata-selected tasks, six unused Python repositories,
  six methods and8000/16000/32000 UTF-8 budgets before prediction/label analysis.
  The selection is below the proposed60-task scale, explicitly a pilot.
- Synthetic independent reviews caught malformed-diff accounting, missing grids,
  silent source-manifest duplicates, and lost common anchors on unresolved graph
  owners. They were repaired before formal predictions. Darwin's unsupported
  address-space limit required a documented pre-prediction RSS-monitor amendment.
- `2451b574856048f3d9dded1fc1f55f209241cdc2` measured run
  `pilot-20261014T081813Z`:39 attempted,34 predicted,5 Python-byte-cap failures,
  32 line-scorable and7 no-target tasks. No task was replaced. Both planning gates
  failed. Source/patch accounting and all702 score cells were recomputed with
  separate local parsers; this is not external replication or human peer review.
- Protocol and reproducible commands: `docs/en/EXTERNAL_PILOT_PROTOCOL.md`;
  generated bilingual result tables: `EXTERNAL_PILOT_RESULTS.md` in `docs/en/zh`;
  original sealed records: `benchmarks/external_context/results/`.
- Verification commands: `PYTHONPATH=src python -m benchmarks.external_context.check`
  and `python -m benchmarks.external_context.report --check`; default tests include
  source-integrity, budget, scoring, monitor and result-tampering counterexamples.

2026-10-13–14实际记录：先冻结39任务pilot与预算，再修复独立合成反例并提交实测源码，
串行尝试全部任务、封存预测后评分。保留5失败和7无行目标；两推进门槛失败。
独立本地计算核对不等于外部同行验收。没有执行上游源码、模型或商业API。

## 2026-10-14: catalog-query mechanism and counterexamples

Starting from `ce6e36de7f6860296d66dadcb3105a8bbda9eb9a`, the process-local
research session gained exact positive/negative candidate tuples and namespace
existence observations. Source-read hashes remain mandatory; missing or unsupported
trace versions force rebuilding. Query-aware whole-catalog and complete root-membership
controls use the same summary cache and preserve every unknown/truncated state.
This is an engineering application of existing dependency tracking ideas.

The first implementation integration run exposed an undefined local mode variable;
it was fixed before natural graph or timing runs. The explicit affected-suite command
was `PYTHONPATH=src python -m pytest -q tests/test_module_catalog.py
tests/test_catalog_reuse_review.py tests/test_incremental_module_cache.py
tests/test_selective_reuse_oracles.py tests/test_selective_replay.py`.
Independent test authorship and a separate fresh resolver check are local regression
evidence, not human peer review. Natural-input preparation retains two failed sampling
rules, all catalog events and a subsequently missing fixed RQ anchor. The source
preflight is separate from candidate correctness and performance.

实际开发记录：从上述真实提交新增目录查询足迹和两种强对照；完整读取哈希、未知与
截断状态仍保留，证书缺失或版本不支持时重建。首次接入因局部变量漏定义失败，已在
自然实验前修复。独立编写反例与本地 fresh 对照属于回归证据，不是人工同行评审。
输入准备保留两次选样规则的否定结果、所有目录事件及后续缺失的固定 RQ 锚点。

## 2026-10-14: frozen catalog study execution

- `e0bc1188ac24a0696828ab6170a07f69c9eb71e9` implements the mechanism and441
  affected regressions. Pre-freeze runner review found eight integrity issues,
  including source-grid omission and missing child provenance; fixes preceded all
  natural resolver/timing observations. Those local review probes are not independent
  human replication.
- A full integration check initially returned6failed/2064passed/2optional skips
  because historical claims bound current evolving source to old measurements.
  Exact20-source files from `a0070ea71cea3c8944c004559602616114011b76` were archived
  without changing prior hashes or outcomes. The repaired ledger rejects relabelling
  new source as the old run; the final pre-freeze suite returned2093passed/2skipped.
- `affa59024f70cde86d2549b690204aa73ddccc7d` froze the four repositories, all
  fixed anchors and source pins, four methods,20%target and source-inclusive costs.
  The actual portable downloader reused107verified archives, with0new downloads.
  Production paths and root licenses were rechecked; analyzed code was never executed.
- `python -m benchmarks.catalog_reuse.legacy_oracle` compared107unique snapshots
  and2568graphs to the unmodified `ce6e36de` resolver:0mismatches. This prevents
  a shared catalog-refactoring bug from masquerading as replay equality.
- `python scripts/run_catalog_study.py` produced
  `catalog-20261014T121419Z-84b62e96` from the clean frozen source:1816retained
  canonical-equal steps and48fresh RSS subprocesses. Performance target0/4, failed;
  resource target passed. All95additional graph reuses, small timing differences,
  capture costs, frontiers and the missing RQ anchor remain in the records.
- `python -m benchmarks.catalog_reuse.report --check` verifies sealed raw files,
  complete grids, frozen-source digests and generated English/Chinese reports.
  Build, publication scan and remote CI are separate post-experiment gates.

真实记录：先修复实验完整性漏洞和历史源码错绑，再真实提交冻结协议，串行运行旧解析器
对照、自然回放和RSS。6项历史账本失败已记录并修复，不重跑/改写旧测量；当前全测试
2093通过、2可选跳过。新性能门槛0/4失败，资源门槛通过；保留全部原始与负面结果。
这些是有限工程研究证据，不等于成熟论文、Python语义证明或agent任务收益。

Post-run acceptance:79affected reporting/runner/ledger tests passed; Ruff, attribution,
frozen-artifact checks and both earlier research reports passed. Isolated sdist/wheel
builds succeeded, installed-wheel CLI and the synthetic real-core example ran. The
sdist retained exact bytes for20archived runtime files and52new raw result files.
Docker was unavailable and not run; no build artifact is presented as a GitHub Release.
Remote publication and CI must be read back after pushing this evidence commit.

实测后79项受影响验证通过；构建、安装wheel入口及72项归档/结果字节检查通过。
Docker未运行，构建文件不等于GitHub Release；远端状态仍须另行核验。


## 2026-10-14 — explicit global write reliability / 显式全局写入可靠性

Post hoc reconstruction of the published catalog study found a real Scrapy
binding counterexample in one getter anchor: an initial literal is mutable via
explicit `global` writes in other functions. This explains one affected anchor,
not the overall low closure coverage. The first 455 independently specified
interface regressions on source09d6476 retained 264 failures and191 passes;
20 possible-write fixtures and12 controls are not455 independent observations.
The corrected implementation passed all455, and an additional seven compiler
name-mangling checks were added after review. Class-private `global __x` writes
the compiler's `_Class__x` name. No general runtime/semantic guarantee follows.

复核旧catalog样本发现Scrapy一个getter锚点的真实反例：同文件函数可能通过
显式global改写初始字面量。不能据此解释整体低覆盖。旧版首轮455项接口回归
实际264失败、191通过；它们由20个潜在写入夹具及12个负控制派生，不是455个
独立观察。修复版455项通过；独立审查后补充7项编译器私有名称检查。不可达
写入仍保守拒绝，反射、外部副作用及运行时语义证明均不在本修复范围。


## 2026-10-14 — fixed execution panel and retained negatives / 固定执行面板与负面结果

Core repair99f09f4, archive binding3ae2744 and panel freeze713682b are real local
commits. A pre-measurement runner review added failed-row retention and true
source-node pairing. After baseline134758 had run, independent physical-line
review required a second amendmentd6231c5; that first baseline remains recorded.
Final paired runs134920/134921 preserve20 corrected possible bindings and12
controls, but zero new watched-binding gain across10 natural anchors. All closures
remain unknown. Existing Scrapy double-version diagnosis is separately recorded.

The portable upstream entry point ran nine fresh processes using unmodified
upstream assertions:43 fixed passed,15 parent passed/28 failed,23 Pyparsing
methods passed,200 binding-state events. This reproduces known development
preflights and does not measure candidate task benefit. Full integration first
returned4 failures/2567 passes/2 optional skips because importing the historical
baseline generated23-source-archive bytecode caches. Only the ten verified
new `.pyc` files were removed; source, ledger, assertions and raw results were
unchanged. With bytecode disabled, all44 affected archive checks passed.

真实阶段提交与首基线均保留。第二次修订发生在已观察基线之后，不能称盲测。
新自然面板无新增收益、所有闭包不完整；九进程真实上游重放保留28条父版本
失败。全量验收首轮归档目录因字节码缓存导致4项失败，未放宽归档检查或改
实验数字；仅删除本任务生成且已核对的10个pyc，44项相关检查随后通过。


The staged whitespace check flagged one trailing space in the exact Pygments
AUTHORS attribution. The original byte was retained; only that attribution file
is exempted by `.gitattributes`. The intended validation/docs stages became the
actual combined commitc611cd5 after the first check rejected that attribution
space. No separate test commit is claimed. Final portable-record checks add
explicitly post-execution helper/dependency fingerprints and preserve the initial
index; worker/runner/raw results remain unchanged.

暂存空白检查遇到Pygments原始AUTHORS文件的尾随空格，保留原字节并仅对该
归属文件设置例外。实际验证/文档变更合并在c611cd5，不虚构未发生的test提交。
重放索引补充指纹明确标为执行后审查，原索引及所有原始结果不改。


## 2026-10-15 — source-bound cycle outputs / 源码绑定的周期输出

A real AutoGPT source run reached the original assertion but then failed the
source-set guard: the summary caller indirectly writes cycle JSON/text outputs,
in addition to two simple logs. The incomplete run and its progress stream were
retained. Added a separate exact six-file, 1 MiB policy with the original
`OVERWRITE_DEBUG` directory option and three additional source proofs. New
owned-child and mutation checks passed; the complete known-task adapter suite
returned176 passed, zero failed/skipped. This is adapter validation, before
rerunning the corrected upstream condition, not a task or research result.

真实 AutoGPT 条件暴露了遗漏的间接周期日志路径；保留原不完整运行与逐阶段
记录。新增精确文件、总字节限制、源码证明及目录选项检查，176项适配器测试
通过。此记录不把适配器通过写成上游任务或研究效果，后续复测另存新条件。


## 2026-10-15 — portable exact source roles / 可移植精确源码角色

Added an independently callable, source-only preparer using fixed public CSV and
archive hashes. It never executes Docker/test-command fields or upstream code,
rejects archive escapes/links/duplicate identities and patch context/position
errors, and refuses outputs inside Git.35 owned checks passed. Recomputed all78
role indexes from39 verified archives and the original dataset, matching137283
files/2461434350 bytes; a real CLI materialization also passed. Initial local
validation used the data subdirectory instead of the archive cache root and
failed before source parsing; corrected cache location is recorded privately.
Old/new parser checks and outputs were retained. No second SUT replay is claimed.

新增源码重建入口和35项异常输入/角色分离检查，真实重算78角色均与先前实验
字节相同；修正了本地验证脚本首次缓存根目录定位错误。原失败及两轮核对均
保留。源码重建检查不当作任务效果、独立SUT复验或研究成熟证据。

## 2026-10-15 — source parser boundary review / 源码解析边界复核

Independent owned counterexamples exposed physical-line splitting, marker
identity, required-link and verify-then-reopen weaknesses. Parsing now uses
physical LF records, verifies both patch markers, rejects case-insensitive Git
metadata and required nonregular entries, and parses the same bounded CSV/tar
bytes whose SHA256 was checked. Malformed extra hunk headers are rejected by a
deliberately stricter input policy; this is not claimed as a Git compatibility
fix. The original failing probes and earlier reconstruction runs are retained
privately. The expanded source-preparation suite returned53 passed, zero failed
or skipped. A fourth source-only readback again matched all78 original role
indexes. No upstream tests were rerun by these parser checks.

独立构造的反例暴露了物理换行、补丁路径标记、必需链接与校验后重读问题。
修正后对同一份有界读取且已校验的字节进行解析；额外畸形hunk采用更严格的
输入策略，不宣称这是Git兼容性修复。保留原失败与各轮核对，53项测试通过，
第四轮78角色索引一致。这些检查不等同于上游测试重跑或独立实验复现。

## 2026-10-15 — public observation checks / 公开观测检查

Added a privacy-filtered observation checker and bounded gzip transport. A
separate review found that empty phase lists, moved condition membership,
fabricated latest states, qualified partial records and missing claim guards
could pass the first candidate. That unpublished candidate and its failures
remain private; the corrected checker rejects these cases. It also executes
only the exact SHA-verified author-written contract bytes and orders explicit
UTC freeze times by datetime value.25 owned tests passed. These are synthetic
bookkeeping controls, not upstream executions or scientific samples. Actual
observation bundles are reviewed and recorded separately before publication.

公开观测检查器修复了空阶段、错配任务、虚构最新状态、不完整记录误合格及
声明缺失等反例，保留未发布首版和失败。仅执行已校验的自主判据字节，按
UTC时间值排序；25项自编检查通过。自编计数不代表上游实测或独立研究样本，
真实观测包另行审核记录；传输检查也不认证私有原始执行。

## 2026-10-15 — complete known-task records / 完整已知任务记录

Executed unchanged dataset-derived upstream tests in both base+test-patch and
oracle-code-patch+test-patch roles for all39 original tasks. The final retained
snapshot has51 complete pair conditions, one closed partial attempt,36008 phase
reports and12006 selected-role node outcomes. Latest conditions qualify finite
labels for30 tasks; three have no observed calls and six remain unqualified
with calls. The87 F2P /5842 P2P original-label denominator is unchanged. Earlier
missing dependencies, native aborts, original skips, already-passing base tests,
gold failures and the AutoGPT incomplete condition are retained. Compatibility
changes create new conditions; this is not a historical official-container replay.

Reviewed an exact53-file gzip observation export (INDEX SHA256
`06020b127bb16d3b8c2b28438ea3b613d683d550d35b8a3401f36eae695ec45b`).
The public report checker recomputed the qualification arithmetic and generated
the English/Chinese39-row tables. A zero-P2P Counter omission initially broke a
candidate table generator; corrected zero handling and four counterexamples are
retained in tests. A local full-test invocation first omitted `PYTHONPATH=src`
and failed collection; corrected invocation returned2947 passed/two optional
tokenizer skips. No source assertion was changed to resolve that invocation.

39项原始任务均实际运行双角色测试，保留51完整条件、1闭合不完整条件、36008阶段
及12006角色节点结果。30项有限合格，3项无观测调用，6项调用后仍未合格；原始
87/5842标签分母不变。保留依赖失败、崩溃、跳过、基线已通过、gold失败和中止。
公开53文件观测包及双语表可核验；生成器曾遗漏零值Counter，修复并保留4反例。
全套本地测试首次因未设置PYTHONPATH而收集失败，修正调用后2947通过、2可选跳过，
没有改动断言以制造通过。

## 2026-10-15 — post-hoc sensitivity and read bounds / 事后敏感性与读取上限

After all52 started conditions closed, froze the final eligibility ledger and
scalar-analysis inputs before computing the30-task subset. The analysis program
SHA256 is `b660d3b4aa34d9cb30905d1458a05a195ca3503970c41a6db186f555d57f25e9`;
result SHA256 is `f9566e32e27decd3a0970a04ffe0fad04be7369e0b33cdf2e48468bf2eadbf3c`.
This is post-hoc known-data analysis, not pre-data preregistration. Independent
integer/Fraction recomputation agreed with all18 method/budget cells in all
three views and their signed effects. At16000bytes the qualified subset changes
graph-minus-declaration F1 to+0.045618pp; recall is still14.300790pp lower.
The original all39 result and failed planning gates are unchanged. The five
original prediction failures remain in the primary; the subset retains three,
of which two have line targets and one is undefined.

Full local tests after adding the scalar report returned2951 passed/two optional
skips. A separate publication review then found that stat-before-read and an
unbounded INDEX read did not enforce a hard allocation cap. Public readers now
read at most limit+1 once and hash/parse those same bytes. Three new controls
cover oversized INDEX/part and the actual bounded read. The prior source-swap
test initially hooked the superseded read API and failed; its hook now follows
the bounded read while retaining the same swap/verified-execution assertions.
All36 affected observation/report controls passed after that test adaptation.
No frozen analysis/contract/source or raw measurement was changed by these fixes.

全部启动条件闭合后冻结资格与输入，再计算30项子集；这不是数据观察前预注册。
独立整数/有理数核对全部18配置×3视图及差值一致。合格子集F1相对声明BM25转为
+0.045618百分点，召回仍低14.300790百分点；原主结果与失败门槛不变。原5项
预测失败在子集中保留3项，其中2项有行目标、1项未知。2951项本地测试通过、2项
可选跳过后，独立审查又发现读取上限缺口；修正为单次limit+1有界读取并新增3反例。
旧源码替换测试首次仍hook旧API而失败，迁移hook后保留原断言，36项受影响测试通过。
未改冻结分析、判据或原始测量。最终全套与构建验证另行记录。

The report reader initially imported the analysis before checking the source
fingerprint. Review narrowed this binding: it now compiles the exact bounded,
SHA-verified own source bytes. A source-swap counterexample verifies execution
of the retained bytes after the file changes.37 related controls passed, followed
by the final complete local suite:2955 passed, two optional tiktoken skips,
zero failures. Commands used `PYTHONPATH=src python -m pytest -q tests
benchmarks/graph/test_scope_audit.py benchmarks/revision_baselines/test_baselines.py`.
This test total validates this checkout, not2955 upstream tasks. Docker was
unavailable; no container build is claimed. Remote CI and package-build results
are checked separately from local tests.

报告入口最初先导入分析再核源码摘要；审查后改为编译同一份有界读取且SHA核验
的自主源码，新增读取后替换源文件反例。37项相关检查通过，随后完整本地套件
2955通过、2项可选tiktoken跳过、零失败；这不是2955项上游任务。Docker不可用，
不宣称容器构建通过；远端CI和包构建结果与本地测试分别记录。

## 2026-10-15 — research-status scope clarification / 研究状态范围澄清

A cross-document review found that the status page's future experiment wording
could be mistaken for an unrun issue-only pilot, although the39-task pilot and
its unchanged-test follow-up were already recorded. The generated English and
Chinese pages now distinguish the outstanding unseen semantic/necessary-context
validation from that completed known-task work, and link to both the execution
and subset reports. The ledger also binds0/768 explicitly to the2026-10-04 frozen
holdout instead of calling it a current total across later studies.

Existing claim-ledger tests returned25 passed. Ruff, publication and attribution
checks passed. Only status prose, its generator and this log changed; no source
measurement, task membership, pass criterion or negative outcome was replaced.
These checks are documentation consistency evidence, not a new experiment.

跨文档复核发现“下一实验尚未运行”容易被误读为39项issue-only pilot尚未执行。
双语生成页现明确区分未完成的未见任务语义/必要上下文验证与已完成的已知任务
测量，并连接执行核验和子集报告；0/768明确限定为2026-10-04固定留出实验。
现有声明账本25项测试、Ruff、公开内容及归属检查通过。仅修改状态文字、生成器
与本日志，不改原始测量、任务成员、通过判据和负面结果；不计为新实验。
