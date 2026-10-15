# Finite binding observation report

All selected tasks: 8; primary scoring repeat: 0.

Invalid tasks and zero denominators contribute zero coverage; zero accepts have undefined accuracy. Repeats check stability and do not increase the task count.

| Method | Execution/prediction qualified | Score-qualified tasks | Tasks accepting | Raw accepted site×source-role observations | Raw mismatching site×source-role observations | All-task macro coverage | Conditional site accuracy | Primary gate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| currentfresh | 6/8 | 3/8 | 2 | 28 | 0 | 0.208333 | 1 | not passed |
| whole_guard | 6/8 | 3/8 | 2 | 28 | 0 | 0.208333 | 1 | not passed |
| selective | 6/8 | 3/8 | 2 | 28 | 0 | 0.208333 | 1 | not passed |
| always_abstain | 6/8 | 3/8 | 0 | 0 | 0 | 0 | undefined / 未定义 | N/A |

| Task | Method | Pair/prediction qualified | Raw accepted sites | Raw mismatching sites | All-task coverage contribution |
|---|---|---|---:|---:|---:|
| eval-01 | currentfresh | true | 4 | 0 | 0.666667 |
| eval-01 | whole_guard | true | 4 | 0 | 0.666667 |
| eval-01 | selective | true | 4 | 0 | 0.666667 |
| eval-01 | always_abstain | true | 0 | 0 | 0 |
| eval-02 | currentfresh | true | 0 | 0 | 0 |
| eval-02 | whole_guard | true | 0 | 0 | 0 |
| eval-02 | selective | true | 0 | 0 | 0 |
| eval-02 | always_abstain | true | 0 | 0 | 0 |
| eval-03 | currentfresh | true | 0 | 0 | 0 |
| eval-03 | whole_guard | true | 0 | 0 | 0 |
| eval-03 | selective | true | 0 | 0 | 0 |
| eval-03 | always_abstain | true | 0 | 0 | 0 |
| eval-04 | currentfresh | false | 0 | 0 | 0 |
| eval-04 | whole_guard | false | 0 | 0 | 0 |
| eval-04 | selective | false | 0 | 0 | 0 |
| eval-04 | always_abstain | false | 0 | 0 | 0 |
| eval-05 | currentfresh | true | 0 | 0 | 0 |
| eval-05 | whole_guard | true | 0 | 0 | 0 |
| eval-05 | selective | true | 0 | 0 | 0 |
| eval-05 | always_abstain | true | 0 | 0 | 0 |
| eval-06 | currentfresh | true | 24 | 0 | 1 |
| eval-06 | whole_guard | true | 24 | 0 | 1 |
| eval-06 | selective | true | 24 | 0 | 1 |
| eval-06 | always_abstain | true | 0 | 0 | 0 |
| eval-07 | currentfresh | false | 0 | 0 | 0 |
| eval-07 | whole_guard | false | 0 | 0 | 0 |
| eval-07 | selective | false | 0 | 0 | 0 |
| eval-07 | always_abstain | false | 0 | 0 | 0 |
| eval-08 | currentfresh | true | 0 | 0 | 0 |
| eval-08 | whole_guard | true | 0 | 0 | 0 |
| eval-08 | selective | true | 0 | 0 | 0 |
| eval-08 | always_abstain | true | 0 | 0 | 0 |

Descriptive timing (milliseconds)

Each method cell is the median of all retained repeats. A missing repeat measurement makes the median unavailable; every raw repeat remains in SUMMARY.json.

| Task | Method | Median initialization | Median capture | Median replay | Median method total |
|---|---|---:|---:|---:|---:|
| eval-01 | currentfresh | 1.15479 | 110.669 | 69.1212 | 181.133 |
| eval-01 | whole_guard | 1.27325 | 109.992 | 69.8509 | 181.722 |
| eval-01 | selective | 1.20046 | 111.827 | 21.2644 | 134.749 |
| eval-02 | currentfresh | 1.11904 | 108.436 | 64.1324 | 173.199 |
| eval-02 | whole_guard | 1.1565 | 110.243 | 64.6531 | 176.174 |
| eval-02 | selective | 1.07375 | 108.627 | 17.9382 | 128.565 |
| eval-03 | currentfresh | 0.830625 | 61.8389 | 45.0245 | 107.61 |
| eval-03 | whole_guard | 0.838667 | 63.5668 | 45.3842 | 109.819 |
| eval-03 | selective | 0.721875 | 60.513 | 32.1192 | 93.4486 |
| eval-04 | currentfresh | 0.817625 | 60.1449 | 37.4692 | 97.8681 |
| eval-04 | whole_guard | 0.7685 | 60.438 | 41.9033 | 100.195 |
| eval-04 | selective | 0.7505 | 59.9884 | 23.8189 | 91.1873 |
| eval-05 | currentfresh | 0.246209 | 44.498 | 36.6203 | 81.8768 |
| eval-05 | whole_guard | 0.31225 | 44.1805 | 36.6593 | 80.5345 |
| eval-05 | selective | 0.331958 | 43.2903 | 9.12104 | 52.5249 |
| eval-06 | currentfresh | 0.162833 | 24.0947 | 19.7381 | 44.1587 |
| eval-06 | whole_guard | 0.185083 | 25.1535 | 19.3984 | 43.7388 |
| eval-06 | selective | 0.190542 | 25.4246 | 5.61033 | 31.2815 |
| eval-07 | currentfresh | 2.47417 | 235.278 | 107.569 | 345.32 |
| eval-07 | whole_guard | 2.54621 | 234.723 | 106.346 | 342.989 |
| eval-07 | selective | 2.72429 | 246.305 | 42.0595 | 291.126 |
| eval-08 | currentfresh | 2.41942 | 238.307 | 113.175 | 351.719 |
| eval-08 | whole_guard | 2.5175 | 246.433 | 104.336 | 351.903 |
| eval-08 | selective | 2.391 | 238.671 | 21.7355 | 262.758 |

| Task | Source validation/load | Shared preparation | All methods including preparation | Final validation | Child end-to-end | Serial controller wall |
|---|---:|---:|---:|---:|---:|---:|
| eval-01 | 37.6641 | 194.529 | 1686.94 | 23.9679 | 1748.57 | 1964.46 |
| eval-02 | 38.6371 | 196.088 | 1635.04 | 23.943 | 1697.62 | 1858.77 |
| eval-03 | 29.6001 | 98.4128 | 1035.16 | 20.5251 | 1085.28 | 1205.85 |
| eval-04 | 34.181 | 99.6241 | 1095.56 | 21.1088 | 1150.85 | 1323.05 |
| eval-05 | 41.1145 | 9.47679 | 658.63 | 23.3203 | 723.065 | 866.463 |
| eval-06 | 22.8518 | 6.90783 | 765.816 | 13.0514 | 801.72 | 1053.37 |
| eval-07 | 90.5216 | 179.025 | 3170.2 | 57.8513 | 3318.57 | 3598.11 |
| eval-08 | 97.7698 | 178.252 | 3146.12 | 54.6747 | 3298.56 | 3538.19 |

Method total includes that method's initialization, capture, replay and projection; it excludes shared preparation, full source loading and process costs. Column medians need not sum to the median total. Shared preparation runs once and must not be added once per method. All-method timing includes preparation, every repeat of the three methods, and the always-abstain diagnostic. Child end-to-end includes source/implementation validation, loading, all methods and final validation; controller wall additionally includes child startup, imports and output serialization through closure, excluding earlier request preparation and later sealing, public export or this report. Not reported / not run means timing is unavailable, not a claim about whether execution occurred. These are descriptive costs, without speed ratios, significance tests or quality gains.


Numbers are recomputed from INDEX-pinned inputs. Execution/prediction qualification does not imply scoreable primitive observations. Raw counts may include invalid-condition diagnostics; conditional accuracy pools only score-qualified tasks. Site×source-role observations are not independent tests. Retained statuses, aggregate graph completeness/frontier counts, repetitions and timings are in SUMMARY.json; per-anchor detail rows are not public.

Observations are pre-op bindings, not proof of consumed operands; disagreement with a derived hypothesis is not a whole-graph bug. Test changes describe original developer fixes only. Equal outputs are ties and timing is descriptive. This report does not establish full semantics, generated-repair benefit, novelty or research maturity.

INDEX SHA256: `b0c354cf756bc700f14a8cfdfa0695b2d671305bd0715574b426e769f9dc8328`

Report analysis source SHA256: `16474ace765e4554873fad57a870eb01cd157fe27be7122e49aba271dfce3ef9`
