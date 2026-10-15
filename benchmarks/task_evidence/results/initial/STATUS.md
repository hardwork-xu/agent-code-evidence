# Invalid execution-semantics pilot; not research evidence

Independent review found that the worker forced postponed annotations absent from
the original upstream test modules. This changes execution semantics and the
trace labels; all pilot witness metrics are invalid for research claims. See
`../../EXECUTION_AMENDMENT.md`. No statement about graph superiority may rely on
this pilot. The original assertions passing did not validate extraction semantics.

This first execution preceded the source freeze commit. Preserve its raw runs and
original summaries. Nine after-version cases passed, repeated traces and outcomes
agreed, and seven cases failed on the before version. No model ran.

Known reporting defect identified before primary freeze: stale graph
`metrics.stale_graph_current_bytes.context_lines` counts only spans credited to
current bytes; actual supplied context is `stale_context_lines`. This understates
stale context cost/density denominator. This accounting issue alone does not change recall, but the separate compiler
semantics error above invalidates pilot trace recall. The corrected harness
now reports actual old-context line count and separately labels credited lines.

This run's provenance records benchmark file hashes but predates the added Git
commit/dirty-state and runtime-source hash fields. Do not describe it as a clean
commit run or use its context-size column as the final comparison.

Further independent review showed the pilot read policy was not a complete outside
allowlist: a controlled outside temporary-file read remained possible. The pilot
therefore also fails its stated isolation contract. Bytecode import and missing-row
validation holes were found and repaired for reproduction; independent inspection
found no bytecode/native artifacts in the six actual input snapshots. Preserve the
failure distinctions: a possible harness pollution path is not evidence that this
pilot loaded such artifacts.
