# Source-read certificates for evolving code evidence: an experimental report

**Status: research draft, not submission-ready or peer reviewed.** This report
separates a resolver correction, a reproducible incremental-computation
experiment, and the evidence still missing for a mature research claim.

## Abstract

We investigate selective reuse of bounded Python source-evidence graphs. The
artifact corrects a class-global rebinding failure and records negative lookup
inputs that are absent from visible graph nodes. A fixed developmental corpus
contains 72 authored instances across 24 templates; 63 are inside the declared
static contract. Twelve previous false-fresh decisions, representing four
templates, become explicit unknowns. Nine runtime-effect cases remain outside
the contract. A paired replay covers four new repositories, six revisions each,
96 unique function identities, and three synthetic corpus sizes. Across
9720 emitted graphs, matched methods produce zero graph-byte
mismatches. The predeclared utility target is **not met**.
These observations establish neither general Python semantic soundness nor
better coding-agent task performance.

## 1. Question and scope

Can complete static evidence be reused across revisions at lower total measured
cost while exactly preserving a full rebuild's bounded output? Source identity,
context relevance, semantic behavior and task success are distinct outcomes.
This is an engineering adaptation of established dependency traces, not a new
general incremental algorithm. Prior model runs found graph, fresh-source and
BM25 conditions tied at 24/25 tasks; those historical results are not rerun or
combined with the new timing table.

## 2. Mechanism and independent checks

A `GraphSession` retains anchors, policy, parsed source and read dependencies.
Only complete graphs qualify for selective reuse. All source paths and all
consulted file bytes must agree; otherwise the full resolver runs. Candidate
package files inspected before submodule fallback are tracked even when absent
from the resulting graph. [Design and correctness argument](SELECTIVE_REUSE.md).

The independent oracle labels were authored separately from the resolver and
checked by executing only the synthetic fixture programs. This is model-assisted
development validation, not independent human annotation or a holdout. There
are 21 scoped templates and three out-of-scope runtime-effect templates. Numeric
variants must not be interpreted as independent samples or a natural error rate.
[Version-2/version-3 matrix](../../benchmarks/selective_reuse/results/v2-v3-matrix.json).

## 3. Method

The protocol, methods and success threshold were fixed locally before primary
measurement; this was **not public preregistration**. Four convenience-sampled
Python projects absent from the previous natural corpus were pinned by latest
release (Pyflakes used the recorded tag fallback). Six first-parent commits per
project yielded 20 distinct filtered source snapshots. SHA-ranked
sampling selected at most 24 top-level function identities from each oldest
version, without selecting on graph completeness. Overloads are deduplicated
as anchor identities but remain in source to preserve ambiguity.

The initial invocation was rejected before timing because overload identities
were duplicated; the original manifest, failure record and explicit protocol
amendment remain. No source commits were replaced and no performance target was
changed. [Preflight record](../../benchmarks/selective_reuse/results/preflight-20261004.json).

Each method shares an indexed corpus per revision and a warm AST cache across
revisions. We rotate whole method trajectories, perform one warmup and five
recorded repetitions, and run benchmarks sequentially. Total times include local
archive reads, UTF-8 decoding, checksum validation, hashing, checking, graph
copying/sealing and fallback. Downloads, correctness comparison and output JSON
serialization are separate. Initial capture is shown separately; it excludes
process startup and session construction. Background OS activity is uncontrolled.

There are 20 natural transitions: 16 change filtered source and
4 retain identical source. They are all retained. Graphs, transitions
and repeated trials are dependent; four repositories do not support broad
population or significance claims. Min/max and individual observations are in
raw data. Metadata, complete pairing, interruption and non-overwrite checks
reject incomplete or inconsistent artifacts before summarization.

## 4. Results

Values are medians of the sum of five transitions in each repetition, in ms.
Positive reduction means faster; negative means slower. The utility target was
at least 20% lower time than the shared-index rebuild on at least three of four
repositories, with no graph mismatch. **0/4 meet that threshold.**

| Repository | Rebuild ms | Whole-corpus ms | Read-set ms | Read-set reduction vs rebuild | vs whole corpus |
|---|---:|---:|---:|---:|---:|
| PyCQA/pyflakes | 5578.47 | 5585.15 | 5584.74 | -0.1% | +0.0% |
| Textualize/rich | 10573.07 | 6811.07 | 10625.50 | -0.5% | -56.0% |
| more-itertools/more-itertools | 651.05 | 649.94 | 647.50 | +0.5% | +0.4% |
| python-humanize/humanize | 402.17 | 275.86 | 399.29 | +0.7% | -44.7% |

Source-changing transitions only (same frozen inputs; no resampling):

| Repository | Rebuild ms | Whole-corpus ms | Read-set ms | Read-set reduction vs rebuild | vs whole corpus |
|---|---:|---:|---:|---:|---:|
| PyCQA/pyflakes | 5578.47 | 5585.15 | 5584.74 | -0.1% | +0.0% |
| Textualize/rich | 6359.48 | 6330.71 | 6329.43 | +0.5% | +0.0% |
| more-itertools/more-itertools | 651.05 | 649.94 | 647.50 | +0.5% | +0.4% |
| python-humanize/humanize | 242.91 | 242.38 | 242.31 | +0.2% | +0.0% |

All 24 natural snapshots had zero complete sampled graphs. That is a coverage
limitation of this resolver and this sampling frame, not evidence that natural
programs are unsafe. Selective reuse retained 0/480 natural anchor-transition graphs
per repetition. This is a replay count, not evidence of semantic safety. A
whole-corpus equality guard can retain incomplete graphs without changing their
unknown status; the selective policy deliberately rebuilds them. Therefore a
comparison only against full rebuild would conceal a strong simple alternative.

| Repository | Initial capture median ms |
|---|---:|
| PyCQA/pyflakes | 1110.46 |
| Textualize/rich | 2252.25 |
| more-itertools/more-itertools | 139.13 |
| python-humanize/humanize | 81.66 |

All three synthetic sizes (10, 100, 1000 modules) include unrelated file edits,
referenced file edits and catalog additions. Raw data retain adverse fallback
cases, initialization and all five repetitions; synthetic timing is not a
natural-workload frequency estimate.

## 5. Provenance correction

Exact third-party license texts are retained and checked offline. Independent
inspection of 71 original source files verified 1309 distributed excerpts:
748 byte matches, 544 matches after presentation whitespace, and 17 historical
noncontiguous excerpts whose declared contiguous line spans were inaccurate.
The 17 cases are explicitly indexed; historical raw outputs are unchanged.
This is a remaining historical citation limitation, not a source-span success.
[Verification](../../third_party/source-verification.json) ·
[17 corrections](../../third_party/noncontiguous-excerpts.json).

## 6. Interpretation and maturity gates

The primary timing hypothesis fails its predeclared target. The artifact remains useful for falsifying an optimization claim, but the results do not justify a general selective-reuse speedup claim.
A mature paper still needs a defensible contribution beyond the established
incremental-computation mechanism, task-conditioned context labels independent
of this resolver, repository/time-disjoint natural validation, and end-to-end
coding-task evidence with fresh retrieval and simple invalidation baselines.
Independent human review and external replication have not occurred here.
An incremental per-module binding-summary baseline and retained-memory/RSS
measurements are also absent; comparisons are limited to the three tested methods.
No acceptance, publication, SOTA, production deployment or model-quality gain
is claimed. This draft is a technical research record, not a completed paper.

## 7. Related work and reproduction

Dependency-hash traces are established in Mokhov, Mitchell and Peyton Jones,
[Build Systems à la Carte (2018)](https://www.microsoft.com/en-us/research/wp-content/uploads/2018/03/build-systems.pdf).
[Tup ghost nodes](https://gittup.org/tup/manual.html) and
[Bazel Skyframe](https://bazel.build/reference/skyframe) establish the importance
of negative and complete dependencies. [ContextBench v3](https://arxiv.org/abs/2602.05892v3)
concerns task-relevant contexts; [When Retrieval Hurts v1](https://arxiv.org/abs/2605.14478v1)
studies stale-context harm. Our adaptation does not establish novelty over these
principles or reproduce their model experiments. [Detailed positioning](RELATED_WORK.md).

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python scripts/check_attribution.py
python scripts/run_selective_reuse.py prepare
python scripts/run_selective_reuse.py run --suite all
python scripts/run_selective_reuse.py analyze --output PATH_TO_NEW_RUN_JSON
python scripts/render_selective_report.py benchmarks/selective_reuse/results/primary-20261004.json
```

The archived command is a portable reproduction command; local cache placement
is intentionally excluded. Runtime code and runner hashes are recorded. The
measured tree included uncommitted documentation/attribution work, while the
listed implementation files and runner were committed and content-hashed.

- run_id: `selective-20261004T195433Z`
- source commit: `b25b3d4ed20eb36f1e432dbd5d8ce4db9ad8bca8`
- protocol SHA256: `ca129aed54bda5e94eadd26929736ed906b2b74e87ca0469b43db7367f2a1e0e`
- manifest SHA256: `c9034cc9fae4e44ae395c9b0a3ad280ae2da17050ff88de4408b5d687d4a5ef0`
- Python 3.12.2, Apple M1 Pro, arm64, RAM 16 GiB; one benchmark thread.
- [Raw data / 原始数据](../../benchmarks/selective_reuse/results/primary-20261004.json); [protocol / 协议](../../benchmarks/selective_reuse/protocol.json); [pins / 版本](../../benchmarks/selective_reuse/natural-manifest.json).

