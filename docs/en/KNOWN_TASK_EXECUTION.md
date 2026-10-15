# Fixed known-task execution qualification

The 39 tasks used in the external-context pilot are already observed development
inputs. This stage checks whether their original regression labels can be
reproduced by actual upstream programs. It does not evaluate generated repairs,
prove necessary context, establish a new holdout, or turn the pilot into mature
research.

The source dataset is `AmazonScience/SWE-PolyBench_500`, revision
`546075b4b05d17ba914e72b8f4c6d5b1ea150c1d`. The original CSV SHA256 is
`20961b616b404875adead16dd456adc4cf583035436fc0d7e9c3f2adf8322e0c`.
All 39 tasks remain in the denominator: 87 F2P and 5,842 P2P metadata labels.
Labels are test identifiers, not independent assertions or tasks. A selected
test can contain several assertions or return before its intended assertion.

Each pair uses the exact dataset base plus its test patch. The gold role also
applies the dataset code patch. The same tests and environment are used in both
roles. An independent `git apply --check`/`git apply` audit agreed with the
separate byte parser for all 39 transformations. Two yt-dlp dataset code patches
omit additional changes present at their official PR heads; the adapter retains
the dataset-derived code instead of silently replacing it with the entire head.

`benchmarks/known_task_execution/worker.py` records actual framework collection,
selects only the frozen metadata subset, preserves phase reports, verifies the
complete prepared source tree before and after execution, and checks imported
production files. Reviewed socket paths are denied or limited to loopback. This
is an environment adapter, not an OS security sandbox or the official container
harness. Raw stack traces and local paths stay outside Git.

`contract.py` requires F2P behavioral call failure followed by actual call pass,
and actual call passes for every P2P label in both roles. Collection failures,
missing outcomes, skips, XFAIL, XPASS, resource failures and unfinished processes
cannot establish qualification. Explicit source-bound aliases support the fixed
pathless labels; normal labels and parameter suffixes are never guessed. Aliases
must match original method names, source bytes and exact actual collection.

This is deliberately stricter than the fixed official harness's
absence-of-P2P-failure criterion. It is an unofficial finite regression
qualification, not an official benchmark score. Official harness source
`amazon-science/SWE-PolyBench@9c836c5d7f3cb991934132b77d29e6941d912a07`
was inspected without executing it or incorporating its source in the adapter. Its root MIT license and Python
file CC-BY-NC-4.0 headers disagree; the independently written adapter does not
redistribute that source. Dataset commands, Dockerfiles and installation scripts
are reference material and are not executed as instructions.

The [generated result table](KNOWN_TASK_EXECUTION_RESULTS.md) counts every
original task and every retained complete pair condition, including unsuccessful
collection and native crashes. It distinguishes a completed pair record from
completed assertion validation. Latest means the most recently frozen protocol,
not the highest score. Earlier failed and incomplete conditions remain retained.
Python versions, dependency fingerprints, protocol hashes and per-phase results
are separate from the older localization pilot. Passing adapter unit tests does
not establish upstream task success or research maturity.

Adapter checks:

```sh
python -m pytest -q tests/test_known_task_execution_contract.py tests/test_known_task_execution_worker.py
python -m benchmarks.known_task_execution.contract --help
```

Sources: [fixed dataset](https://huggingface.co/datasets/AmazonScience/SWE-PolyBench_500/tree/546075b4b05d17ba914e72b8f4c6d5b1ea150c1d),
[fixed official harness](https://github.com/amazon-science/SWE-PolyBench/tree/9c836c5d7f3cb991934132b77d29e6941d912a07).


Source-adjacent runtime logs require a fixed, source-hash-bound allowlist and a
1 MiB combined byte limit. The AutoGPT summary test also invokes the original
cycle logger indirectly. Its source-supported `OVERWRITE_DEBUG=1` option fixes
the output directory; only the four named summary artifacts for the two batches
are additionally permitted, with caller, logger and test source proofs. Every
other new file, source mutation, symlink, hard link or byte-limit violation
invalidates execution. Artifact contents remain private. The earlier incomplete
condition that exposed the missing log paths is retained, not reinterpreted as
qualified. Passing an owned adapter fixture does not verify the upstream task.


Source preparation is now runnable independently of the private task directory:

```sh
WORK="$(mktemp -d)"
CACHE="$WORK/cache"
python -m benchmarks.external_context.fetch --cache "$CACHE"
python -m benchmarks.known_task_execution.prepare --csv "$CACHE/test.csv" --cache "$CACHE" --task yt-dlp__yt-dlp-1649 --output "$WORK/yt-1649"
```

Set `CACHE` and `WORK` to new private directories outside Git. The first command
fetches the fixed public inputs; neither command executes dataset instructions
or upstream programs. The second creates immutable `base_tests` and
`fixed_tests` plus a complete file-hash manifest. Source-only reconstruction for
all39 original tasks matched all78 previously prepared role indexes,137283
files and2461434350 bytes. A real CLI preparation also matched the yt-dlp1649
inputs. This verifies source reconstruction, not a second regression execution.
Regular unmodified assets over5MiB and nonregular entries are explicitly omitted
in the31-task general scope; TensorFlow uses the declared subsystem Python/proto
scope. Every patched file is required. An absent fixture still fails execution.

## Reading the actual observations

The source, runtime and labels are fixed within each condition; changing a
compatibility dependency creates another explicitly frozen condition. There is
no pooling of a favorable subset into the39-task denominator. Conditions use
native Apple M1 Pro CPU or explicitly recorded x86_64 Rosetta,16 GiB macOS;
Docker and CUDA were unavailable. Upstream tests and CPU dependency gates run
serially. Warm/cold loading and different environments make elapsed times
diagnostic, not fair baseline/candidate performance measurements.

Important interpretation limits remain even for qualified labels:

- LangChain5450 base fails constructor validation for `encode_kwargs`, before
  the normalization assertion. Gold passes the original five selected tests
  with actual pretrained models. This is API behavior evidence, not a measured
  normalization-quality or embedding-quality improvement. Its post-launch
  correction narrows the frozen phrase about an original lock to a reviewed
  minimum lock with selected original direct pins; both records are retained.
- AutoGPT4652 uses the original mocked summary completion. It executes source
  message-history code and an actual tokenizer resource, not a commercial model.
- DINOv2 tests include cross-framework skips and source branches that can return
  early when an offline resource is absent. Raw passes cannot establish model
  inference on those branches. No branch trace is claimed.
- The legacy Keras3983 condition explicitly substitutes Theano with the Python
  linker and `FAST_COMPILE` for the original TensorFlow backend. It reproduces
  the target fail-to-pass but retains
  five P2P failures and one original skip, so the task is unqualified.
- TensorFlow1.15 x86_64 under Rosetta aborts at its AVX guard on this host. This is a retained
  environment failure with no observed target assertion, not a behavioral F2P.
- Two yt-dlp target tests already pass at base in the declared native condition.
  Their gold passes do not reproduce the supplied F2P label.
- OWL-ViT20136's newer condition resolves observed NumPy/Torch bridge failures;
  bootstrap pip also differs. It is a compatibility condition, not a perfectly
  isolated single-variable causal experiment. All prior failures remain.

## Rechecking and rerunning are different operations

The latest nine unqualified tasks are retained explicitly:

| Tasks | Retained limit or negative observation |
|---|---|
| yt-dlp1649,8917 | Target already passes at base; supplied F2P not reproduced. |
| Keras3983 | Target reproduces, but five P2P failures and one original skip remain under the explicit Theano alternative. |
| Transformers27561 | Two F2P reproduce; five original cross-framework skips prevent full P2P qualification. Some pipeline raw passes can return early without inference. |
| Transformers27717 | No F2P reproduced; protobuf/resource errors, an IndexError and a TF skip remain. Empty process-denial records do not prove process refusal. |
| Transformers7075 | Eleven base TypeErrors and eleven gold sampler pickling AttributeErrors; no numerical memory-performance result. Separate process-denial records are not established as the pickling cause. |
| Transformers13989 | Both actual source roles abort with empty captured logs; no test calls. AVX attribution is inferred from a separate failing trusted TensorFlow gate. |
| Transformers3198 | Both roles fail collection with missing boto3; complete Torch+TF runtime remains unverified. |
| TensorFlow2727 | Both roles abort under x86 TensorFlow1.15/Rosetta; zero calls, with generated protos also unready. |

These are measured failures or explicit unverified conditions, not missing tasks
silently removed from the denominator. Native source-build alternatives were
not established as either feasible or impossible by this study.

Run the source preparation command above from a source checkout installed with
`python -m pip install -e '.[dev]'`. The controller requires Python3.11+; the
standalone target worker supports the explicitly tested Python3.7+ conditions,
with a locked metadata backport on3.7. It takes a reviewed JSON configuration
as its sole positional argument. Its required fields and failure cases are
exercised by `tests/test_known_task_execution_worker.py`; this is a low-level
adapter, not an installer or an automatic execution of dataset shell fields.
An actual rerun must independently review and freeze the target environment,
source manifest, exact selectors, plugins, resources and caps first.

The public transport checker requires a separately trusted INDEX digest. It
checks gzip and canonical JSON identities, source-role provenance fields,
per-phase aggregation and the unchanged finite qualification contract. It does
not reconstruct private inventories, authenticate the original execution or
rerun model/test programs. Retained package versions and installed hashes are
not portable wheel locks. Complete historical-container or one-command39-task
reproduction is not claimed by this artifact; raw source, resource bytes,
private logs and platform-specific environment preparation remain outside Git.
No public CI job downloads models or runs the39 upstream programs.

From the source checkout, verify the retained public observations and generated
tables offline (Python3.11+, standard library only):

```sh
python -m benchmarks.known_task_execution.report --check \
  --bundle benchmarks/known_task_execution/results/known39-20261015 \
  --expected-index-sha256 06020b127bb16d3b8c2b28438ea3b613d683d550d35b8a3401f36eae695ec45b
python -m benchmarks.known_task_execution.secondary_report --check
```

The exact53-file transport and its capture-time `candidate` classification are
unchanged. That field describes the local export review at capture, not current
GitHub publication or CI status. The [secondary sensitivity report](KNOWN_TASK_SENSITIVITY.md)
keeps all39 primary results separate from the post-hoc30-task qualified subset.

The failed TF2.13.1 Rosetta dependency gate has an explicit AVX diagnostic;
the actual13989 source processes abort with empty captured logs. Attributing
those source aborts to the same cause is an inference, not a quoted source log.
Official PyPI metadata also exposes native ARM TensorFlow alternatives, but
13989 requires `tokenizers>=0.10.1,<0.11` at runtime and3198 pins0.5.2 in setup.
The admissible old releases have no official ARM/universal2 wheels for the
available native interpreters. Source-build feasibility was not tested; an
available TensorFlow wheel alone does not establish a working complete lock.
[TF-macos2.13.1 metadata](https://pypi.org/pypi/tensorflow-macos/2.13.1/json),
[Tokenizers0.10.3](https://pypi.org/pypi/tokenizers/0.10.3/json),
[Tokenizers0.5.2](https://pypi.org/pypi/tokenizers/0.5.2/json).

## Evidence-led research gate

Keras supplies5153/5842 P2P labels (88.2061%); two Keras tasks alone supply
80.8970%. Six tasks have no P2P labels. The39 tasks span six convenience-sampled
repositories, not thousands of independent research samples. Pooling nodes
would hide this imbalance. No confidence interval treating nodes as independent
is reported.

This stage audits the measurement instrument and label portability, not the
benefit of the retrieval method. The earlier localization pilot's failed gates
remain failed; the global-binding natural panel still has zero coverage gain.
A defensible next question is whether version-aware evidence can improve the
cost/abstention tradeoff on tasks with observable downstream behavior. Before a
confirmatory test, freeze untouched repository/time splits, source-compatible
runtimes, strong fresh-retrieval and whole-corpus-invalidation baselines, total
cost accounting and semantic/downstream endpoints. Report all-selected results
and a separately labeled runnable subset; retries and test nodes are not new
samples. These are outstanding research requirements, not completed outcomes.
