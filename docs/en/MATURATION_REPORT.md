# Incremental code-evidence reuse and task execution witnesses

**Status: reproducible engineering research report; no claim of submission maturity, SOTA, independent human review or coding-agent improvement.** Tables and verdicts are generated from validated completed records. The invalid task pilot supplies no result claim.

## Abstract

We evaluate a process-local application of dependency tracking to bounded Python source-evidence graphs. A repository-held-out convenience sample contains 4 repositories, 8 pinned revisions each and 96 fixed anchors. The candidate is compared with persistent module indexing plus whole-corpus-equality reuse. 4/4 repositories reach the 20.0% replay reduction threshold; the timing target is **met** and the RSS gate is **met**. Completed records contain 0 canonical mismatches against uncached reconstruction. 768/768 reference graphs retain incomplete frontiers: the cache preserves those unknowns and does not certify fresh semantics. A separate, corrected 9-case development study executes original upstream assertion bodies with reviewed fixture adaptations. Graph and matched-line BM25 macro execution-witness recall are 53.9% and 37.4%. These are separate observations about replay cost and task-conditioned source coverage; neither establishes context sufficiency, semantic soundness or model-task benefit.

## 1. Research questions and contribution boundary

RQ1 asks whether selective read-set replay adds value beyond both persistent indexing and the cheap whole-corpus guard, at disclosed end-to-end ingestion and memory costs. RQ2 asks which lines actually executed by specific upstream assertions are present in each supplied context. The second label is obtained from Python execution, independently of static dependency extraction, but is not human gold context. Source identity, resolver equality, execution coverage and agent success remain distinct claims.

Module summaries cache parsed source and guarded bindings by path and source hash; cross-file resolution uses the current catalog. Read sets include unsuccessful candidate lookups. Catalog changes conservatively invalidate reuse; incomplete frontiers remain incomplete. Graphs are copied/resealed, old summaries are pruned, and session state is published only after the update succeeds. Every source byte is still hashed; avoiding index work does not remove archive I/O, decoding or graph-output costs. [Exact mechanism and assumptions](INCREMENTAL_DESIGN.md).

## 2. Frozen design and comparators

The four repositories are absent from the historical/development source corpora. The latest stable release and seven contiguous first parents were pinned before graph outcomes. Exactly 24 top-level function identities per repository were SHA-ranked in the oldest version and never reselected. Duplicate declarations, missing/ambiguous anchors and every transition remain. This is a local prespecification, not public preregistration.

Source-only inspection found 15/28 source-identical transitions. Before any held-out graph/timing observation, an explicit amendment added IWCG and strengthened the primary comparator from IDX to IWCG. Original protocol and manifest bytes remain archived; sources, anchors and targets were unchanged. All methods share one indexed corpus within a snapshot. The public default strict completeness policy is unchanged; this experiment evaluates the named experimental modes.

| ID | Mode | Behavior |
|---|---|---|
| AST | `warm_ast_rebuild` | warm AST; rebuild bindings and graphs |
| WCG | `whole_corpus_guard` | warm AST; reuse only an equal source map |
| RS | `read_set_any_status` | warm AST; selective reuse preserving every frontier |
| IDX | `incremental_index_rebuild` | persistent module summaries; rebuild every graph |
| IWCG | `incremental_whole_corpus_guard` | persistent summaries plus whole-corpus reuse; PRIMARY BASELINE |
| IRS | `incremental_read_set` | persistent summaries plus read-set reuse; CANDIDATE |

[Final protocol](../../benchmarks/incremental_holdout/protocol.json) · [Initial protocol](../../benchmarks/incremental_holdout/initial-protocol.json) · [Frozen source/anchor manifest](../../benchmarks/incremental_holdout/manifest.json).

## 3. Workload and measurement boundaries

| Repository | Release | Files at first version | Max source bytes | Anchors | Changed transitions | Identical transitions |
|---|---|---|---|---|---|---|
| pallets/jinja | 3.1.6 | 25 | 490070 | 24 | 4 | 3 |
| encode/starlette | 1.7.0 | 36 | 257955 | 24 | 6 | 1 |
| agronholm/anyio | 4.15.1 | 46 | 529017 | 24 | 2 | 5 |
| Python-Markdown/markdown | 3.11.0 | 32 | 327320 | 24 | 1 | 6 |

One complete-trajectory warmup and 5 measured trajectories per method are rotated in whole-method order. Each starts with a fresh GraphSession. The primary observation is the sum of seven replay transitions per trajectory; tables report its median and min/max, not a pooled transition or anchor statistic. Local archive reads, hashes, decompression, decoding, source checks, indexing, guards, copying/sealing and fallback are timed. Downloads, canonical comparison and result serialization are outside timing. Capture is separately reported, and capture plus replay remains a required secondary result; process startup/session construction is not included in these timing sums. Changed-only strata are descriptive and never replace the fixed primary endpoint. Background OS activity is not controlled.

## 4. Primary results and target decisions

The prespecified speed criterion is at least 20.0% lower median replay time in at least 3/4 repositories. Every repository must also remain at no more than 2× baseline median uninstrumented peak RSS and 512 MiB. **Timing: met; memory: met; combined gates: met.** Positive reduction is faster; a negative value is a regression.

| Repository | IWCG ms [min,max] | IRS ms [min,max] | Reduction | Speed gate | RSS IRS/IWCG | Memory gate |
|---|---|---|---|---|---|---|
| pallets/jinja | 1959.32 [1939.14, 1991.39] | 1279.66 [1250.61, 1374.68] | +34.7% | met | 0.995× | met |
| encode/starlette | 2011.70 [1985.94, 2029.13] | 888.80 [879.42, 954.00] | +55.8% | met | 0.895× | met |
| agronholm/anyio | 481.03 [477.37, 507.64] | 290.42 [269.12, 297.37] | +39.6% | met | 1.026× | met |
| Python-Markdown/markdown | 641.98 [631.89, 678.15] | 427.87 [408.17, 501.84] | +33.4% | met | 0.998× | met |

Validation matched 768 distinct snapshot/anchor references, 23040 emitted timing graph digests and 27648 emitted memory-run graph digests to freshly parsed per-snapshot references, with zero canonical mismatches. These repeated outputs are not independent semantic test cases.

## 5. All methods, adverse strata and startup cost

All cells are ms median [minimum, maximum] across trajectory totals. Changed-only totals contain different numbers of transitions by repository; compare methods within the same repository, not these totals across repositories.

| Repository | Method | Replay | Changed-only replay | Capture | Capture + replay |
|---|---|---|---|---|---|
| pallets/jinja | AST | 3763.34 [3759.55, 3864.95] | 2141.36 [2137.95, 2175.38] | 584.75 [579.73, 622.33] | 4346.09 [4343.80, 4487.28] |
| pallets/jinja | WCG | 2252.88 [2226.34, 2295.13] | 2162.98 [2136.10, 2200.37] | 585.71 [579.09, 603.50] | 2838.60 [2823.11, 2898.63] |
| pallets/jinja | RS | 1560.49 [1528.33, 1571.16] | 1457.34 [1436.24, 1480.33] | 585.92 [577.13, 599.19] | 2146.22 [2123.98, 2170.35] |
| pallets/jinja | IDX | 3239.05 [3199.60, 3285.30] | 1860.98 [1842.43, 1924.91] | 585.05 [578.93, 623.15] | 3829.40 [3809.94, 3864.23] |
| pallets/jinja | IWCG | 1959.32 [1939.14, 1991.39] | 1867.39 [1824.66, 1878.68] | 579.15 [574.05, 590.71] | 2548.13 [2518.28, 2565.44] |
| pallets/jinja | IRS | 1279.66 [1250.61, 1374.68] | 1167.56 [1156.46, 1250.33] | 588.15 [580.20, 639.64] | 1862.71 [1838.35, 2014.31] |
| encode/starlette | AST | 2616.25 [2587.77, 2825.43] | 2252.28 [2219.09, 2444.05] | 402.48 [394.40, 406.63] | 3018.73 [2994.40, 3219.83] |
| encode/starlette | WCG | 2299.66 [2273.17, 2325.24] | 2248.66 [2221.99, 2271.71] | 397.62 [393.75, 417.39] | 2693.41 [2678.84, 2742.64] |
| encode/starlette | RS | 1031.87 [1022.98, 1041.67] | 971.52 [969.49, 980.91] | 395.63 [394.88, 398.44] | 1426.75 [1421.42, 1437.30] |
| encode/starlette | IDX | 2279.73 [2268.15, 2315.07] | 1953.53 [1949.17, 1998.41] | 409.97 [403.53, 422.71] | 2698.03 [2675.12, 2718.61] |
| encode/starlette | IWCG | 2011.70 [1985.94, 2029.13] | 1959.78 [1933.95, 1976.57] | 395.93 [393.07, 403.29] | 2414.33 [2383.02, 2425.06] |
| encode/starlette | IRS | 888.80 [879.42, 954.00] | 836.52 [827.26, 902.66] | 405.20 [391.26, 413.32] | 1296.28 [1283.93, 1345.25] |
| agronholm/anyio | AST | 1827.06 [1818.13, 1849.68] | 516.50 [514.93, 543.60] | 310.14 [307.81, 327.28] | 2134.87 [2127.95, 2176.96] |
| agronholm/anyio | WCG | 677.73 [649.00, 683.19] | 513.99 [510.10, 544.58] | 314.76 [313.86, 325.24] | 992.49 [963.07, 999.64] |
| agronholm/anyio | RS | 463.51 [437.56, 465.06] | 301.84 [300.08, 324.98] | 314.20 [309.03, 328.31] | 774.08 [759.73, 777.72] |
| agronholm/anyio | IDX | 1197.58 [1177.55, 1209.24] | 341.13 [337.43, 343.96] | 313.84 [305.05, 321.87] | 1508.17 [1499.41, 1523.08] |
| agronholm/anyio | IWCG | 481.03 [477.37, 507.64] | 341.15 [339.88, 368.96] | 313.51 [308.52, 331.48] | 810.22 [792.40, 821.15] |
| agronholm/anyio | IRS | 290.42 [269.12, 297.37] | 131.49 [128.03, 153.22] | 313.45 [310.91, 331.66] | 601.63 [593.93, 610.82] |
| Python-Markdown/markdown | AST | 2577.57 [2563.66, 2759.55] | 364.96 [360.16, 546.08] | 392.13 [385.25, 413.75] | 2972.32 [2950.15, 3151.68] |
| Python-Markdown/markdown | WCG | 690.87 [685.41, 701.91] | 371.93 [361.88, 380.10] | 396.48 [395.83, 403.97] | 1092.20 [1081.24, 1101.88] |
| Python-Markdown/markdown | RS | 462.87 [454.02, 469.31] | 135.81 [134.27, 138.70] | 395.70 [384.43, 397.24] | 852.76 [842.84, 866.55] |
| Python-Markdown/markdown | IDX | 2292.58 [2245.57, 2425.46] | 338.74 [317.42, 352.86] | 402.12 [394.68, 421.56] | 2694.70 [2640.25, 2847.02] |
| Python-Markdown/markdown | IWCG | 641.98 [631.89, 678.15] | 320.03 [317.80, 345.87] | 392.52 [384.08, 403.56] | 1030.75 [1015.97, 1081.71] |
| Python-Markdown/markdown | IRS | 427.87 [408.17, 501.84] | 98.72 [92.97, 106.63] | 396.11 [388.47, 408.03] | 822.70 [800.87, 903.46] |

## 6. Uninstrumented resident memory

Each cell is MiB median [minimum, maximum] from 3 fresh processes executing the complete 8-version trajectory, without warmup or tracemalloc. The RSS gate uses only these processes. RSS includes interpreter/imports, source maps, transient objects, indexes and graphs; it is not cache-only storage. Native high-water units are normalized from bytes on [macOS (Apple XNU manual)](https://raw.githubusercontent.com/apple-oss-distributions/xnu/main/bsd/man/man2/getrusage.2) and KiB on [Linux (getrusage manual)](https://man7.org/linux/man-pages/man2/getrusage.2.html).

| Repository | Method | RSS peak MiB [min,max] |
|---|---|---|
| pallets/jinja | AST | 68.22 [67.94, 69.88] |
| pallets/jinja | WCG | 70.11 [66.94, 70.47] |
| pallets/jinja | RS | 68.12 [65.83, 71.61] |
| pallets/jinja | IDX | 69.05 [67.38, 72.17] |
| pallets/jinja | IWCG | 70.59 [70.58, 73.11] |
| pallets/jinja | IRS | 70.25 [67.81, 70.73] |
| encode/starlette | AST | 66.98 [62.95, 73.45] |
| encode/starlette | WCG | 75.88 [72.17, 78.19] |
| encode/starlette | RS | 71.41 [70.86, 72.75] |
| encode/starlette | IDX | 76.12 [72.08, 77.05] |
| encode/starlette | IWCG | 75.55 [62.16, 77.78] |
| encode/starlette | IRS | 67.64 [63.25, 71.27] |
| agronholm/anyio | AST | 63.69 [63.28, 65.03] |
| agronholm/anyio | WCG | 63.98 [63.28, 65.14] |
| agronholm/anyio | RS | 63.86 [63.00, 64.27] |
| agronholm/anyio | IDX | 63.53 [62.61, 66.11] |
| agronholm/anyio | IWCG | 63.00 [62.97, 63.45] |
| agronholm/anyio | IRS | 64.64 [64.58, 65.88] |
| Python-Markdown/markdown | AST | 51.14 [49.86, 57.50] |
| Python-Markdown/markdown | WCG | 55.81 [55.33, 57.06] |
| Python-Markdown/markdown | RS | 51.47 [51.38, 56.73] |
| Python-Markdown/markdown | IDX | 52.47 [51.48, 57.72] |
| Python-Markdown/markdown | IWCG | 56.45 [55.27, 57.36] |
| Python-Markdown/markdown | IRS | 56.31 [55.69, 56.34] |

Observed candidate median RSS increases relative to IWCG: agronholm/anyio +2.6%. Passing the memory budget is not a claim of lower memory use.

## 7. Separately traced Python allocations

These fresh processes enable tracemalloc before the first source load and are separate from both timing and RSS-gate processes. Current traced retention is sampled after releasing returned graphs and collecting garbage, while the session and current source map remain alive. Peak/current traced bytes describe allocations observed since tracing started, not all process memory; tracing itself changes costs. [Python 3.12 tracemalloc documentation](https://docs.python.org/3.12/library/tracemalloc.html).

| Repository | Method | Python peak MiB [min,max] | Final retained MiB [min,max] |
|---|---|---|---|
| pallets/jinja | AST | 22.71 [22.71, 22.71] | 18.67 [18.67, 18.67] |
| pallets/jinja | WCG | 22.71 [22.71, 22.71] | 18.66 [18.66, 18.66] |
| pallets/jinja | RS | 22.28 [22.28, 22.28] | 18.66 [18.66, 18.66] |
| pallets/jinja | IDX | 22.72 [22.72, 22.72] | 19.00 [19.00, 19.00] |
| pallets/jinja | IWCG | 22.71 [22.71, 22.71] | 19.00 [19.00, 19.00] |
| pallets/jinja | IRS | 22.46 [22.46, 22.46] | 19.00 [19.00, 19.00] |
| encode/starlette | AST | 17.09 [17.09, 17.09] | 12.56 [12.56, 12.56] |
| encode/starlette | WCG | 17.09 [17.09, 17.09] | 12.56 [12.56, 12.56] |
| encode/starlette | RS | 16.97 [16.97, 16.97] | 12.55 [12.55, 12.55] |
| encode/starlette | IDX | 17.09 [17.09, 17.09] | 12.89 [12.89, 12.89] |
| encode/starlette | IWCG | 17.09 [17.09, 17.09] | 12.89 [12.89, 12.89] |
| encode/starlette | IRS | 16.97 [16.97, 16.98] | 12.88 [12.88, 12.88] |
| agronholm/anyio | AST | 22.11 [22.11, 22.12] | 18.87 [18.87, 18.87] |
| agronholm/anyio | WCG | 22.11 [22.11, 22.11] | 18.86 [18.86, 18.86] |
| agronholm/anyio | RS | 21.23 [21.23, 21.23] | 18.85 [18.85, 18.85] |
| agronholm/anyio | IDX | 22.09 [22.09, 22.09] | 19.47 [19.47, 19.47] |
| agronholm/anyio | IWCG | 22.08 [22.08, 22.08] | 19.46 [19.46, 19.46] |
| agronholm/anyio | IRS | 21.23 [21.23, 21.23] | 19.46 [19.46, 19.46] |
| Python-Markdown/markdown | AST | 15.43 [15.43, 15.43] | 12.39 [12.39, 12.39] |
| Python-Markdown/markdown | WCG | 15.43 [15.42, 15.43] | 12.39 [12.39, 12.39] |
| Python-Markdown/markdown | RS | 14.50 [14.50, 14.50] | 12.39 [12.38, 12.39] |
| Python-Markdown/markdown | IDX | 15.42 [15.42, 15.42] | 12.62 [12.62, 12.62] |
| Python-Markdown/markdown | IWCG | 15.41 [15.41, 15.41] | 12.61 [12.61, 12.61] |
| Python-Markdown/markdown | IRS | 14.54 [14.54, 14.54] | 12.61 [12.61, 12.61] |

Primary pair, post-GC retention by version (MiB); eight revisions cannot prove a long-running memory bound:

| Repository | Version | Commit | IWCG [min,max] | IRS [min,max] |
|---|---|---|---|---|
| pallets/jinja | 0 | eda8fe86fd | 18.97 [18.97, 18.97] | 18.97 [18.97, 18.97] |
| pallets/jinja | 1 | 8d58859265 | 18.97 [18.97, 18.97] | 18.97 [18.97, 18.97] |
| pallets/jinja | 2 | b4ffc8ff29 | 18.98 [18.98, 18.98] | 18.98 [18.98, 18.98] |
| pallets/jinja | 3 | ab8218c7a1 | 18.99 [18.99, 18.99] | 18.99 [18.99, 18.99] |
| pallets/jinja | 4 | bc68d4efa9 | 18.99 [18.99, 18.99] | 18.99 [18.99, 18.99] |
| pallets/jinja | 5 | 033c20015c | 19.00 [19.00, 19.00] | 19.00 [19.00, 19.00] |
| pallets/jinja | 6 | 90457bbf33 | 18.99 [18.99, 18.99] | 18.99 [18.99, 18.99] |
| pallets/jinja | 7 | 15206881c0 | 19.00 [19.00, 19.00] | 19.00 [19.00, 19.00] |
| encode/starlette | 0 | 485aca4e79 | 12.84 [12.84, 12.84] | 12.84 [12.84, 12.84] |
| encode/starlette | 1 | f03f65c2f9 | 12.82 [12.82, 12.82] | 12.82 [12.82, 12.82] |
| encode/starlette | 2 | 76fd00f1e2 | 12.83 [12.83, 12.83] | 12.53 [12.53, 12.53] |
| encode/starlette | 3 | 03f12b7fcf | 12.84 [12.83, 12.84] | 12.83 [12.83, 12.83] |
| encode/starlette | 4 | 57de5fa9c2 | 12.87 [12.87, 12.87] | 12.87 [12.87, 12.87] |
| encode/starlette | 5 | 1f08daf162 | 12.88 [12.88, 12.88] | 12.69 [12.69, 12.69] |
| encode/starlette | 6 | 4fe55eb264 | 12.88 [12.88, 12.88] | 12.88 [12.88, 12.88] |
| encode/starlette | 7 | 2269e9a08c | 12.89 [12.89, 12.89] | 12.88 [12.88, 12.88] |
| agronholm/anyio | 0 | 9727dc5046 | 19.46 [19.46, 19.46] | 19.46 [19.46, 19.46] |
| agronholm/anyio | 1 | b825c3be7c | 19.43 [19.43, 19.43] | 19.43 [19.43, 19.43] |
| agronholm/anyio | 2 | 942e9a6552 | 19.44 [19.44, 19.44] | 19.44 [19.44, 19.44] |
| agronholm/anyio | 3 | 033fc52b8f | 19.45 [19.44, 19.45] | 19.44 [19.44, 19.44] |
| agronholm/anyio | 4 | d137692a90 | 19.45 [19.45, 19.45] | 19.45 [19.45, 19.45] |
| agronholm/anyio | 5 | 9283662595 | 19.45 [19.45, 19.45] | 19.45 [19.45, 19.45] |
| agronholm/anyio | 6 | 0ecf5ed98d | 19.46 [19.46, 19.46] | 19.45 [19.45, 19.45] |
| agronholm/anyio | 7 | ffcd1542cd | 19.46 [19.46, 19.46] | 19.46 [19.46, 19.46] |
| Python-Markdown/markdown | 0 | 5d1363ce4b | 12.61 [12.61, 12.61] | 12.61 [12.61, 12.61] |
| Python-Markdown/markdown | 1 | 8a96db59e3 | 12.59 [12.59, 12.59] | 12.59 [12.59, 12.59] |
| Python-Markdown/markdown | 2 | 36cdbd3c7e | 12.59 [12.59, 12.59] | 12.59 [12.59, 12.59] |
| Python-Markdown/markdown | 3 | 819fff96b0 | 12.59 [12.59, 12.59] | 12.59 [12.59, 12.59] |
| Python-Markdown/markdown | 4 | a5176b06f2 | 12.60 [12.60, 12.60] | 12.60 [12.60, 12.60] |
| Python-Markdown/markdown | 5 | 571f050f0c | 12.60 [12.60, 12.60] | 12.60 [12.60, 12.60] |
| Python-Markdown/markdown | 6 | 547a9349d4 | 12.61 [12.61, 12.61] | 12.61 [12.61, 12.61] |
| Python-Markdown/markdown | 7 | 0ffbf00cf6 | 12.61 [12.61, 12.61] | 12.61 [12.61, 12.61] |

## 8. Reuse and incomplete-output coverage

768/768 reference graphs have incomplete frontiers. Reuse counts are saved computations, not newly certified fresh semantics. Complete-graph counts are shown for every pinned version, once, from uncached references. All methods must preserve those same counts and canonical frontiers. The timing file stores completeness and graph digests rather than per-kind frontier histograms; no unrecorded histogram is inferred.

| Repository | Method | Reused in repetitions 1–5 | Anchors × transitions | Complete graphs in versions 0–7 |
|---|---|---|---|---|
| pallets/jinja | AST | 0, 0, 0, 0, 0 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| pallets/jinja | WCG | 72, 72, 72, 72, 72 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| pallets/jinja | RS | 149, 149, 149, 149, 149 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| pallets/jinja | IDX | 0, 0, 0, 0, 0 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| pallets/jinja | IWCG | 72, 72, 72, 72, 72 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| pallets/jinja | IRS | 149, 149, 149, 149, 149 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| encode/starlette | AST | 0, 0, 0, 0, 0 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| encode/starlette | WCG | 24, 24, 24, 24, 24 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| encode/starlette | RS | 159, 159, 159, 159, 159 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| encode/starlette | IDX | 0, 0, 0, 0, 0 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| encode/starlette | IWCG | 24, 24, 24, 24, 24 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| encode/starlette | IRS | 159, 159, 159, 159, 159 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| agronholm/anyio | AST | 0, 0, 0, 0, 0 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| agronholm/anyio | WCG | 120, 120, 120, 120, 120 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| agronholm/anyio | RS | 164, 164, 164, 164, 164 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| agronholm/anyio | IDX | 0, 0, 0, 0, 0 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| agronholm/anyio | IWCG | 120, 120, 120, 120, 120 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| agronholm/anyio | IRS | 164, 164, 164, 164, 164 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| Python-Markdown/markdown | AST | 0, 0, 0, 0, 0 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| Python-Markdown/markdown | WCG | 144, 144, 144, 144, 144 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| Python-Markdown/markdown | RS | 167, 167, 167, 167, 167 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| Python-Markdown/markdown | IDX | 0, 0, 0, 0, 0 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| Python-Markdown/markdown | IWCG | 144, 144, 144, 144, 144 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |
| Python-Markdown/markdown | IRS | 167, 167, 167, 167, 167 | 168 | 0, 0, 0, 0, 0, 0, 0, 0 |

## 9. Task-conditioned execution witness method

The separate task set contains 9 assertion cases from packaging, attrs and pluggy, using existing development release pairs. It is not held out. Exact after-version upstream function bodies run against both versions, with reviewed imports/arguments and fixture adaptations; the full pytest suite/conftest/setup hooks are not executed. Original future flags are preserved with dont_inherit=True. Pytest fixtures can change setup, scope and parameters, so an extracted body is not the full pytest environment. [Official fixture semantics](https://docs.pytest.org/en/stable/how-to/fixtures.html).

Each version runs twice traced and twice untraced in separate restricted macOS processes (72 children). Repeats and per-invocation assertion outcomes must agree; 9/9 cases pass that parity check. Imports/fixture setup precede the tracing window. The witness is the union of physical package lines executed by the after-version assertions across that case’s invocations; before-version outcomes provide change/control context. Generated attrs code is counted separately. Python tracing is thread-specific; these reviewed single-process callables do not provide a general multi-thread execution oracle. [Python 3.12 tracing](https://docs.python.org/3.12/library/sys.html#sys.settrace).

All methods receive the same pinned source and entrypoint hints. BM25 uses the upstream test text plus hints over 20-line windows at exactly the graph’s unique physical-line budget. Full source is an unbudgeted upper bound. Old graph lines are all charged as supplied context, but receive current-source credit only for exact, unique same-file span matches. The score is executed-line recall, not gold-context precision, token cost or repair success. 7/9 cases fail before and pass after; a release-pair difference does not identify one causal patch.

| Case | Before → after release | Original after-version test | Invocations per child |
|---|---|---|---|
| packaging-prereleases | 23.2 → 24.2 | [TestSpecifier.test_specifier_prereleases_detection](https://github.com/pypa/packaging/blob/d8e3b31b734926ebbcaff654279f6855a73e052f/tests/test_specifiers.py#L517) | 14 |
| packaging-specifier-iterable | 23.2 → 24.2 | [TestSpecifierSet.test_create_from_specifiers](https://github.com/pypa/packaging/blob/d8e3b31b734926ebbcaff654279f6855a73e052f/tests/test_specifiers.py#L659) | 1 |
| packaging-metadata-keywords | 23.2 → 24.2 | [TestMetadata.test_optional_defaults_to_none](https://github.com/pypa/packaging/blob/d8e3b31b734926ebbcaff654279f6855a73e052f/tests/test_metadata.py#L620) | 1 |
| attrs-makeclass-annotations | 23.2.0 → 24.3.0 | [TestMakeClass.test_annotations](https://github.com/python-attrs/attrs/blob/598494a618410490cfbe0c896b7a544f6d23e0d9/tests/test_make.py#L1187) | 1 |
| attrs-preinit-default | 23.2.0 → 24.3.0 | [TestAttributes.test_pre_init_kw_only_work_with_defaults](https://github.com/python-attrs/attrs/blob/598494a618410490cfbe0c896b7a544f6d23e0d9/tests/test_make.py#L698) | 2 |
| attrs-init-subclass | 23.2.0 → 24.3.0 | [TestFunctional.test_init_subclass](https://github.com/python-attrs/attrs/blob/598494a618410490cfbe0c896b7a544f6d23e0d9/tests/test_functional.py#L754) | 2 |
| pluggy-set-blocked | 1.3.0 → 1.5.0 | [test_set_blocked](https://github.com/pytest-dev/pluggy/blob/f8aa4a009716a7994f2f6c1947d9fa69feccbdd5/testing/test_pluginmanager.py#L95) | 1 |
| pluggy-registration-name | 1.3.0 → 1.5.0 | [test_pm_name](https://github.com/pytest-dev/pluggy/blob/f8aa4a009716a7994f2f6c1947d9fa69feccbdd5/testing/test_pluginmanager.py#L76) | 1 |
| pluggy-call-extra | 1.3.0 → 1.5.0 | [test_call_extra](https://github.com/pytest-dev/pluggy/blob/f8aa4a009716a7994f2f6c1947d9fa69feccbdd5/testing/test_pluginmanager.py#L400) | 1 |

[Frozen test/source manifest](../../benchmarks/task_evidence/manifest.json) · [Task execution and fixture adaptation protocol](../../benchmarks/task_evidence/PROTOCOL.md) · [Source fetch, isolation preflight and reproduction commands](../../benchmarks/task_evidence/README.md).

## 10. Per-case and per-repository task results

Each cell below is recall / supplied physical lines. Graph recall is greater than BM25 in 7 cases, lower in 1, and equal in 1. These dependent convenience cases do not support a significance or general superiority claim. Lower graph-recall cases: pluggy-registration-name.

Graph recall is also below the direct-anchor context in packaging-prereleases. At repository level, graph macro recall is lower than BM25 for pluggy. These observed coverage comparisons do not identify the causal reason.

| Case | Full source | Anchors | Graph | BM25 | Old graph |
|---|---|---|---|---|---|
| packaging-prereleases | 100.0% / 5653 | 23.0% / 50 | 9.8% / 34 | 0.0% / 34 | 0.0% / 34 |
| packaging-specifier-iterable | 100.0% / 5653 | 4.1% / 37 | 94.5% / 1179 | 21.9% / 1179 | 0.0% / 1168 |
| packaging-metadata-keywords | 100.0% / 5653 | 30.8% / 56 | 100.0% / 3484 | 100.0% / 3484 | 0.0% / 127 |
| attrs-makeclass-annotations | 100.0% / 5823 | 7.1% / 163 | 28.7% / 755 | 3.6% / 755 | 4.5% / 996 |
| attrs-preinit-default | 100.0% / 5823 | 5.7% / 387 | 82.6% / 2326 | 43.3% / 2326 | 12.6% / 2313 |
| attrs-init-subclass | 100.0% / 5823 | 15.0% / 222 | 99.8% / 2129 | 66.2% / 2129 | 17.2% / 2372 |
| pluggy-set-blocked | 100.0% / 1666 | 4.2% / 4 | 4.2% / 4 | 2.1% / 4 | 4.2% / 4 |
| pluggy-registration-name | 100.0% / 1666 | 20.5% / 50 | 20.5% / 437 | 87.2% / 437 | 20.5% / 420 |
| pluggy-call-extra | 100.0% / 1666 | 13.5% / 33 | 45.2% / 171 | 12.7% / 171 | 31.7% / 170 |

| Group | Method | Cases | Macro recall | Mean supplied lines |
|---|---|---|---|---|
| all | Anchors | 9 | 13.8% | 111.33 |
| all | Full source | 9 | 100.0% | 4380.67 |
| all | Graph | 9 | 53.9% | 1168.78 |
| all | BM25 | 9 | 37.4% | 1168.78 |
| all | Old graph | 9 | 10.1% | 844.89 |
| attrs | Anchors | 3 | 9.3% | 257.33 |
| attrs | Full source | 3 | 100.0% | 5823.00 |
| attrs | Graph | 3 | 70.3% | 1736.67 |
| attrs | BM25 | 3 | 37.7% | 1736.67 |
| attrs | Old graph | 3 | 11.5% | 1893.67 |
| packaging | Anchors | 3 | 19.3% | 47.67 |
| packaging | Full source | 3 | 100.0% | 5653.00 |
| packaging | Graph | 3 | 68.1% | 1565.67 |
| packaging | BM25 | 3 | 40.6% | 1565.67 |
| packaging | Old graph | 3 | 0.0% | 443.00 |
| pluggy | Anchors | 3 | 12.7% | 29.00 |
| pluggy | Full source | 3 | 100.0% | 1666.00 |
| pluggy | Graph | 3 | 23.3% | 204.00 |
| pluggy | BM25 | 3 | 34.0% | 204.00 |
| pluggy | Old graph | 3 | 18.8% | 198.00 |

## 11. Every recorded task frontier and negative state

9/9 current task graphs contain frontiers. Nothing is upgraded to fresh merely because it was cached or covers an executed line. Every case’s anchor status, frontier-kind count, missing anchors, old-span state and old-graph validation is retained below, including before failures and generated-code locations.

| Case | Before → after | Witness lines | Generated locations | Anchor states | All frontier counts | Missing anchors | Old-span states | Old-graph validation |
|---|---|---|---|---|---|---|---|---|
| packaging-prereleases | False → True | 61 | 0 | unresolved=3 | unresolved=5 | {"after": [], "before": []} | changed_or_missing_spans=1, uniquely_unchanged_spans=1 | {"fresh": false, "status": "changed"} |
| packaging-specifier-iterable | False → True | 73 | 0 | unresolved=1 | unresolved=57 | {"after": [], "before": []} | changed_or_missing_spans=14, uniquely_unchanged_spans=6 | {"fresh": false, "status": "changed"} |
| packaging-metadata-keywords | False → True | 13 | 0 | unresolved=1 | truncated=17, unresolved=109 | {"after": [], "before": []} | changed_or_missing_spans=2, uniquely_unchanged_spans=1 | {"fresh": false, "status": "changed"} |
| attrs-makeclass-annotations | False → True | 533 | 3 | unresolved=2 | truncated=1, unresolved=37 | {"after": [], "before": []} | changed_or_missing_spans=11, uniquely_unchanged_spans=6 | {"fresh": false, "status": "changed"} |
| attrs-preinit-default | False → True | 609 | 5 | unresolved=1 | truncated=10, unresolved=65 | {"after": [], "before": []} | changed_or_missing_spans=19, uniquely_unchanged_spans=17 | {"fresh": false, "status": "changed"} |
| attrs-init-subclass | False → True | 400 | 6 | unresolved=1 | truncated=8, unresolved=87 | {"after": [], "before": []} | changed_or_missing_spans=28, uniquely_unchanged_spans=18 | {"fresh": false, "status": "changed"} |
| pluggy-set-blocked | False → True | 48 | 0 | unresolved=1 | unresolved=2 | {"after": [], "before": []} | uniquely_unchanged_spans=1 | {"fresh": false, "status": "unresolved"} |
| pluggy-registration-name | True → True | 39 | 0 | unresolved=1 | unresolved=26 | {"after": [], "before": []} | changed_or_missing_spans=2, uniquely_unchanged_spans=9 | {"fresh": false, "status": "changed"} |
| pluggy-call-extra | True → True | 126 | 0 | unresolved=1 | unresolved=15 | {"after": [], "before": []} | changed_or_missing_spans=1, uniquely_unchanged_spans=3 | {"fresh": false, "status": "changed"} |

## 12. Historical evidence is not rewritten

The earlier complete-only primary experiment met its speed target in 0/4 development repositories and reused 0/480 natural anchor transitions per repetition. Its failed target remains a negative result. The later same-data any-status ablation reused 364/480 transitions, but was designed after that outcome and is exploratory, not a held-out confirmation. Neither table is pooled with the new repository holdout. [Historical primary](RESEARCH_REPORT.md) · [Exploratory ablation](ABLATION_REPORT.md).

The first task pilot was invalidated because forced postponed annotations changed upstream test execution semantics and its read isolation was incomplete. Its raw records remain preserved, but none of its coverage metrics is used here. The corrected run preserves upstream compiler flags, restricts reads, rejects unverified bytecode/native imports, validates every case/repeat/line identity, retains partial failures and checks traced/untraced outcomes. This is a disclosed same-sample correction, not an independent replication or new task holdout. [Invalid-pilot status](../../benchmarks/task_evidence/results/initial/STATUS.md) · [Execution amendment](../../benchmarks/task_evidence/EXECUTION_AMENDMENT.md).

## 13. Interpretation, limitations and next evidence

The narrow combined performance target is met on this fixed sample. Per-repository results, source-changing strata, capture cost and observed RSS increases remain part of the result. 15/28 source-identical transitions favor simple reuse, and short release-centered histories are not representative edit streams. Four convenience repositories, fixed top-level anchors and a bounded resolver do not establish population effects. Five repeated trajectories describe timing variability, not five independent datasets; no confidence/significance claim is made.

Task witnesses omit unexecuted alternatives and native/generated behavior outside their stated scope. High recall can reflect broad class/module spans and cannot demonstrate that a context is minimal or sufficient. The line-matched BM25 budget is not a token or retrieval-latency match. Known development projects, release-pair selection and reviewed fixture substitutes limit external validity. Memory tests include short-lived overlap of old/new state and process overhead; eight revisions cannot prove unbounded-run stability.

Further research needs independent human task-context review, additional repository/time holdouts, calibrated end-to-end coding tasks against current retrieval/invalidation baselines, external reproduction and a separate novelty argument. This report establishes an inspectable engineering experiment, not a mature paper, SOTA result or deployed system.

## 14. Related work and official method sources

Dependency-hash traces and rebuild decisions are established in [Mokhov, Mitchell and Peyton Jones, Build Systems à la Carte (2018)](https://www.microsoft.com/en-us/research/publication/build-systems-la-carte/). [Tup ghost nodes](https://gittup.org/tup/manual.html) provide prior treatment of failed lookups; [Bazel Skyframe](https://bazel.build/reference/skyframe) explains registered dependencies and incremental evaluation. Our claim is their scoped engineering application and evaluation, not new memoization or negative-dependency theory.

[ContextBench v3](https://arxiv.org/abs/2602.05892v3) evaluates task-relevant coding contexts, whereas this report’s execution witnesses are not human relevance labels. [When Retrieval Hurts v1](https://arxiv.org/abs/2605.14478v1) studies stale repository context; stale-context harm is not a newly established phenomenon here. Neither paper’s model experiments is reproduced. These distinctions are our interpretation, not the authors’ assessment of this artifact. [Detailed positioning](RELATED_WORK.md). Official Python 3.12 tracing/tracemalloc and pytest fixture references are cited at the respective measurement boundaries above.

## 15. Provenance and offline regeneration

Holdout environment: Python 3.12.2; Darwin; Apple M1 Pro; arm64; 16.0 GiB RAM; one benchmark thread. Task environment: Python 3.12.2; Darwin; arm64. Holdout source_dirty=True; task measured_inputs_dirty=False. Runtime/supporting file hashes and actual order remain in raw provenance. The whole-worktree dirty flag and measured implementation digests describe different scopes. Pinned input identity and saved result consistency are checked again before this report is generated. Offline validation checks record consistency and arithmetic, not a new source execution or independent replication.

| Record | Identity | Commit |
|---|---|---|
| Holdout run | holdout-20261004T211414735263Z | a0070ea71cea3c8944c004559602616114011b76 |
| Task run | bcebd88f-0906-4040-b3d3-e228f3f1a1df | a0070ea71cea3c8944c004559602616114011b76 |
| Holdout protocol SHA256 | a7eeb619d4e76c763bacc809f753135c3240544d82fc224e45b11a7d1121992d |  |
| Holdout manifest SHA256 | 126df30f4d69aa667b951ba1856dcb9b2ae03fba8d23e4a358e7127e936b7bc5 |  |
| Task manifest SHA256 | 4653503c6b5208f1c07c2535a97c76aaadfc08dc102f3beb5fc9b8463bfba2a4 |  |
| Task amendment SHA256 | 2d39a533f59a0ddf20448569ed24ba158877f5184659dbf87f1dddf2ca31c11c |  |

[Holdout raw / 留出原始数据](../../benchmarks/incremental_holdout/results/primary-20261004.json) · [Task raw / 任务原始数据](../../benchmarks/task_evidence/results/primary-20261004/runs.json) · [Task cases / 逐案例](../../benchmarks/task_evidence/results/primary-20261004/cases.json) · [Task provenance / 任务出处](../../benchmarks/task_evidence/results/primary-20261004/provenance.json).

```bash
python scripts/render_maturation_report.py
python scripts/render_maturation_report.py --check
```

These commands perform offline validation and rendering only. Raw measurement commands remain in the input artifacts; new executions must use new result paths. Exact third-party license bytes and source pins are included in the tracked attribution records.

## 16. Reproduce in a new environment and result path

Run from the repository root in a fresh Python 3.12 environment. Development dependencies are optional for measurement and needed for the test suite. The public archive fetchers require curl with normal TLS verification; they use frozen URLs, SHA-256 digests and byte counts without authentication. Existing verified caches are reusable; changed archives are rejected. Neither fetching nor extraction executes upstream code.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
# Optional integrity-test dependencies / 可选的完整性测试依赖
python -m pip install -e ".[dev]"
```

The all-suite holdout includes timing plus both memory modalities. Memory measurement supports macOS/Linux; duration depends on hardware and system load. The prepare step populates the external cache from the existing frozen manifest. Use a new output filename, never the preserved primary artifact:

```bash
python scripts/prepare_incremental_holdout.py --cache-dir ../holdout-inputs
python scripts/run_incremental_holdout.py run --suite all \
  --cache-dir ../holdout-inputs --output work/NEW_HOLDOUT.json
python scripts/run_incremental_holdout.py analyze --output work/NEW_HOLDOUT.json
```

The adapted upstream assertion harness requires macOS sandbox-exec and fails closed when its isolation preflight cannot be enforced. Fetch the six pinned archives, verify/extract them, and execute into a new result directory:

```bash
python scripts/fetch_task_inputs.py --cache ../task-inputs
python scripts/run_task_evidence.py --sources ../task-inputs --extract
python scripts/run_task_evidence.py --sources ../task-inputs --output work/NEW_TASK
```

Both experiment runners retain failed or interrupted attempts; a failure cannot be published as a completed summary. These are reproduction instructions, not evidence that a second machine has reproduced the reported measurements.

[中文](../zh/MATURATION_REPORT.md)
