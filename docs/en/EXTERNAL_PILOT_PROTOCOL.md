# Issue-only external edit-localization pilot

The frozen study selects39 real tasks from six previously unused Python repositories in AmazonScience/SWE-PolyBench_500. Selection uses repository/language/task ID metadata only. Within each repository, it takes the first10 tasks ordered by SHA256(`external-context-20261013:` + instance ID). The resulting1/10/10/10/2/6 distribution is below the proposed60-task scope, so it is explicitly a pilot.

[Protocol](../../benchmarks/external_context/protocol.json) was committed at `aefdf06fc34f7c74434c67640e80128df350260a` before predictions or label scoring. [Pre-prediction amendments](../../benchmarks/external_context/amendments.json) explain operational download retries and macOS RSS monitoring. The query is the complete problem statement. Hints, reference patches, dataset test_patch, modified-node metadata and manual anchors never enter the retrieval worker.

## Inputs and scope

The dataset-specific card declares MIT; the dataset revision is `546075b4b05d17ba914e72b8f4c6d5b1ea150c1d`. Each task uses its exact base commit and checked root license. Original issues, patches and upstream source snippets remain in a local cache outside Git. Public results contain task IDs, source coordinates, hashes and scalar measurements. Per-file third-party licenses are not exhaustively audited because source is read locally as data and is not redistributed.

This is Python-only localization of removed base-version lines and edited existing files in textual patch hunks. A patch shows one actual edit; it does not identify all necessary context, semantic sufficiency or a successful repair by this project. Pure insertions have no removed-line target and receive `null` line metrics. New files cannot have base-version source. Targets absent from the usable source corpus remain in the denominator. An unsuccessful prediction is conservatively scored as empty source where a target exists; its corpus-availability diagnostic remains unknown.

## Methods and fair budget

| Method | Candidate source |
|---|---|
| bm25_windows | Fixed, nonoverlapping80-line windows |
| bm25_declarations | Existing innermost-declaration80-line chunks |
| anchors_only | Three highest-ranked distinct declaration owners |
| graph_expand | The same anchors plus resolved dependency graph source; depth2, node cap128 |
| window_expand | The same anchors plus80 lines before/after each |
| file_expand | The same anchors plus BM25-ranked windows of their files |

All methods use the same deterministic JSON packer at8000/16000/32000 UTF-8 bytes. The complete issue, delivered metadata and exact source all consume budget. Overlapping physical source lines are sent once. Large declarations are split before packing; a predeclared piece that cannot fit is skipped whole. Out-of-payload diagnostics are audit records and must not be supplied to a model without charging their bytes.

The primary endpoint is repository-macro removed-line F1 at16000 bytes, comparing graph expansion separately with both lexical baselines. Recall, precision, edited-file metrics, every task's actual byte consumption and unresolved frontiers are secondary. The task/repository, not18 method-budget rows or timing samples, is the observation. No p-value or significance claim is made.

## Execution and verification

The single worker reads a checked source archive without extraction, imports or execution. Frozen caps are5000 Python files,32MiB total Python bytes,1MiB per Python file and300 seconds/task. Linux uses a4GiB address-space bound; macOS samples RSS against4GiB every250ms, allows possible transient overshoot and fails explicitly if monitoring fails. These modes are not equivalent hardware bounds.

Prediction requires a clean source commit. Exact rendered blocks are checked against the source, byte count and physical-line uniqueness. Each task's prediction is written once; the complete prediction bundle is sealed with hashes before the separate scoring command reads patches. Score validation requires every frozen task and exactly six methods times three budgets, with consistent repository/base identities. Every failure and no-target case remains visible.

```bash
python -m pip install -e '.[dev]'
python -m benchmarks.external_context.fetch --cache work/external-inputs
PYTHONPATH=src python -m benchmarks.external_context.runner predict \
  --dataset work/external-inputs/test.csv --sources work/external-inputs/sources.json \
  --output work/external-runs/my-new-run
PYTHONPATH=src python -m benchmarks.external_context.runner score \
  --dataset work/external-inputs/test.csv --run work/external-runs/my-new-run \
  --output work/external-runs/my-new-run/scores.json
PYTHONPATH=src python -m benchmarks.external_context.analyze \
  --scores work/external-runs/my-new-run/scores.json \
  --output work/external-runs/my-new-run/summary.json
python -m pytest -q tests/test_external_context_*.py
```

Run from a clean Git checkout. Every output path must be new. Inputs require about1.24GB compressed source downloads plus local working space; no model/API/GPU is required. Existing matching caches are reused; mismatched cache bytes are rejected.

The predeclared planning gate requires no integrity failure, positive graph F1 effects on at least4of6 repositories, macro F1 gain at least0.03 against both lexical baselines, and recall degradation at most0.02. Passing would only motivate a larger untouched confirmatory study. It would not establish agent benefit, novelty or mature research. Failure narrows the claim; tuning on these39 tasks cannot turn them into a new holdout.

[中文](../zh/EXTERNAL_PILOT_PROTOCOL.md)
