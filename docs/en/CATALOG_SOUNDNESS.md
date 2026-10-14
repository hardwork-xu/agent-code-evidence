# Conditional correctness of catalog-query graph replay

This note reviews the experimental catalog modes in
[`contextproof.reuse.GraphSession`](../../src/contextproof/reuse.py), with
`CATALOG_TRACE_VERSION = 1`. It concerns equality with this bounded resolver's
fresh reconstruction. It does not prove Python runtime semantics, useful agent
context, a new incremental-computation principle, or a performance improvement.
The base checkout is `ce6e36de7f6860296d66dadcb3105a8bbda9eb9a`; the catalog
implementation is a subsequent development change, not code present at that pin.
Source and primary-reference review date: 2026-10-14.

## Assumptions and claim

Let `Build(S, id, A, P)` denote a freshly constructed graph from source mapping
`S`, provider snapshot identity `id`, fixed anchor `A`, and fixed graph policy
`P`. The claim is conditional: an accepted replay has the same complete
`canonical_graph_bytes` as `Build` for the current source map and snapshot ID.
The comparison includes graph identity, source identity, policy, nodes, edges,
bindings, reasons, unknown/truncated frontiers, and the final seal.

The argument requires these premises:

1. The caller supplies a consistent source snapshot. The API defensively copies
   and validates the mapping; copying a mixed-time input cannot make it atomic.
2. Resolver code, its version, path/alias rules, Python parsing behavior, anchors,
   limits, and deterministic ordering remain fixed during the session. Updating
   resolver code in a live process is outside this contract.
3. Every source consultation affecting a graph is covered by its recorded source
   set, and every catalog consultation uses the two tracked query primitives.
4. Equal source SHA256 values imply equal relevant source bytes for this use;
   hash collisions are excluded from the argument. Missing source paths use a
   distinct absence state when hashes are compared.
5. Cached summaries depend only on their own `(path, source SHA256)`, preserve the
   existing static guards, and are read-only during replay. AST objects remain
   private read-only objects; they are not deeply immutable Python objects.
6. Calls are sequential and internal state is trusted. The session is not a
   concurrent API, and it neither accepts nor validates external serialized
   certificates.

Complete consultation coverage is a maintained premise supported by source
review and counterexamples. It is not a formal verification result.

## Code facts: the two observable catalog operations

[`ModuleCatalog`](../../src/contextproof/catalog.py) derives names from sorted,
deduplicated paths using the previous resolver's literal rules. Recognized
suffixes are case-insensitive `.py` and `.pyi`; `__init__` is collapsed to its
package; `src/pkg/x.py` contributes both `src.pkg.x` and `pkg.x`; empty names are
excluded. Candidate membership is constructed independently of parsing, so an
unparseable candidate can still cause ambiguity. Exact answers preserve path
identity and ordering, not just cardinality or content hashes.

| Operation | Recorded answer | Branches protected |
|---|---|---|
| `_Corpus.module_candidates(name)` | Complete ordered tuple, including `()` | Package uncertainty checks, missing imports, ambiguity, parse failure, explicit bindings and namespace fallback |
| `_Corpus.module_subtree_exists(name)` | Boolean, including `False` | Whether the exact module or any dotted descendant exists and namespace recursion is attempted |

The subtree predicate is equivalent to the old expression
`name in modules or any(key.startswith(name + '.') for key in modules)`.
The dot boundary distinguishes `pkg.a` from `pkg.ab`. It does not enumerate a
subtree: a stable `True` answer permits changes to unread siblings when subsequent
exact queries remain equal. Future code that enumerates descendants would need
to record that enumeration rather than reuse this Boolean contract.

The source audit found these consumers in
[`dependencies.py`](../../src/contextproof/dependencies.py) and
[`static_scope.py`](../../src/contextproof/static_scope.py):

- `resolve_module` obtains tracked candidates, records every candidate path as
  a source read, and invokes `module_lookup_uncertainty` before fallback. It uses
  candidates for ambiguity, parse availability and package-binding decisions.
- `module_lookup_uncertainty` also obtains tracked candidates and retains the
  package wildcard and `__getattr__` guards.
- The namespace-recursion branch uses `module_subtree_exists` after normalizing
  the actual import name. Relative imports under `src` therefore record the
  queried canonical alias, not the raw `.worker` spelling.
- The only remaining `.modules` access in the source package constructs a
  defensive compatibility view in `_load_texts`. No graph-resolution branch
  consumes that view directly. The review suite contains a supplementary static
  prohibition on direct access in the resolver and uncertainty guard.

The query dictionary stores one answer for each distinct `(kind, name)` pair.
Repeated queries have the same answer within an immutable catalog, so recording
the answer once is sufficient for replay; it is not an ordered execution trace.

The module-value early return, excessive qualified depth, lexical/dynamic
uncertainty, and depth-budget cutoff occur before a catalog query when that is
what the original resolver does. A genuine empty query trace is permitted. The
cache does not invent queries for branches the resolver never took.

## Code facts: source guards and state publication

[`build_graph`](../../src/contextproof/graph.py) finalizes source reads from
`lookup_paths`, every supplied anchor path, and every graph-node path.
`resolve_name` records its source path before unsuccessful binding checks;
`resolve_module` records candidate paths before uncertainty, parse-failure or
node-budget exits. Consequently the source guard also covers:

- A package read for a negative attribute check that never becomes a node.
- Wildcard, `__getattr__`, explicit/dynamic bindings and class-body `global`
  guards that may prevent a submodule fallback.
- An unparseable candidate or a resolved target excluded by the node budget.
- An absent anchor path whose later appearance changes the source state.

Catalog equality cannot replace these reads. An empty namespace gaining an empty
`__init__.py` must rebuild even if graph bytes initially agree, so the new package
read is captured before a later `__getattr__` or wildcard edit. Conversely a
depth-zero graph can have no module queries and retain its original truncated
frontier. A hit never upgrades an unknown graph to complete.

`GraphSession` copies anchors at construction and owns its depth/node policy.
Each update still copies and validates the full source map, hashes all supplied
source strings, and builds the current catalog for the new catalog modes. The
guards differ only in their catalog acceptance condition:

| Mode | Catalog condition, in addition to unchanged consulted-source hashes |
|---|---|
| `incremental_read_set` | Historical equality of all source-path keys |
| `incremental_catalog_coarse_guard` | A valid empty query trace, or equality of all source-path keys |
| `incremental_catalog_root_guard` | Equal complete module/candidate membership beneath every queried canonical root |
| `incremental_catalog_read_set` | Equal answers for every recorded exact and subtree query |

When all path keys agree, the catalog modes may skip individual query comparison
because the catalog is a deterministic function of those keys. Source hashes and
trace validity are still checked. A missing trace, non-dictionary trace or root
guard, absent version, or unsupported version causes reconstruction; it is not
treated as a legitimate zero-query certificate. Versioning protects the stored
trace format and does not permit changing resolver semantics within a session.

Each rebuilding anchor clears `lookup_paths` and `catalog_queries`, then copies
its own finalized observations. Reused graphs copy their previous reads and
observations. Fixed anchors can therefore share one corpus without sharing an
observation dictionary. Candidate answers and root-membership values are tuples;
the stored trace containers are private copied dictionaries, not externally
exposed immutable proof objects.

[`ModuleCache.for_snapshot`](../../src/contextproof/module_cache.py) creates a
candidate cache containing only current-hash summaries, including parse-failure
summaries. After all anchors succeed, the session publishes hashes, graphs,
source sets, query traces, root guards, versions and the candidate module cache.
A second-anchor failure leaves the previous committed state usable. Returned
graphs are deep copies; replay changes the provider snapshot ID and reseals the
copied graph. Query metadata and audit counters are outside the sealed payload.

## Conditional replay argument

Consider the prior successful build's consultations in their actual execution
order. At the first consultation, fixed local inputs and unchanged consulted
source bytes or catalog answer give the same resolver branch. Inductively,
unchanged previous answers produce the same local state, next query, and next
answer. A repeated query is covered by the same stored answer. Source-local
summaries supply the same guarded syntax facts, so recursion, queue order,
budget decisions and error/unknown reasons also agree. The run terminates with
the same graph content before provider identity and sealing are applied.

The fine guard directly requires the catalog answers used by this induction.
The coarse guard implies their equality when source-path keys agree; a genuine
zero-query run needs no catalog premise. The root guard implies equal exact and
subtree answers for queries under each protected canonical root, including aliases
and negative answers. Its empty-root case conservatively protects the entire
module map. All three retain the same consulted-source premise.

Copying the prior graph, replacing its snapshot ID and resealing therefore
produces the same canonical bytes as fresh reconstruction under these premises.
This preserves even a resolver error or incomplete result. It does not establish
that the resolver's result describes every Python runtime behavior.

## Tests and unresolved evidence boundaries

The preimplementation acceptance specification contains C01–C24. Its executable
fixtures are in
[`test_catalog_reuse_review.py`](../../tests/test_catalog_reuse_review.py): fixed
fresh expectations, four-mode guard decisions, aliases/ambiguity, missing exact
and subtree answers, two-update empty-init dependency acquisition, parse failures,
unknown/truncated preservation, multi-anchor isolation, mutation isolation,
certificate fallback and failure rollback. C04/C05 exercise catalog changes
within a queried root; C01/C02/C22 are zero-query controls.

The review suite was executed successfully during development. It also exposes
deliberately unsound test-only variants that discard empty exact answers, false
or true subtree answers, consulted package hashes, or uncertainty guards. The
guard-bypass tests compare against a saved guarded fresh graph, so candidate and
oracle cannot both silently adopt that injected failure. These variants are test
sensitivity checks, never supported modes or performance comparators.

[`test_module_catalog.py`](../../tests/test_module_catalog.py) separately compares
the new index with the historical literal alias/subtree expressions. Existing
reuse/index/oracle tests provide compatibility coverage. Final combined test
counts belong to the completed validation record; this note does not add partial
runs together. Finite tests and source review support the stated assumptions,
but do not prove exhaustive coverage of future resolver changes. A new consumer
must extend the observation contract or use a conservative catalog guard.

Fresh reconstruction with the same resolver is a replay oracle. Independent
runtime/semantic labels, agent-task outcomes and generalization require separate
evidence. This note reports no performance result or claim of scientific maturity.

## Established ideas and scoped adaptation

The following primary sources were read on 2026-10-14. The relationships are our
interpretation; the upstream projects have not assessed this implementation.

- [TypeScript v5.9.3 `resolutionCache.ts`](https://github.com/microsoft/TypeScript/blob/v5.9.3/src/compiler/resolutionCache.ts#L89-L169)
  retains failed lookup and affecting locations, with directory/file watchers and
  [invalidation processing](https://github.com/microsoft/TypeScript/blob/v5.9.3/src/compiler/resolutionCache.ts#L1535-L1588).
  Negative lookup invalidation already exists; our bounded source-map graph API
  does not reproduce its module-resolution or watch service.
- [mypy v1.18.2 `server/deps.py`](https://github.com/python/mypy/blob/v1.18.2/mypy/server/deps.py#L1-L71)
  uses triggers for affected locations and module creation/deletion. It also
  [records missing module attributes and logical dependencies](https://github.com/python/mypy/blob/v1.18.2/mypy/server/deps.py#L626-L657).
  Previously absent names becoming relevant are established Python-tooling concerns.
- [Bazel Skyframe](https://bazel.build/reference/skyframe) requires registered
  dependencies for incremental correctness and distinguishes file state,
  contents and directory-listing values. This supports separating source reads
  from catalog observations, without transferring Bazel's guarantees here.
- [Tup's official manual](https://gittup.org/tup/manual.html) describes ghost nodes
  for attempted access to nonexistent files and records command file reads as
  dependencies. Our static name-resolution observations concern a different
  object, while following an established negative-dependency principle.

No compiler/build-system benchmark or exhaustive priority search follows from
this reading. The contribution considered here is a scoped engineering adaptation
with inspectable observation coverage and counterexamples, not invention of
dependency traces, negative dependencies or fine-grained invalidation.

[简体中文](../zh/CATALOG_SOUNDNESS.md) · [Module-summary design](INCREMENTAL_DESIGN.md)
