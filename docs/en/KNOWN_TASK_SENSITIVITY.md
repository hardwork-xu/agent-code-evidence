# Post-hoc execution-qualified sensitivity

This is a descriptive reanalysis of the already observed pilot. No new SUT, retrieval, model, holdout or generated repair was run. The original 39-task primary results and failed advancement gates remain unchanged.

Run ID: `known39-secondary-final-20261015`. UTC: `2026-10-15T05:00:55.619687+00:00`.

The secondary protocol was frozen before this subset calculation, after the original scores and execution outcomes were known. It is not a pre-data preregistration. The input seal binds author-written scientific inputs; it is not a signature, external approval or independent authentication.

Eligibility uses the latest approved started condition, including closed failures and partial attempts; it never selects the best environment. There are 51 complete conditions and one closed partial attempt. All 87 F2P / 5842 P2P labels remain in the execution ledger; labels and retries are not independent samples.

| Repository | Original tasks | Finite-qualified | Qualified line-targetable | Qualified undefined | Original prediction failures |
|---|---:|---:|---:|---:|---:|
| `Significant-Gravitas/AutoGPT` | 1 | 1 | 1 | 0 | 0 |
| `huggingface/transformers` | 10 | 5 | 4 | 1 | 5 |
| `keras-team/keras` | 10 | 9 | 8 | 1 | 0 |
| `langchain-ai/langchain` | 10 | 10 | 8 | 2 | 0 |
| `tensorflow/models` | 2 | 1 | 1 | 0 | 0 |
| `yt-dlp/yt-dlp` | 6 | 4 | 2 | 2 | 0 |

The subset contains 30 tasks: 24 line-targetable and six undefined, versus 32/7 in the original 39. The last column refers to all original tasks, not subset failures. Original source-cap failures retain conservative zero scores; no predictions were regenerated or rescored. Undefined labels stay null.

## 16,000-byte focus

Differences are graph expansion minus baseline in percentage points (pp), not relative percent.

| Population | Baseline | F1 difference (pp) | Recall difference (pp) | F1 repo wins/ties/losses/undefined |
|---|---|---:|---:|---|
| all39 | `bm25_windows` | +0.064799 | -9.336383 | 2/1/3/0 |
| all39 | `bm25_declarations` | -0.259808 | -9.722716 | 2/1/3/0 |
| qualified30 | `bm25_windows` | +0.191104 | -13.650599 | 2/2/2/0 |
| qualified30 | `bm25_declarations` | +0.045618 | -14.300790 | 2/2/2/0 |

F1 ordering against declaration BM25 flips on the selected subset; this positive observation is retained. Recall remains lower than both baselines, by 13.650599 and 14.300790 pp respectively. The selection changes within-repository task composition. All six repositories still contribute, so the common-contributing-repository diagnostic equals the original all39 result.

The joint strict-negative F1-and-recall flag is false in both populations: the original graph F1 was already above window BM25. This flag is not evidence of overall superiority. No p-values or confidence intervals treating nodes/retries as independent samples are reported.

## All methods and budgets

Task means are computed within each repository, then defined repository means receive equal weight. The exact ratios, every per-repository comparison, membership and exclusions are retained in result.json.

| Method | Byte budget | All39 F1 | All39 recall | Qualified30 F1 | Qualified30 recall |
|---|---:|---:|---:|---:|---:|
| `bm25_windows` | 8000 | 0.804657% | 10.482226% | 0.330277% | 13.715278% |
| `bm25_windows` | 16000 | 0.816360% | 18.234442% | 0.456704% | 22.749864% |
| `bm25_windows` | 32000 | 0.718537% | 20.878179% | 0.299272% | 24.969363% |
| `bm25_declarations` | 8000 | 1.665541% | 13.931732% | 1.117114% | 18.062364% |
| `bm25_declarations` | 16000 | 1.140966% | 18.620775% | 0.602190% | 23.400054% |
| `bm25_declarations` | 32000 | 0.725397% | 19.398329% | 0.294895% | 23.522603% |
| `anchors_only` | 8000 | 1.053091% | 6.081369% | 0.701856% | 5.735975% |
| `anchors_only` | 16000 | 1.035492% | 8.756266% | 0.816333% | 8.976716% |
| `anchors_only` | 32000 | 1.123448% | 10.693298% | 0.689637% | 10.539216% |
| `graph_expand` | 8000 | 0.995380% | 6.203918% | 0.637748% | 5.858524% |
| `graph_expand` | 16000 | 0.881158% | 8.898059% | 0.647808% | 9.099265% |
| `graph_expand` | 32000 | 0.926545% | 10.819485% | 0.484674% | 10.661765% |
| `window_expand` | 8000 | 0.977264% | 6.602203% | 0.621588% | 6.256808% |
| `window_expand` | 16000 | 0.810069% | 9.350917% | 0.498467% | 9.497549% |
| `window_expand` | 32000 | 0.828068% | 12.140399% | 0.313180% | 11.928105% |
| `file_expand` | 8000 | 0.956427% | 6.602203% | 0.595803% | 6.256808% |
| `file_expand` | 16000 | 0.843673% | 12.128694% | 0.532071% | 12.275327% |
| `file_expand` | 32000 | 0.800058% | 15.285823% | 0.282640% | 15.073529% |

## Reproduce and check

From a checkout of this branch, Python 3.11+ is sufficient; no third-party package, dataset download, model or API key is needed for scalar reanalysis. The saved result includes the original measurement timestamp, platform and analysis duration. A replay has different provenance; compare scientific fields, not wall-clock bytes or execution speed.

```sh
python -m benchmarks.known_task_execution.secondary_report --check
WORK="$(mktemp -d)"
DATA=benchmarks/known_task_execution/secondary/known39-20261015
python -m benchmarks.known_task_execution.analyze_sensitivity \
  --protocol "$DATA/protocol.json" \
  --protocol-sha256 6d978f180ad4386416ac3cb04984e66484cd2691fa35339fa61eecd8c9c2cc56 \
  --pilot-repository-root . --eligibility-ledger "$DATA/eligibility.json" \
  --eligibility-sha256 a7e56df07d366afa8959a1fa2dead1ff3d5565ba26fc361b0f162259dae400b4 \
  --approval "$DATA/analysis-seal.json" \
  --approval-sha256 c86bd4a7b75e23543dfd9bbe353e26532bf08a7c1f101ec9fde082a2336ded7e \
  --run-id known39-secondary-replay --output "$WORK/result.json"
```

The report checker verifies the published SHA pins, reloads the exact verified original inputs, and recomputes the scalar result using the frozen analysis program. This detects inconsistency with this artifact; it is not independent replication of private upstream executions.

| File | SHA256 |
|---|---|
| `result.json` | `f9566e32e27decd3a0970a04ffe0fad04be7369e0b33cdf2e48468bf2eadbf3c` |
| `protocol.json` | `6d978f180ad4386416ac3cb04984e66484cd2691fa35339fa61eecd8c9c2cc56` |
| `eligibility.json` | `a7e56df07d366afa8959a1fa2dead1ff3d5565ba26fc361b0f162259dae400b4` |
| `analysis-seal.json` | `c86bd4a7b75e23543dfd9bbe353e26532bf08a7c1f101ec9fde082a2336ded7e` |
| `analyze_sensitivity.py` | `b660d3b4aa34d9cb30905d1458a05a195ca3503970c41a6db186f555d57f25e9` |

## Research boundary and next gates

Local platform, available dependencies, original test strength and execution feasibility select this subset. Known-data filtering is neither causal identification nor a new holdout. Reference edit overlap is not necessary context, semantic correctness or coding-agent repair benefit. The current evidence supports an auditable measurement artifact and a negative/mixed pilot, not a mature positive research claim.

Advancement requires a separately frozen unseen task set, fair strong retrieval and whole-corpus invalidation/cost baselines, an executable semantic endpoint, and independent replay under declared budgets. Those are uncompleted gates, not promised outcomes. No release or paper acceptance is implied.

[Execution protocol / 执行协议](KNOWN_TASK_EXECUTION.md) · [Original pilot / 原pilot](EXTERNAL_PILOT_RESULTS.md)
