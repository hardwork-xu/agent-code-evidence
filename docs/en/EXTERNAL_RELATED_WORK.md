# External localization: established mechanisms and contribution boundary

Official sources were checked on2026-10-14. This is a targeted comparison, not a systematic literature review. No external implementation below was run; their paper numbers are not included in local measurement tables.

| Work | Fixed code revision | Established mechanism | Comparison boundary |
|---|---|---|---|
| [Agentless](https://arxiv.org/html/2407.01489v2) | `5ce5888b9f149beaace393957a55ea8ee46c9f71` | Hierarchical file/symbol/edit localization, LibCST skeletons, repair and validation | Our static issue-only adapter is not its LLM/embedding/repair system |
| [Aider repo map](https://aider.chat/docs/repomap.html) | `5dc9490bb35f9729ef2c95d00a19ccd30c26339c` | Tree-sitter definitions/references, dependency graph and personalized PageRank, budgeted maps, mtime caches/refresh | A symbol map and exact declaration text have different output contracts; strict UTF-8 bytes are not its approximate token allowance |
| [SWE-bench](https://arxiv.org/html/2310.06770v3) | `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e` | Issue→Lucene/Pyserini BM25, context limits, reference edited-file recall | The official pipeline excludes tests and uses files/top20; our internal BM25 uses all Python/tests and windows/declarations |
| [ContextBench](https://arxiv.org/html/2602.05892v3) | `1436c28a8eb95496da4ea69ad458b9f8a8eb7d61` | File/definition/line precision and coverage, interval unions, process context evaluation | Expert reference context differs from patch edits; its gold dataset was not used because dataset permission remained unestablished |

Fixed code positions are in [the source register](../../benchmarks/external_context/related-work-pins.json). Reading published design/source does not establish a strict clean-room implementation. No third-party code from these projects was copied into this adapter.

Graph/AST retrieval, byte/token budgets, caches and overlap metrics already have precedents. The existing research branch's narrower engineering contribution is an explicit versioned source-evidence contract, observable uncertainty, conservative read-set invalidation and tested replay cost. Dependency tracking itself also has prior art; see [the incremental related-work analysis](RELATED_WORK.md).

The39-task pilot observes one base revision per task. It can assess static edit localization under this implementation and budget, and can refute a broad graph-benefit claim under those conditions. It cannot establish cross-version recovery, semantic freshness, agent repair gains, academic firstness or mature research. Any stronger comparison requires an actual pinned external adapter, a fair native/shared-corpus protocol and untouched validation inputs.

[中文](../zh/EXTERNAL_RELATED_WORK.md)
