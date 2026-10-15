"""Independent exact-count scorer controls / 独立精确计数反例。

Handwritten codec constants and authored programs only; no evaluator/SUT data.
仅使用手写常量与自编程序，不读取 evaluator 或上游任务。
"""

from copy import deepcopy
import hashlib
import sys

import pytest

from benchmarks.semantic_observer import GlobalReadObserver
from benchmarks.semantic_observer.methods import evaluate_pair
from benchmarks.semantic_observer.score import score_pair


SHA = "a" * 64
ONE = {"status": "supported", "type": "int", "decimal": "1"}
TWO = {"status": "supported", "type": "int", "decimal": "2"}
UNSUPPORTED = {"status": "unsupported", "type": "other", "reason": "owned_unsupported"}


def row(value=None, **changes):
    result = {"event_kind": "pre_op_binding", "source_path": "module.py", "source_sha256": SHA,
        "code_signature": "b" * 64, "qualname": "read", "function_name": "read", "name": "X",
        "bytecode_offset": 2, "lineno": 3, "end_lineno": 3, "col_offset": 11,
        "end_col_offset": 12, "position_complete": True, "certified_code": True,
        "binding": "module_global", "status": "primitive", "value": deepcopy(value or ONE),
        "count": 1, "first_event": 1, "last_event": 1}
    return result | changes


def observed(rows=None, **changes):
    rows = [row()] if rows is None else rows
    status = {}
    for entry in rows:
        status[entry["status"]] = status.get(entry["status"], 0) + entry["count"]
    total = sum(entry["count"] for entry in rows)
    report = {"schema_version": 1, "state": "closed", "event_semantics":
        "pre_op_binding_not_consumed_operand", "runtime": {"implementation": "cpython",
        "version": [3, 12, 2], "optimize": 0}, "source_pins": {"module.py": SHA},
        "max_observations": 100, "no_observations": not total,
        "measurement_valid": True, "complete": True, "observations": deepcopy(rows),
        "counts": {"eligible_load_global_events": total, "retained_observations": len(rows),
            "retained_events": total, "dropped_observations": 0,
            "uncertified_code_events": sum(r["count"] for r in rows if not r["certified_code"]),
            "unsupported_filename_events": 0, "partial_position_events": 0,
            "exception_events": 0, "status_counts": status},
        "integrity": {"source_initial_verified": True, "source_final_verified": True,
            "trace_intact_at_exit": True, "source_changed": [], "other_threads_seen": False,
            "observer_errors": 0, "body_raised": False}}
    return report | changes


def fact(expected=None, **changes):
    result = {"source_path": "module.py", "source_sha256": SHA, "qualname": "read",
        "runtime_qualname": "read", "source_start_line": 2, "source_end_line": 3,
        "name": "X", "operation": "read", "edge_id": "edge-one",
        "claim_kind": "experimental_runtime_value_hypothesis", "expected": deepcopy(expected or ONE),
        "complete_graph": True, "supporting_graphs": [{"graph_id": "graph-one", "complete_graph": True}]}
    return result | changes


def method(facts=None, *, selection=None, graphs=None, abstentions=None, repeats=1):
    version = {"facts": deepcopy([fact()] if facts is None else facts),
               "abstentions": deepcopy(abstentions or []), "graphs": deepcopy(graphs if graphs
               is not None else [{"graph_id": "graph-one", "complete_graph": True, "frontier_count": 0}])}
    return {"schema_version": 1, "selection": deepcopy(selection if selection is not None else [
        {"path": "module.py", "qualname": "read", "versions_present": ["before", "after"],
         "declaration_counts": {"before": 1, "after": 1}}]), "methods": {
        "currentfresh": {"runs": [{"repeat": index, "versions": {
            "before": deepcopy(version), "after": deepcopy(version)}} for index in range(repeats)]}}}


def score(result=None, report=None, parity=None):
    return score_pair(result or method(), {"before": deepcopy(report or observed()),
                                          "after": deepcopy(report or observed())},
                      role_parity_valid=parity or {"before": True, "after": True})


def output(scored, role="after", name="currentfresh", repeat=0):
    return scored["methods"][name]["runs"][repeat]["versions"][role]


def test_exact_source_owner_and_value_match_keeps_site_event_task_units_distinct():
    result = score(report=observed([row(count=100, last_event=100)]))
    role = output(result)
    summary = role["summary"]
    assert summary["all_retained_sites"] == summary["observed_primitive_module_global_sites"] == 1
    assert summary["all_retained_events"] == summary["matching_primitive_events"] == 100
    assert summary["conditional_primitive_site_accuracy"] == {"numerator": 1, "denominator": 1, "value": 1.0}
    assert summary["conditional_primitive_event_accuracy"]["denominator"] == 100
    assert summary["accuracy_qualified"] and summary["no_observed_primitive_disagreement"]
    assert result["methods"]["currentfresh"]["runs"][0]["task"]["all_retained_sites"] == 2
    assert result["policy"]["runtime_value_hypotheses_are_product_guarantees"] is False
    assert "not_whole_graph_stale_bug" in result["policy"]["mismatch_interpretation"]


def test_one_disagreement_at_same_site_is_not_hidden_by_many_matching_events():
    report = observed([row(count=100, last_event=100),
                       row(TWO, count=1, first_event=101, last_event=101)])
    summary = output(score(report=report))["summary"]
    assert summary["observed_primitive_module_global_sites"] == 1
    assert summary["accepted_primitive_sites"] == summary["mismatching_primitive_sites"] == 1
    assert summary["matching_only_primitive_sites"] == 0
    assert summary["mixed_match_mismatch_sites"] == 1
    assert summary["matching_primitive_events"] == 100 and summary["mismatching_primitive_events"] == 1
    assert summary["conditional_primitive_site_accuracy"]["value"] == 0.0
    assert summary["conditional_primitive_event_accuracy"]["value"] == 100 / 101
    assert summary["no_observed_primitive_disagreement"] is False


def test_same_line_multiple_load_offsets_are_separate_runtime_sites():
    report = observed([row(), row(TWO, bytecode_offset=30, col_offset=20, end_col_offset=21,
                                  first_event=2, last_event=2)])
    summary = output(score(report=report))["summary"]
    assert summary["accepted_primitive_sites"] == 2
    assert summary["matching_only_primitive_sites"] == summary["mismatching_primitive_sites"] == 1
    assert summary["conditional_primitive_site_accuracy"]["value"] == 0.5


@pytest.mark.parametrize(("change", "state"), [
    ({"source_sha256": "c" * 64}, "source_sha_mismatch"),
    ({"source_start_line": 4, "source_end_line": 5}, "owner_span_mismatch"),
    ({"source_path": "other.py"}, "graph_absent"),
    ({"runtime_qualname": "other"}, "graph_absent"),
    ({"name": "Y"}, "graph_absent"),
])
def test_wrong_identity_or_span_cannot_be_called_a_match(change, state):
    summary = output(score(method([fact(**change)])))["summary"]
    assert summary["classification_event_counts"][state] == 1
    assert summary["observed_primitive_module_global_sites"] == 1
    assert summary["accepted_primitive_sites"] == 0
    assert summary["conditional_primitive_site_accuracy"]["value"] is None


def test_nested_qualnames_require_exact_runtime_identity():
    report = observed([row(qualname="outer.<locals>.read")])
    selection = [{"path": "module.py", "qualname": "outer.read",
                  "versions_present": ["before", "after"]}]
    expected = fact(qualname="outer.read", runtime_qualname="outer.<locals>.read")
    assert output(score(method([expected], selection=selection), report))["summary"][
        "accepted_primitive_sites"] == 1
    expected["runtime_qualname"] = "outer.read"
    assert output(score(method([expected], selection=selection), report))["summary"][
        "classification_event_counts"]["graph_absent"] == 1


def test_multiple_derived_hypotheses_abstain_even_if_values_equal():
    result = score(method([fact(), fact(edge_id="edge-two")]))
    summary = output(result)["summary"]
    assert summary["classification_event_counts"]["ambiguous_hypothesis"] == 1
    assert summary["zero_accept"] and not summary["accuracy_qualified"]
    assert output(result)["sites"][0]["hypothesis_edge_ids"] == ["edge-one", "edge-two"]


def test_unselected_graph_absent_graph_abstain_and_ambiguous_owner_are_distinct():
    assert output(score(method([], selection=[])))["summary"]["classification_event_counts"]["unselected"] == 1
    assert output(score(method([])))["summary"]["classification_event_counts"]["graph_absent"] == 1
    abstention = {"source_path": "module.py", "runtime_qualname": "read", "name": "X", "reason": "dynamic"}
    assert output(score(method([], abstentions=[abstention])))["summary"][
        "classification_event_counts"]["graph_abstain"] == 1
    selected = [{"path": "module.py", "qualname": "read", "versions_present": ["before", "after"],
                 "declaration_counts": {"before": 2, "after": 2}}]
    assert output(score(method([], selection=selected)))["summary"][
        "classification_event_counts"]["ambiguous_owner"] == 1


def test_always_abstain_has_zero_coverage_and_undefined_accuracy():
    result = method([])
    result["methods"]["always_abstain"] = result["methods"].pop("currentfresh")
    summary = output(score(result), name="always_abstain")["summary"]
    assert summary["score_qualified"] and not summary["accuracy_qualified"]
    assert summary["primitive_site_coverage"] == {"numerator": 0, "denominator": 1, "value": 0.0}
    assert summary["conditional_primitive_site_accuracy"] == {"numerator": 0, "denominator": 0, "value": None}
    assert summary["no_observed_primitive_disagreement"] is None


def test_all_observed_primitive_sites_remain_denominator_when_unselected():
    rows = [row(), row(name="Y", bytecode_offset=14, first_event=2, last_event=2),
            row(name="Z", qualname="unselected", bytecode_offset=26, first_event=3, last_event=3)]
    summary = output(score(report=observed(rows)))["summary"]
    assert summary["observed_primitive_module_global_sites"] == 3
    assert summary["accepted_primitive_sites"] == 1
    assert summary["primitive_site_coverage"]["value"] == 1 / 3
    assert summary["classification_site_counts"]["graph_absent"] == 1
    assert summary["classification_site_counts"]["unselected"] == 1


def test_unsupported_fact_does_not_remove_primitive_site_from_coverage():
    role = output(score(method([fact(UNSUPPORTED)])))
    assert role["static_fact_counts"] == {"derived_hypotheses": 1, "supported": 0,
                                          "unsupported": 1, "abstentions": 0}
    assert role["summary"]["observed_primitive_module_global_sites"] == 1
    assert role["summary"]["classification_event_counts"]["unsupported_hypothesis"] == 1


def test_builtin_missing_and_unsupported_observed_values_remain_visible():
    rows = [row(UNSUPPORTED, binding="builtin", status="builtin_fallback"),
            row(UNSUPPORTED, binding="missing", status="missing_binding", bytecode_offset=14,
                first_event=2, last_event=2),
            row(UNSUPPORTED, status="unsupported_value", bytecode_offset=26, first_event=3, last_event=3)]
    summary = output(score(report=observed(rows)))["summary"]
    assert summary["all_retained_sites"] == summary["all_retained_events"] == 3
    assert summary["observed_primitive_module_global_sites"] == 0
    assert not summary["score_qualified"] and not summary["accuracy_qualified"]
    assert {key: summary["classification_event_counts"][key] for key in [
        "builtin", "missing", "unsupported_observed_value"]} == {
        "builtin": 1, "missing": 1, "unsupported_observed_value": 1}


def test_whole_graph_frontier_is_separate_from_individual_hypothesis_match():
    graphs = [{"graph_id": "graph-one", "complete_graph": False, "frontier_count": 3}]
    role = output(score(method([fact(complete_graph=False)], graphs=graphs)))
    assert role["summary"]["matching_only_primitive_sites"] == 1
    assert role["whole_graph"] == {"graphs": 1, "complete_graphs": 0,
                                    "incomplete_graphs": 1, "frontier_entries": 3}


@pytest.mark.parametrize("change", ["measurement", "complete", "parity", "source_pin", "counter",
                                     "trace", "threads", "runtime", "position", "uncertified",
                                     "dropped", "body_raised"])
def test_invalid_incomplete_or_nonparity_keeps_diagnostics_but_no_qualified_metrics(change):
    report, parity = observed(), {"before": True, "after": True}
    if change == "measurement":
        report["measurement_valid"] = False
    elif change == "complete":
        report["complete"] = False
    elif change == "parity":
        parity["after"] = False
    elif change == "source_pin":
        report["source_pins"]["module.py"] = "f" * 64
    elif change == "counter":
        report["counts"]["retained_events"] = 99
    elif change == "trace":
        report["integrity"]["trace_intact_at_exit"] = False
    elif change == "threads":
        report["integrity"]["other_threads_seen"] = True
    elif change == "body_raised":
        report["integrity"]["body_raised"] = True
    elif change == "runtime":
        report["runtime"]["version"] = [3, 13, 0]
    elif change == "position":
        report["observations"][0]["col_offset"] = None
        report["observations"][0]["position_complete"] = False
        report["counts"]["partial_position_events"] = 1
    elif change == "uncertified":
        report["observations"][0]["certified_code"] = False
        report["counts"]["uncertified_code_events"] = 1
    elif change == "dropped":
        report["counts"]["eligible_load_global_events"] = 3
        report["counts"]["dropped_observations"] = 2
        report["counts"]["status_counts"] = {"primitive": 1, "unsupported_value": 2}
    result = score(report=report, parity=parity)
    role = output(result)
    assert role["raw_observer_counts"] == report["counts"]
    assert role["summary"]["all_retained_events"] == 1
    assert role["validity_errors"]
    assert not role["summary"]["score_qualified"] and not role["summary"]["accuracy_qualified"]
    assert role["summary"]["conditional_primitive_site_accuracy"]["value"] is None
    assert role["summary"]["primitive_site_coverage"]["value"] is None
    assert not result["methods"]["currentfresh"]["runs"][0]["task"]["score_qualified"]


def test_zero_observations_or_absent_role_cannot_establish_accuracy():
    summary = output(score(report=observed([])))["summary"]
    assert summary["all_retained_events"] == 0 and not summary["score_qualified"]
    assert summary["conditional_primitive_site_accuracy"]["value"] is None
    scored = score_pair(method(), {"before": observed(), "after": None},
                        role_parity_valid={"before": True, "after": False})
    assert output(scored)["validity_errors"] == ["observer_report_missing"]
    assert output(scored)["raw_observer_counts"] is None
    assert not scored["methods"]["currentfresh"]["runs"][0]["task"]["score_qualified"]


@pytest.mark.parametrize(("expected", "actual"), [
    ({"status": "supported", "type": "bool", "value": True}, ONE),
    ({"status": "supported", "type": "float", "hex": "0x0.0p+0"},
     {"status": "supported", "type": "float", "hex": "-0x0.0p+0"}),
])
def test_typed_comparison_preserves_bool_int_and_signed_zero(expected, actual):
    summary = output(score(method([fact(expected)]), observed([row(actual)])))["summary"]
    assert summary["mismatching_primitive_sites"] == 1


def test_static_repeats_do_not_increase_independent_task_count_and_inputs_are_detached():
    data, report = method(repeats=3), observed()
    before = deepcopy((data, report))
    result = score(data, report)
    record = result["methods"]["currentfresh"]
    assert record["independent_task_count"] == 1 and record["repeat_count"] == 3
    assert record["score_repeats_equal"]
    assert all(run["task"]["observed_primitive_module_global_sites"] == 2 for run in record["runs"])
    assert (data, report) == before
    output(result)["raw_observer_counts"]["retained_events"] = 999
    assert report["counts"]["retained_events"] == 1


def test_one_role_without_primitive_observations_does_not_qualify_paired_task():
    scored = score_pair(method(), {"before": observed([]), "after": observed()},
                        role_parity_valid={"before": True, "after": True})
    task = scored["methods"]["currentfresh"]["runs"][0]["task"]
    assert task["observed_primitive_module_global_sites"] == 1
    assert not task["score_qualified"] and not task["accuracy_qualified"]
    assert task["conditional_primitive_site_accuracy"]["value"] is None
    assert output(scored)["summary"]["accuracy_qualified"]


def test_matching_and_mismatching_value_evidence_remains_traceable_per_site():
    report = observed([row(), row(TWO, first_event=2, last_event=2)])
    site, = output(score(report=report))["sites"]
    first, last = site["scored_observations"]
    assert first["observed_value"] == ONE and last["observed_value"] == TWO
    assert first["hypotheses"][0]["expected"] == last["hypotheses"][0]["expected"] == ONE
    assert first["classification"] == "matching" and last["classification"] == "mismatching"
    assert last["first_event"] == last["last_event"] == 2


def test_inconsistent_binding_status_cannot_make_a_qualified_report():
    report = observed([row(binding="builtin")])
    role = output(score(report=report))
    assert "observation_binding_status_inconsistent" in role["validity_errors"]
    assert not role["summary"]["score_qualified"]


def test_empty_method_inventory_and_boolean_schema_are_rejected():
    empty = method()
    empty["methods"] = {}
    with pytest.raises(ValueError, match="At least one method"):
        score(empty)
    bad = method()
    bad["schema_version"] = True
    with pytest.raises(ValueError, match="method schema"):
        score(bad)


@pytest.mark.parametrize("bad", [True, "1", {"status": "supported", "type": "bool", "value": 1},
                                    {"status": "supported", "type": "float", "hex": "nan"}])
def test_malformed_primitive_inputs_are_rejected(bad):
    with pytest.raises((ValueError, TypeError)):
        score(method([fact(bad)]))


def test_real_owned_before_after_dynamic_change_refutes_derived_hypothesis_only(tmp_path):
    if sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 12):
        pytest.skip("Owned runtime observation requires CPython3.12")
    source = "X = 1\ndef read():\n    return X\n"
    raw = source.encode()
    (tmp_path / "module.py").write_bytes(raw)
    reports = {}
    for side, value in [("before", 1), ("after", 2)]:
        namespace = {}
        exec(compile(raw, str(tmp_path / "module.py"), "exec", dont_inherit=True,
                     optimize=sys.flags.optimize), namespace)
        namespace["X"] = value
        with GlobalReadObserver(source_root=tmp_path,
                source_pins={"module.py": hashlib.sha256(raw).hexdigest()}) as observer:
            assert namespace["read"]() == value
        reports[side] = observer.report()
    methods = evaluate_pair({"module.py": source}, {"module.py": source}, repeats=1)
    scored = score_pair(methods, reports, role_parity_valid={"before": True, "after": True})
    for name in ["currentfresh", "whole_guard", "selective"]:
        assert output(scored, role="before", name=name)["summary"]["matching_only_primitive_sites"] == 1
        assert output(scored, name=name)["summary"]["mismatching_primitive_sites"] == 1
    assert output(scored, name="always_abstain")["summary"]["zero_accept"]
    assert scored["policy"]["whole_graph_completeness_is_separate"]
