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
Labels are assertion identifiers, not independent tasks.

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

The first native batch freezes six yt-dlp tasks (12 F2P/236 P2P labels) after
source, dependency, helper and fixture review. Other original tasks remain
pending actual runtime validation; source preparation is not execution.
Python versions, dependency files, protocol and failures are retained separately
from the older localization pilot. No task-success or maturity claim follows
from a passing adapter unit test.

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
