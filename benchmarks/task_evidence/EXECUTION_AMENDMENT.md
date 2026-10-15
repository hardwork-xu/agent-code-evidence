# Execution-correctness amendment / 执行正确性修订

2026-10-05, after independent review of the pre-commit pilot and before the source
freeze / corrected primary reproduction.

The original worker unconditionally inserted `from __future__ import annotations`
when compiling extracted functions. None of the selected upstream test modules
contains that future import. This changes execution of nested class annotations,
including calls that tracing is intended to observe. Passing original assertions
alone did not detect this semantic change. The pilot's execution-witness metrics
are **invalid for research claims**; preserve the raw pilot and do not describe a
corrected run as an independent replication of valid pilot results.

Correction: carry only the original module's `__future__` statements into the
extracted-function module and use `compile(..., dont_inherit=True)` so the worker's
own future flags cannot leak into the original function. A regression test checks
both eager and postponed annotation behavior using a nested-class annotation with
an observable function call. The nine case functions, arguments, sources, hints,
selection rules, graph policy and scoring goals are unchanged. The original
manifest and premeasurement protocol remain byte-identical; primary provenance
additionally records this amendment's hash.

Separate reporting correction found during pilot inspection: stale-context size
must count all supplied old lines, not only old spans credited to current source.
Recall's numerator/denominator definition remains unchanged; actual old-context
size and credited-current-source lines are now separately reported.

首次提取器错误地给原始测试添加了延迟注解语义，改变了潜在执行路径。因此试运行
指标不能作为研究结论。修订仅恢复上游原有编译标志并阻止 worker 标志泄漏；案例、
参数、来源、提示和比较协议未变。另修正旧上下文的行数计费。历史失败和原始结果
完整保留；修正后的运行是同一固定样本的重新执行，不是新的留出集。

Independent review also found incomplete harness integrity checks, repaired before
freeze: the pilot sandbox only denied reads under two directory trees and allowed
other outside reads, demonstrated with a controlled temporary sentinel. The new
profile denies reads by default and preflight includes an outside temporary-file
read. Explicit runtime exceptions permit root-directory data and only ancestor
metadata for allowed roots: macOS loader/realpath require these to start Python;
they do not permit the controlled outside file contents. Import-tree checks reject stale bytecode/native artifacts and symlinks before
reading; `-B` alone only disables bytecode writes. No such artifacts were present
in the inspected study inputs, but their absence must be verified on reproduction.
Scoring now rejects missing, reordered or duplicated cases and mismatched repeat,
invocation, outcome or source-line identities rather than accepting a shortened
`zip`. Source decoding preserves original newline bytes, and retained worker-error
payloads sanitize task-owned absolute paths. These checks change no selected case.

Completed child executions now atomically checkpoint progress. A later exception
or interruption records a sanitized failed stage and cannot silently convert an
incomplete case set into success. Historical pilot files are not overwritten.

Post-pilot method-review amendment, before corrected source freeze: add explicit
tracing-perturbation controls. Every case/version now has two traced and two
untraced executions in separate fresh processes (72 children total). Assertions,
parameters, fixture setup and original compiler flags are identical. Eligibility
requires deterministic repeats and identical per-invocation assertion/failure
outcomes with and without tracing. Untraced runs contribute no witness lines.
This check does not establish equivalence to a full pytest environment; isolated
function/fixture adaptations remain a stated limitation. The invalid pilot had no
such controls and cannot supply this evidence. No case or retrieval setting changes.

Final provenance records a UUID run ID, UTC start/finish, portable command,
implementation/source identities and dirty flags. Before successful completion the
runner rechecks implementation, manifest, amendment, protocol, source and archive
bytes; changes fail the run while preserving completed child records. Python `-I`
ignores `PYTHONHASHSEED`, so this study makes no fixed hash-seed claim: deterministic
repeated outcomes/traces are an empirical gate in the recorded environment.
