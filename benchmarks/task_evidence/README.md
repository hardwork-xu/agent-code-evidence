# Upstream-test execution witness audit / 上游测试执行证据审计

This study executes **nine original upstream assertion functions** from Packaging,
attrs and Pluggy against pinned old/new releases, then compares source contexts
with independently traced current-version execution. It measures **task-conditioned
physical-source execution coverage**, not sufficient context, issue resolution,
patch quality or model performance. No model/API, setup script or dependency
installation is used. This is a reviewed convenience sample from projects already
used during development, not a heldout or representative bug benchmark.

本实验直接执行三个上游项目的九个原始断言函数；独立标签来自 Python 运行轨迹，
不是静态解析器输出。指标是“这些测试实际执行到的源码行被证据覆盖多少”，不代表
上下文充分性、修复成功率或模型收益。三个项目已用于开发，不能包装成独立留出集。

## Frozen selection and execution / 固定选择与执行

The premeasurement [protocol](PROTOCOL.md) and [manifest](manifest.json) bind case
IDs, exact test-function ranges/hashes, repository/archive/source hashes, explicit
invocation parameters, localized entrypoint hints, graph bounds and lexical
baseline. The two premeasurement class-name corrections are retained in the
protocol. The later [execution-correctness amendment](EXECUTION_AMENDMENT.md)
records the invalid pilot and restores original compiler flags without changing
the frozen cases. No case was discarded after observing coverage.

| Project | Before → after | Original functions |
|---|---|---|
| Packaging | 23.2 → 24.2 | prereleases detection; iterable specifier construction; missing keywords metadata |
| attrs | 23.2.0 → 24.3.0 | make_class annotations; pre-init keyword-only default; init-subclass hook |
| Pluggy | 1.3.0 → 1.5.0 | block/unblock registration; registration name; extra hook call |

Two traced and two untraced fresh processes per case/version check that tracing
preserves per-invocation assertion outcomes, for 72 child executions. Repeat or
trace-control mismatches make the case ineligible; control runs supply no labels.

Each test body is extracted unchanged from the **after** archive using its exact
qualified name. Outer test decorators are removed; the harness supplies reviewed
imports, `self=None` for methods that do not use `self`, and explicit parameters.
The prerelease case includes all 14 upstream parameter pairs. The attrs cases
include both validation/slots fixture states. Metadata uses only the `keywords`
member of the upstream field parameterization. Pluggy's `pm` fixture is exactly
`PluginManager("example")`. These invocation adaptations are visible in the
manifest and worker. Full test modules, conftest and setup hooks are not executed;
these are isolated original assertion functions, not full upstream test suites.

导入和 fixture 初始化不计入轨迹。每个版本各用两个 traced 和两个 untraced 独立进程复核断言一致性；只记录测试调用阶段
本项目 `src/` 内的唯一物理源码行。attrs 动态生成方法另计，避免把它们伪装成
可直接定位的源码。版本间隔包含多个提交，失败到通过不是对单个补丁的因果归因。

## Measurements and controls / 指标与比较

For case `i`, witness recall is `|context_lines ∩ executed_lines_i| /
|executed_lines_i|`. Unique source lines are unioned across that case's original
parameter variants. Aggregate recall is a macro average over eligible cases,
with separate per-project results. After-version failures, empty traces and
nondeterministic repeats remain recorded and are explicitly excluded from the
eligible average. Stable old/new assertions remain included. Assertions passing
on the new snapshot establish that the recorded path belongs to a passing test;
they do not establish general program correctness.

- **Fresh full source:** all project Python source, an unbudgeted mechanical upper
  bound, not a practical retrieval competitor.
- **Fresh anchors:** independently extracted spans of the manually localized
  entrypoint hints. These hints are available to all applicable methods; this
  study does not evaluate issue localization.
- **Fresh graph:** bounded graph with depth 4 and 256 nodes; all source spans are
  unioned once, including unresolved closures. Frontier states remain visible.
- **Lexical matched lines:** BM25 (`k1=1.2`, `b=.75`) on disjoint 20-line windows;
  query is the original test plus the same path/symbol hints. It receives exactly
  the fresh graph's unique physical-line budget. Stable tie order and a clipped
  final window fill that budget. This is a disclosed fixed lexical baseline, not
  a claim that all lexical retrievers are inferior.
- **Stale graph, current-byte credit:** old graph source spans receive current
  witness credit only when the complete span occurs byte-for-byte exactly once
  in the same current file. Changed, missing or multiply occurring spans receive
  no credit. Actual old context size is counted separately from credited current
  lines. This conservative text-identity rule is not a semantic edit mapper.

`execution_density` is covered witness lines divided by supplied context lines;
it is **not gold-context precision** because unexecuted code can still be useful.
Line budgets do not equal token budgets, and no performance or token-cost claim
is made. Fixture setup, import-time work, native calls, unexecuted branches and
unmapped generated code are outside the physical-line denominator. A large class
span may trivially cover many executed methods; higher recall must be read with
its context size and unresolved status. Nine correlated cases from three projects
cannot establish population prevalence or statistically independent task gains.

图闭包未解析时仍可提供部分有用证据；覆盖率与“可以认证复用”是不同指标。
所有不确定状态、失败和旧版上下文计费均保留；不以动态执行覆盖冒充 gold context。

## Reproduction / 复现

Requires Python 3.11+ and macOS Seatbelt for execution. The exact primary Python
version is recorded in each run. Source checks/scoring/unit tests are portable;
execution fails closed on unsupported platforms. The sandbox preflight verifies
network, fork, outside reads in both the source parent and `/private/tmp`, inside
writes and outside writes are denied. Runtime read exceptions include the Python
installation, system runtime directories, root-directory data and ancestor metadata
for allowed paths; arbitrary outside file contents remain denied.

1. Download the six `archive_url` entries in `manifest.json` to a directory outside
   the repository, named `{project}-{before|after}.tar.gz`. Keep TLS verification
   enabled. The runner performs no network requests or installations.
2. Verify/extract the archives, then use a new output directory for every run:

```sh
python scripts/run_task_evidence.py --sources /path/to/task-inputs --extract
python scripts/run_task_evidence.py --sources /path/to/task-inputs \
  --output /path/to/new-task-results
python -m pytest -q tests/test_task_evidence.py
```

The runner verifies every source Python file and exact test-file hash before
execution, checks the original archive hash, captures twice-repeated raw traces,
and records implementation hashes plus Git HEAD and dirty-state flags. Existing run directories
are never overwritten. Each child completion atomically updates `progress.json`;
`status.json` records execution/evaluation failure stages with sanitized errors.
A summary is written only after complete validated evaluation. Source snapshots and test bodies are fetched as data;
only the nine reviewed functions and their imported library code are executed.
`results/initial` is an invalid pre-commit pilot: its forced postponed annotations
changed upstream execution semantics. Do not use its metrics for research claims.
Its `STATUS.md` also preserves a separate stale-context accounting erratum.

## Prior work and licenses / 先例与许可

[ContextBench §2.3–2.5 and Appendix D](https://arxiv.org/html/2602.05892v3)
uses expert-annotated gold context. Our automatically traced execution witness
is a narrower signal and does not reproduce its gold-context evaluation.
[SWE-bench's official overview](https://www.swebench.com/SWE-bench/) describes
repository issue tasks evaluated through submitted patches and tests. We submit
no patches and report no SWE-bench score. These sources motivated the boundary;
the actual measurement inputs are the original upstream tests linked in the
manifest. Accessed 2026-10-04.

Packaging is Apache-2.0 OR BSD-2-Clause; attrs and Pluggy are MIT. Exact license
bytes for both pinned versions are retained under `licenses/`, with upstream
license hashes in the manifest. Original assertions and source are not relicensed
by this harness. All upstream source archives remain external inputs.
