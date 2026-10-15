# Agent Code Evidence · 智能体代码证据校验

Previously `contextproof`. Package and command names remain unchanged (`contextproof`). 仓库原名 `contextproof`，包名及现有命令保持不变。

[![CI](https://github.com/hardwork-xu/agent-code-evidence/actions/workflows/ci.yml/badge.svg)](https://github.com/hardwork-xu/agent-code-evidence/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Versioned source evidence for coding agents.**

When a repository changes, a saved caller can still look identical while its
dependencies have changed. ContextProof records the source and supported Python
references behind that caller, explains which recorded dependency changed, and
delivers current source within a measured context allowance.

The graph workflow adds immutable Git snapshots, bounded transitive dependency
evidence, verified graph deltas and MCP handles. Full evidence stays in the local
store; the model receives a separately budgeted source payload. Dynamic dispatch,
ambiguous symbols, unsupported references and missing source remain explicit.

Python 3.11+, macOS/Linux. The core has no third-party runtime dependencies and
requires no model, GPU or API key. Hosted-model experiments are separate.

[简体中文](docs/README.zh-CN.md) · [Graph API and contracts](docs/GRAPH.md) ·
[Measured report](docs/GRAPH_REPORT.md) · [Model protocol](docs/REVISION_STUDY_PROTOCOL.md)

## External real-task pilot (2026-10-14)

The [frozen issue-only study](docs/en/EXTERNAL_PILOT_RESULTS.md) attempted **39 real
tasks across six unused repositories**:34 generated predictions and five hit the
32 MiB Python-source cap. All tasks and failures are retained. Seven tasks have
no removed-line target, so their line metrics remain undefined.

Both predeclared planning gates failed. At16000 UTF-8 bytes, graph expansion
achieved0.881158% repository-macro removed-line F1 and8.898059% recall;
declaration BM25 achieved1.140966% F1 and18.620775% recall. These are reference-edit
proxy labels, not necessary context or agent repair success. The [raw results,
source checks and limits](docs/en/EXTERNAL_PILOT_RESULTS.md) support a reproducible
negative/mixed pilot, with no maturity or external-tool superiority claim.

[Protocol and commands](docs/en/EXTERNAL_PILOT_PROTOCOL.md) ·
[Prior-work boundary](docs/en/EXTERNAL_RELATED_WORK.md)

The [unchanged-upstream test follow-up](docs/en/KNOWN_TASK_EXECUTION.md) retains
the same39 observed tasks and every earlier failed condition. Its
[generated status table](docs/en/KNOWN_TASK_EXECUTION_RESULTS.md) separates actual
finite-label qualification from crashes, skips and missing calls.
The final snapshot retains51 complete pair conditions and one closed partial
attempt: **30/39 qualify finite labels; nine remain unqualified**. Source-role
preparation and the public observation checker are independently runnable;
checking exported records does not rerun upstream tests. Gold patches are
existing evaluation oracles, not generated repairs. This stage does not change
the pilot's failed gates or establish research maturity.

The [post-hoc sensitivity analysis](docs/en/KNOWN_TASK_SENSITIVITY.md) reports the
execution-qualified subset separately. At16000 bytes, its F1 ordering against
declaration BM25 flips, while recall remains lower than both BM25 baselines.
The all39 primary population and every negative result remain unchanged.

## Explicit-global binding reliability (2026-10-14)

[Resolver 4](docs/en/FUNCTION_GLOBAL_BINDINGS.md) retains possible deferred
function-global writes as unknown instead of selecting an initial module literal.
In 32 controlled fixtures, 20 possible-write bindings changed from resolved to
unresolved and 12 non-writing controls remained supported; one unreachable write
shows the conservatism cost. **No new watched-binding gain appeared in the natural
panel**: all ten anchor closures remain unknown, and three Pyparsing keys were
already unresolved. Four upstream fixes supplied 43 assertions, not 43 repair
tasks; their execution preflights do not measure candidate benefit.

[Design, commands and limitations](docs/en/FUNCTION_GLOBAL_BINDINGS.md) ·
[Paired development results](benchmarks/global_bindings/results/development-20261014/REPORT_en.md)
Two protocol amendments and the first baseline remain recorded; the last amendment
followed an observed baseline. This is development evidence, not blind evaluation,
performance improvement or mature research.

## Catalog-dependency study (2026-10-14)

The [new typed catalog guards](docs/en/CATALOG_RESULTS.md) retain positive and negative
module queries while preserving source hashes and all unknown frontiers. Four
natural repositories supplied 64 updates, each combining eight commits, and all 23
catalog event pairs. The primary 20% replay cost target against a complete module-root
guard was met in **0/4** repositories, so the overall gate failed. Observed median
reductions were 0.46%–5.10%; these small differences on one host do not establish a
robust speedup. The mechanism reused 95 more of 1536 anchor updates than the root guard;
this means fewer unnecessary rebuilds, without establishing
semantic freshness or coding-task improvement.

Only 15/1536 replay outputs in the first measured trajectories had no frontier; unknowns remain.
All 1816 retained steps matched fresh canonical graphs; the unmodified baseline also
matched 107 unique snapshots/2568 graphs. All 48 fresh RSS workers completed and the memory gate passed.
[Complete costs, negatives and limits](docs/en/CATALOG_RESULTS.md) include capture,
replay, total cost and the missing RQ anchor. No maturity claim or new Release.

The first three catalog reproduction commands below use a separate checkout at measured
commit `affa59024f70cde86d2549b690204aa73ddccc7d`. The current resolver deliberately
rejects that old measurement fingerprint. Run the last command in the current
research checkout to validate retained records against its read-only source archive.

```sh
PYTHONPATH=src python examples/catalog_reuse.py
python scripts/prepare_catalog_sources.py --output /tmp/catalog-study-inputs
PYTHONPATH=src python scripts/run_catalog_study.py --inputs /tmp/catalog-study-inputs/ready-manifest.json --protocol benchmarks/catalog_reuse/protocol.json --output /tmp/catalog-study-results
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m benchmarks.catalog_reuse.report --check
```

## Research branch (1.2.0a1)

Resolver 4 includes deferred function-global guards; resolver 3 introduced the
class-body global repair. Older graphs must be recaptured. Historical measurements
below retain their recorded resolver versions.
The new [source-read replay study](docs/en/RESEARCH_REPORT.md) preserves a negative
result: complete-only certificates reused **0/480** natural anchor transitions,
and no repository met the predeclared speed target. All sampled natural graphs
had unresolved frontiers. This is not a mature-paper or general acceleration claim.

The follow-up [research manuscript and complete results](docs/en/MATURATION_REPORT.md)
compare persistent module summaries and selective graph reuse across six methods
on four separately held-out repositories, with isolated RSS and Python-memory
measurements. A separate nine-case, 72-process study measures upstream-test
execution-witness coverage, including cases where BM25 covers more than the graph.
[Design and conditional guarantees](docs/en/INCREMENTAL_DESIGN.md) explain the
cache and invalidation mechanisms. These studies do not establish model-task
improvement or peer-reviewed research maturity.
The [claim-by-claim research status](docs/en/RESEARCH_STATUS.md) links supported
results to frozen records and lists missing semantic, task-benefit and external
validation evidence. Its automated check verifies consistency, not scientific merit.

To reproduce this experimental branch, clone with
`git clone --branch research/evidence-risk-20261004 https://github.com/hardwork-xu/agent-code-evidence.git`.
The manuscript records the exact measured commits, source pins and raw runs;
normal installation and the stable graph example below remain available on main.

The [research API and example](docs/en/SELECTIVE_REUSE.md) are offline and require
no model key. An explicitly exploratory `read_set_any_status` mode tests caching
unknown outputs while retaining their unknown status. It is not a freshness
certificate. [Source attribution](third_party/README.md) now includes exact
licenses and 17 disclosed historical excerpt-location limitations.

## Run the three-hop example

```sh
git clone https://github.com/hardwork-xu/agent-code-evidence.git
cd agent-code-evidence
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python scripts/demo_graph.py
```

Open `docs/assets/graph-demo.html` locally. This clearly labeled synthetic
demonstration creates real Git commits, changes a third-hop dependency from
`0.05` to `0.20`, and runs the actual implementation. It checks that the changed
source reaches the model payload, the delta exactly reconstructs the current
graph, unrelated changes can retain evidence, and insufficient budgets or unknown
references remain incomplete. Fixture code is inspected, never executed.

## Use it with a repository

Replace `REPOSITORY`, `BEFORE_COMMIT` and `AFTER_COMMIT` with real values:

```sh
contextproof graph-capture REPOSITORY "invoice_total" \
  --ref BEFORE_COMMIT --budget 16000 \
  --output work/before.json --payload work/before-context.json

contextproof graph-refresh REPOSITORY work/before.json \
  --ref AFTER_COMMIT --view full --budget 16000 \
  --output work/after.json --payload work/current-context.json \
  --delta work/change.json

contextproof graph-apply work/before.json work/change.json \
  --output work/reconstructed.json
```

Use `--view update` when retaining the identified base context. An update is not
standalone full context. Commands save full artifacts separately; **only the
payload file is the bounded model message**. Exit `1` means incomplete delivery,
which can still contain useful source; exit `2` is an input or operation error.
Omitting `--ref` scans and hashes the working tree without promising an atomic
filesystem snapshot. Immutable Git reads never fetch missing objects or execute
repository code.

## What is checked

| Contract | Evidence | Limit |
|---|---|---|
| Source identity | Exact text, path, declaration and recorded fingerprint | No semantic-equivalence or authorship proof |
| Static dependency evidence | Supported definitions, import bindings, cycles and bounded transitive paths | Unresolved or truncated frontiers prevent freshness |
| Model delivery | All UTF-8 bytes of source, citations, metadata and summarized diagnostics | Whole declarations may not fit; complete delivery is not task sufficiency |
| Graph delta | Named base, field edits, target seal and exact reconstruction | Storage/transport savings do not imply fewer model tokens |

Nodes have stable path/symbol/kind identities and separate source fingerprints.
Line movement can change citations without retransmitting unchanged source text.
ASTs are reused in memory across MCP requests; source hashes and resolution
catalogs are checked again. Optional disk AST persistence remains available for
measurement, but is not the default after a fair timing comparison found overhead.

The existing exact-span `bundle/verify/repair` workflow and v1 direct-witness
`capture/check/refresh` APIs remain available. The latter's source-only rendering
does not guarantee delivery of a changed dependency; use the graph workflow when
the model needs that dependency's code. Historical evaluations remain unchanged.

## MCP

Use [examples/mcp.json](examples/mcp.json) with a fixed absolute repository root.
`contextproof serve ROOT` exposes ten tools. The graph pair is:

- `contextproof_graph_capture`: choose anchors, save the full graph locally and return bounded source plus its handle.
- `contextproof_graph_refresh`: read that handle and return current full/update source with explicit coverage.

Their complete returned text is charged to `budget` in UTF-8 bytes. Tool schemas
and outer conversation framing are not part of that string; actual experiment
token usage is recorded separately. Legacy tool sidecars have a different budget
contract, documented in the [v1 report](docs/TECHNICAL_REPORT.md).

## Evidence, including negative results

The [graph replay](benchmarks/graph/README.md) measures exact reconstruction,
additional transitive observations, delivery failures and fair cache baselines.
It preserves the initial renderer's metadata-overflow failures and the slower
persistent-cache design. A lexical-scope correctness review also triggered a
versioned resolver correction; original artifacts are retained.

The [real revision study](docs/REVISION_STUDY_PROTOCOL.md) freezes 30 upstream-derived
API probes from four libraries, with 5 development and 25 held-out tasks. It
compares six source conditions under a 16,000-byte cap, including a same-anchor
source baseline and actual Archex 0.31.2. A capable-model gate passed 5/5 before
held-out inference. The public protocol and inputs precede those completions.
This is source-conditioned output prediction with supplied localization hints.

The frozen 150-completion comparison scores **8/25 with stale source and 24/25
with graph context, fresh supplied declarations or BM25**; Archex scores 21/25.
The graph ties the simpler same-anchor baseline and uses more input tokens.
These results motivate version tracking and auditable refresh. A separate
25-completion resolver-v2 sensitivity produces the same 24/25 answers; the original
150 records remain available. [Full paired results and correction history](docs/GRAPH_REPORT.md).

![Original comparison and corrected graph sensitivity](docs/assets/revision-results.svg)

Earlier results remain public: [300 exact-text drift cases](docs/DRIFT_STUDY.md),
[34 direct-dependency controls](docs/DEPENDENCIES.md), and a
[60-generation Qwen study with 0/20 in every condition](docs/DOWNSTREAM.md).
Neither contract agreement nor a smaller artifact establishes model effectiveness.

## Reproduce and contribute

```sh
python -m pip install -e '.[dev]'
ruff check .
pytest -q tests benchmarks/graph/test_scope_audit.py benchmarks/revision_baselines/test_baselines.py
python scripts/check_publication.py
python -m build
```

For official MCP SDK interoperability, install `.[integration]` and run
`python scripts/check_mcp_sdk.py`. Benchmark commands and frozen inputs are linked
from their reports; CI does not invoke hosted models.

[Related work](docs/RESEARCH.md) · [Security](SECURITY.md) ·
[Publication/privacy policy](docs/PUBLISHING.md) · [Development log](docs/DEVELOPMENT_LOG.md)

Maintained by **hardwork-xu**, with AI assistance for design, implementation,
experiments and writing. The project claims no new retrieval algorithm or
published research result. Source and evaluation records are public; personal
plans, account data and raw local diagnostics are kept outside Git.

The [post-result ablation](docs/en/ABLATION_REPORT.md) preserves unknown states and reuses 364/480 natural graph transitions. Relative to the contemporaneous whole-corpus guard, replay time decreases by 83.0% (Rich), 29.3% (Humanize), 18.8% (More Itertools), and 6.2% (Pyflakes). These are same-data exploratory CPU results, not task-quality gains.
