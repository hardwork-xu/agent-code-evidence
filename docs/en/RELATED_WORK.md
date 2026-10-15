# Related work and contribution boundaries

Sources checked on 2026-10-04. This note retains five closely related sources,
using author, official-project or original arXiv pages. It is not a systematic
literature review and does not establish a priority claim.

## 1. Build Systems à la Carte

**Authors and version:** Andrey Mokhov, Neil Mitchell and Simon Peyton Jones;
2018, PACMPL 2 (ICFP), Article 79, DOI `10.1145/3236774`. The authors' institution
provides the [publication record](https://www.microsoft.com/en-us/research/publication/build-systems-la-carte/)
and [paper PDF](https://www.microsoft.com/en-us/research/wp-content/uploads/2018/03/build-systems.pdf).
This is the 2018 paper, not its 2020 extended journal version.

**Relevant sections:** §4.2.2 (PDF pages 14–15) and §5.3 (pages 20–21). Verifying
traces already retain prior dependencies and their hashes to decide whether to
rebuild; scheduling and rebuilding are separate concerns.

**Boundary:** Dependency-hash traces and reuse decisions are established. Our
read-set guard adapts these ideas to bounded source-evidence graphs; naming the
stored read set a certificate does not establish a new general incremental
algorithm. The defensible scope is an inspectable source-evidence contract,
conservative invalidation, explicit uncertainty, independent counterexamples and
measured workload limits. Replay equality and semantic validity remain separate.

## 2. Tup manual: observed reads and ghost nodes

**Attribution and date:** The Tup project's [official manual](https://gittup.org/tup/manual.html)
has no named individual author or publication date: **n.d., accessed 2026-10-04**.
Do not assign the related 2009 paper's date to this manual.

**Relevant sections:** `graph --ghosts`, `graph.ghosts` and the Tupfile `command`
description. The manual retains nodes for attempted reads of nonexistent files
and tracks inputs actually read by commands, providing a direct precedent for
negative dependencies.

**Boundary:** A failed lookup becoming invalid after a later file or binding
change is not a new observation. Our scheme records static name-resolution
consultations and checks candidate-file reads plus the complete catalog; Tup
observes file accesses by build commands. These are different objects. We have
not run or benchmarked Tup. Our coarse catalog guard establishes neither minimal
invalidation nor a new negative-dependency algorithm.

## 3. Bazel Skyframe documentation

**Attribution and date:** The Bazel project's [official documentation](https://bazel.build/reference/skyframe)
provides no individual author or publication/update date: **n.d., accessed
2026-10-04**.

**Relevant sections:** “Evaluation,” “Incrementality” and “Mapping to Bazel
concepts.” Unregistered input reads can undermine incremental correctness. File
contents, file state and directory listings are distinct dependencies. The
account also distinguishes rebuilding from incrementally modifying prior results.

**Boundary:** Complete dependency registration and clean-rebuild equivalence are
established engineering principles. Tracking only files represented by resolved
graph nodes is insufficient: an attribute added to `package/__init__.py` can
shadow a submodule, and a new catalog entry can make a module ambiguous. Every
consultation that affects this resolver must be registered. Byte-equivalent fresh
reconstruction checks this resolver's output, not program semantics. Successful
fixtures alone prove neither complete tracking, hermeticity nor optimal invalidation.

## 4. ContextBench: A Benchmark for Context Retrieval in Coding Agents

**Authors and version:** Han Li, Letian Zhu, Bohan Zhang, Rili Feng, Jiaming Wang,
Yue Pan, Earl T. Barr, Federica Sarro, Zhaoyang Chu and He Ye; 2026.
[arXiv v3](https://arxiv.org/abs/2602.05892v3), dated 2026-02-11; v1 is dated
2026-02-05. The [full text](https://arxiv.org/html/2602.05892v3) is available.

**Relevant sections:** §2.3–2.5 and Appendices D/H. The benchmark provides
human-annotated task context and process-level retrieval evaluation at multiple
granularities, extending evaluation beyond final task success.

**Boundary:** Context relevance and temporal source validity are distinct.
ContextBench evaluates retrieval and use of task context; this package studies
whether source evidence can be reused across revisions. Our synthetic oracles
supply no gold task context. The separate [upstream-test witness audit](../../benchmarks/task_evidence/README.md)
measures coverage of physical source lines executed by selected original tests.
Those traces are neither minimal nor sufficient context, and are not expert gold
annotations. They do not reproduce ContextBench, establish general retrieval
quality or demonstrate a model-task benefit.

## 5. When Retrieval Hurts Code Completion: A Diagnostic Study of Stale Repository Context

**Authors and version:** Haojun Weng, Qianqian Yang, Hao Fu, Haobin Pan and Xinwei
Lv; 2026. [arXiv v1](https://arxiv.org/abs/2605.14478v1), dated 2026-05-14;
[full text](https://arxiv.org/html/2605.14478v1). The page says “Submitted to
Information and Software Technology”; this must not be reported as journal acceptance.

**Relevant sections:** Abstract, experimental design and validity discussion.
The authors compare current, stale, no-retrieval and mixed contexts on 17 helper
signature changes from five Python repositories. This diagnostic study shows
that stale context can mislead, beyond merely lacking context; it does not estimate
an overall natural failure rate.

**Boundary:** Evidence that stale context can harm completion already exists.
The defensible question is when reuse can be conditionally certified, when to
abstain or refresh, and what risk/coverage/cost tradeoffs follow. Resolver regression
results and replay equality do not establish better generated code or task
success. Such a claim requires model-task experiments. This work did not rerun
that paper's experiments.

## Defensible present claim

This package implements and evaluates conservative reuse for bounded Python
source-evidence graphs. It records consulted sources, invalidates on catalog or
read-set changes, retains incomplete frontiers and separates replay equality,
limited static contracts, out-of-scope runtime stress and task execution witnesses.
Persistent source-local summaries are described in the
[incremental design](INCREMENTAL_DESIGN.md). This remains a scoped adaptation of
established incremental techniques and a reproducible research artifact. It has
not established a new general algorithm, population-level risk reduction or
improved model-task performance.

The companion [maturation report](MATURATION_REPORT.md) records the current
experimental status and evidence boundaries. Results for a heldout performance
study must come from its completed, validated records; this literature note
asserts no pending speed or memory result.

## Comparisons and gaps that must remain visible

- Compare methods that share a snapshot corpus and parsing/indexing work. The
  current design includes persistent-summary reconstruction and a combined
  whole-corpus guard; selective reuse must be compared with these practical
  alternatives. Count source verification, hashing, catalog checks, copying,
  rendering and memory rather than isolating only avoided graph work.
- Every update still hashes all supplied source bytes and checks the full path
  set. Source-local summary reuse does not imply sublinear ingestion. File-level
  read sets and catalog invalidation remain coarse; no minimal-invalidation or
  repository-size-independent total-cost claim follows.
- Report replay equality, in-contract false-fresh/unknown/coverage and runtime
  stress separately. Fresh output from the same resolver cannot replace independent
  semantic expectations. Reusing an unresolved result preserves uncertainty rather
  than certifying freshness.
- The historical 72-case corpus comes from 24 authored synthetic templates and
  includes known development regressions. Natural-source replay is not natural
  semantic labeling. The new upstream assertion audit is a convenience sample
  from development repositories, with independent execution labels but no gold
  sufficient context. It is distinct from the repository-heldout performance
  study. Task sufficiency and end-to-end model benefits remain unestablished.

These comparisons are our interpretation of the sources and implementation, not
an assessment of this project by the cited authors.

[简体中文](../zh/RELATED_WORK.md)
