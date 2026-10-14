# Catalog dependency footprints: fixed natural trajectories

Run `catalog-20261014T121419Z-84b62e96`, measured source `affa59024f70cde86d2549b690204aa73ddccc7d`. The primary target was met in 0/4 repositories; the overall performance gate **failed**. This supports bounded resolver replay and engineering cost only, not mature research, Python semantic proof or agent benefit.

4 repositories, 17 snapshots and 24 fixed anchors each; 21/64 batches of eight commits changed the production catalog. One warmup and five measurements; 1816 retained primary/secondary steps, of which 1360 are measured primary steps, plus 48 fresh RSS subprocesses. The unmodified resolver was checked on 107 unique snapshots/2568 graphs. Repeats and anchors are not independent samples.

| Repository | C replay ms | D replay ms | D reduction vs C | D reduction vs A | D/C RSS | >=20% |
|---|---:|---:|---:|---:|---:|---|
| rq/rq | 12404.731 | 12348.172 | 0.46% | 0.46% | 1.062 | no |
| modelcontextprotocol/python-sdk | 12188.444 | 11566.814 | 5.10% | 6.91% | 0.944 | no |
| scrapy/scrapy | 3895.112 | 3869.365 | 0.66% | 1.64% | 0.956 | no |
| pypa/hatch | 1695.611 | 1615.071 | 4.75% | 7.78% | 0.984 | no |

| Repository | C capture ms | D capture ms | C total ms | D total ms | C reused/384 | D reused/384 |
|---|---:|---:|---:|---:|---:|---:|
| rq/rq | 562.292 | 563.647 | 12963.413 | 12911.819 | 230 | 251 |
| modelcontextprotocol/python-sdk | 991.342 | 994.358 | 13180.030 | 12561.172 | 268 | 313 |
| scrapy/scrapy | 566.370 | 566.112 | 4474.118 | 4439.026 | 274 | 291 |
| pypa/hatch | 262.064 | 269.145 | 1943.960 | 1842.963 | 320 | 332 |

384 observations per repository = 24 anchors x 16 replays; reuse counts use the first measured trajectory and every repeat remains. Capture and total are independently computed medians of five trials, so medians need not add. Small timing differences do not establish a robust speedup.

Adverse observations: comparing the same repetition index within each repository, D was slower than C in 3/20 replay trajectories and 13/20 captures. These counts describe repeated measurements, not independent error rates or causal estimates.

Coverage boundary: only 15/1536 D graph outputs in the first measured replay trajectories had no frontier; the rest retain missing/unresolved/truncated states. Replay equality cannot be promoted to complete semantic freshness.

Frontier state counts (D first measured trajectory including capture; descriptive, not semantic error rate):`{"missing": 1, "truncated": 3633, "unresolved": 29332}`

Every unknown/truncated frontier remains; the later missing RQ anchor is not replaced. Initial capture, capture+replay totals and every RSS sample remain in raw summaries. No upstream source, model or Docker was executed; CI is verified separately. Convenience sources have unequal window durations and one macOS measurement host. Fine-grained caching does not repair the negative39-task localization pilot.

[Protocol](CATALOG_PROTOCOL.md) · [Conditional guarantees](CATALOG_SOUNDNESS.md) · [Raw results](../../benchmarks/catalog_reuse/results/catalog-20261014T121419Z-84b62e96/run.json) · [Frozen resolver check](../../benchmarks/catalog_reuse/results/catalog-20261014T121419Z-84b62e96/legacy-oracle.json)
