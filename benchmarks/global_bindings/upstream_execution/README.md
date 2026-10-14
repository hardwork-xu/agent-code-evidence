# Pinned upstream execution inputs

[简体中文](README_zh.md)

This directory contains source/license pins, exact upstream test selections and
sanitized **development resource preflight** records. It contains no upstream
source bundle and no candidate graph predictions. All baseline outcomes were
known before the subsequent graph study: these are external executable validation
inputs, **not unseen holdout, necessary-context gold or mature research results**.

| Official upstream | Fixed commit | Immediate parent | Cases | Fixed passed | Parent failed |
|---|---|---|---:|---:|---:|
| [Marshmallow](https://github.com/marshmallow-code/marshmallow) | `7dff08fcb7fb` | `2d30a962a0a1` | 7 | 7 | 1 |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | `0b2880591780` | `791414804eff` | 1 | 1 | 1 |
| [TOML Kit](https://github.com/python-poetry/tomlkit) | `6b5f079099d4` | `229ee8660872` | 18 | 18 | 17 |
| [Python Semver](https://github.com/python-semver/python-semver) | `37ae009c7cac` | `1d515915d50b` | 17 | 17 | 9 |

These **43 parameterized cases belong to four upstream changes**. The same fixed
upstream test/fixture files run against both production source versions; no
assertions are edited. The parent failures are expected historical upstream
behavior differences, not ContextProof failures. The tests cover NaN exception
type, user-path expansion, empty array-of-tables rendering and prerelease token
families. One IPython-only dotenv regression was excluded before execution for
its interactive-framework dependency; it remains in `inputs.json`.

The additional [Pyparsing](https://github.com/pyparsing/pyparsing) source at
`f803ae834288032a700331977639fc49c62fcd7f` contributes **all 23** methods in
`Test02_WithoutPackrat` with `ParseAction` or `TrimArity` in the upstream name.
All passed. Its 200 real `_trim_arity` call/return observations include an import
changing `_trim_arity_call_line` from `NoneType` to `FrameSummary`, and
`pa_call_line_synth` from an empty tuple to length two. Two exception tests only
assert inside `except`, so their passes alone cannot establish exception behavior.
The earlier three-method arity diagnostic is retained separately; do not add it
as three independent cases to this panel.

## Reproduce

Reference execution uses Python **3.12**, pytest **8.4.2**, macOS arm64. The
stdlib runner supports macOS/Linux; Windows execution is unverified. Resource
durations include Python tracing and are feasibility observations, not latency
comparisons. Original per-process peak RSS was 41.97–72.12 MiB for the four pairs
and 92.22 MiB for the whole Pyparsing panel. No commercial key is required.

From the repository root, use explicit directories outside every Git tree:

```bash
python3.12 scripts/prepare_global_execution_sources.py \
  --source-root /tmp/contextproof-global-inputs --with-dependencies
python3.12 benchmarks/global_bindings/upstream_execution/run.py \
  --source-root /tmp/contextproof-global-inputs \
  --output /tmp/contextproof-global-execution-new
python3.12 benchmarks/global_bindings/upstream_execution/check.py
python3.12 -m pytest -q tests/test_global_execution_inputs.py
```

`--output` must be new. To prepare offline after acquiring the pinned assets,
pass `--offline --cache ARCHIVE_CACHE --dependency-cache WHEEL_CACHE` to the
preparer. Source folders use `owner--repo-commitprefix` under `--source-root`;
`prepared.json` uses relative paths. All 15 unique archives support the eight
current-head source scans plus the four fixed/parent pairs. Preparation verifies
TLS, archive/wheel digests, every regular file, source-role identity and resource
caps. It records/skips links rather than creating or following them. Dependency
wheels are pure Python and unpacked outside Git; no setup/build script runs.
The worker uses Python isolation, a sanitized environment, verified imports and
disabled pytest plugin auto-discovery. This is not an OS sandbox.

## Records and limits

- `inputs.json`: immutable source versions, file hashes, test roles, selection and exclusions.
- `dependencies.json`: exact seven wheel URLs, versions, hashes and license bytes.
- `results/upstream-preflight.json`: all eight source-role runs, including all 28 parent failures.
- `results/global-whole-panel.json`: all 23 global-writer panel tests and 200 binding observations.
- `results/global-arity-diagnostic.json`: earlier known three-method diagnostic.
- `results/preflight-failures.json`: mistaken repository address, wheel-selector ambiguity and corrected export-path failure.
- `licenses/`: original root license/NOTICE and dependency license bytes.

Python line traces are observed paths for these inputs; they do not prove causal
necessity, complete dynamic dependencies or correctness on every valid input.
Seven of eight head scans contain no explicit function `global` declaration;
this does not rule out mutable state through attributes, aliases or dynamic code.
The source metadata and old/fixed tests were reviewed before graph evaluation;
any subsequent candidate result must retain this development exposure. The
read-only record checker detects missing failures, role substitution, changed
import identity and missing observations; its pass is an integrity check.
Full local stacks/configuration and downloaded source trees remain outside Git.
Never upload the reproduction directory or `.private-logs` as a release asset.

Upstream source remains under its original licenses (including Marshmallow's
Django-derived BSD notice). The runner and record-checking code are part of this
project's MIT implementation; this is unofficial validation infrastructure.
