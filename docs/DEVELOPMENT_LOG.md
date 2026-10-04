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
