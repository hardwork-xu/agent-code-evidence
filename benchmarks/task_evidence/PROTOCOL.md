# Task execution witness audit: premeasurement plan

2026-10-04. No resolver coverage observed when written. Nine upstream assertion
cases, selected for deterministic in-process execution, no external runtime deps,
no filesystem/network effects, and direct callable entrypoint localization.

- packaging: TestSpecifier.test_specifier_prereleases_detection (all 14 literal
  upstream parameter pairs), TestSpecifierSet.test_create_from_specifiers,
  TestMetadata.test_optional_defaults_to_none (keywords parameter only).
- attrs: TestMakeClass.test_annotations,
  TestAttrs.test_pre_init_kw_only_work_with_defaults (both validation states),
  TestAttrs.test_init_subclass (both original slots states).
- pluggy: test_set_blocked, test_pm_name, test_call_extra (original pm fixture).

Reuse exact pinned release pairs from revision_tasks frozen protocol, but execute
original after-version test bodies against both package versions. No test suite,
conftest, setup.py, nox, or arbitrary build hook is imported. Extract a function by
AST-qualified identity, drop its outer decorators, preserve its body unchanged;
provide explicit reviewed imports/arguments and tiny fixture equivalents.
Keep source/test/license bytes and hashes. No model or repair score is claimed.

Primary independent label: unique in-repository physical source lines reached by
Python tracing while each upstream test callable executes. Imports/prelude are
outside the tracing window; dynamically generated code is separately counted.
Current graphs are scored by source-span overlap against after-version witnesses.
Controls: anchor spans, current full source (unbudgeted upper bound), lexical BM25
20-line windows at graph's unique source-line budget, old-version graph. The old
context receives current-source credit only for byte-identical uniquely located
spans; unmatched old spans are retained and reported. Graph policy depth=4,
nodes=256. Report macro per-case and per-repo recall, line budget, assertion
pass/fail in each version, frontier statuses, no claims that witness recall means
minimal/sufficient context or model/repair quality. Cases are a convenience sample
from known development repositories, not a heldout dataset or natural bug census.

Run each version twice in separate processes. Use macOS Seatbelt with no network,
process forks, or writes; fail closed if unavailable. Independently validate trace
identity and deterministic outcomes. Preserve all failures and missing witnesses.
No timings are recorded or compared.

Premeasurement source-review amendment (2026-10-04): exact upstream class names
are TestAttributes.test_pre_init_kw_only_work_with_defaults and
TestFunctional.test_init_subclass; earlier TestAttrs labels were inherited from
historical probe metadata. No case function or parameter selection changed.
The original prereleases matrix has 14 parameter pairs. PM fixture is precisely
PluginManager('example'); fixture construction/imports are outside trace scope.
