"""Owned offline bundle controls; no upstream execution / 自编离线公开包反例。"""
from copy import deepcopy
import builtins
import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.semantic_observer import report as reporting
from benchmarks.semantic_observer.run import condition_qualified, paired_parity


REPOSITORY = Path(__file__).resolve().parents[1]
SHA = "a" * 64
ONE = {"status": "supported", "type": "int", "decimal": "1"}


def observation(*, decimal="1", count=1, empty=False):
    row = {"event_kind": "pre_op_binding", "source_path": "module.py", "source_sha256": SHA,
        "code_signature": "b" * 64, "qualname": "read", "function_name": "read", "name": "X",
        "bytecode_offset": 2, "lineno": 3, "end_lineno": 3, "col_offset": 11,
        "end_col_offset": 12, "position_complete": True, "certified_code": True,
        "binding": "module_global", "status": "primitive",
        "value": {"status": "supported", "type": "int", "decimal": decimal},
        "count": count, "first_event": 1, "last_event": count}
    rows = [] if empty else [row]
    count = 0 if empty else count
    return {"schema_version": 1, "state": "closed", "event_semantics":
        "pre_op_binding_not_consumed_operand", "runtime": {"implementation": "cpython",
        "version": [3, 12, 2], "optimize": 0}, "source_pins": {"module.py": SHA},
        "max_observations": 100, "no_observations": not count,
        "measurement_valid": True, "complete": True, "observations": rows,
        "counts": {"eligible_load_global_events": count, "retained_observations": len(rows),
            "retained_events": count, "dropped_observations": 0, "uncertified_code_events": 0,
            "unsupported_filename_events": 0, "partial_position_events": 0,
            "exception_events": 0, "status_counts": {"primitive": count} if count else {}},
        "integrity": {"source_initial_verified": True, "source_final_verified": True,
            "trace_intact_at_exit": True, "source_changed": [], "other_threads_seen": False,
            "observer_errors": 0, "body_raised": False}}


def predictions():
    fact = {"source_path": "module.py", "source_sha256": SHA, "qualname": "read",
        "runtime_qualname": "read", "source_start_line": 2, "source_end_line": 3,
        "name": "X", "operation": "read", "edge_id": "edge-one",
        "claim_kind": "experimental_runtime_value_hypothesis", "expected": ONE,
        "complete_graph": True, "supporting_graphs": [{"graph_id": "g", "complete_graph": True}]}
    versions = {role: {"facts": [deepcopy(fact)], "abstentions": [], "graphs": [
        {"graph_id": "g", "complete_graph": True, "frontier_count": 0}]} for role in ("before", "after")}
    result = {"schema_version": 1, "selection": [{"path": "module.py", "qualname": "read",
        "versions_present": ["before", "after"], "declaration_counts": {"before": 1, "after": 1}}],
        "methods": {}}
    for name in reporting.METHODS:
        runs = []
        for repeat in range(3):
            value = deepcopy(versions)
            if name == "always_abstain":
                for role in value.values():
                    role["facts"] = []
                    role["graphs"] = []
            runs.append({"repeat": repeat, "versions": value,
                "semantic_output_sha256": reporting._hypothesis_digest(value),
                "timings_seconds": {"initialization": .01, "capture_including_projection": .02,
                    "replay_including_projection": .03, "total_method": .06,
                    "shared_preparation_separately_measured": .01}})
        result["methods"][name] = {"runs": runs, "repeats_semantically_equal": True}
    return result


def close(result):
    return {"closed": True, "termination_reason": None, "result_present": result is not None,
            "result_error": None, "returncode": 0}


def update_parity(role):
    parity = paired_parity(role["plain"], role["traced"])
    qualification = {kind: condition_qualified(role[kind], role[kind + "_closure"])
                     for kind in ("plain", "traced")}
    parity["condition_qualification"] = qualification
    parity["checks"] = {**parity.get("checks", {}), "closed_regular_conditions":
                         all(row["passed"] for row in qualification.values())}
    parity["passed"] = parity["passed"] and parity["checks"]["closed_regular_conditions"]
    role["parity"] = parity


def task(index=0):
    identity = f"owned/task-{index}"
    result = {"task_id": identity, "prediction": predictions(), "prediction_failure": None,
              "roles": [], "raw_artifact_sha256": {"owned-result": "c" * 64}}
    for name in ("base_tests", "fixed_tests"):
        role = {"role": name}
        for kind in ("plain", "traced"):
            worker = {"schema_version": 1, "task_id": identity, "role": name,
                "observe": kind == "traced", "selected": ["tests/test_owned.py::test_value"],
                "phase_reports": [{"nodeid": "tests/test_owned.py::test_value", "phase": phase,
                    "outcome": "passed", "wasxfail": False, "error_type": None}
                    for phase in ("setup", "call", "teardown")],
                "collection_errors": [], "missing_selectors": [], "pytest_exit_code": 0,
                "status": "completed", "source_before_after_verified": True,
                "network_denials": [], "process_denials": [], "thread_denials": 0,
                "observation": observation() if kind == "traced" else None}
            role[kind] = worker
            role[kind + "_closure"] = close(worker)
        update_parity(role)
        result["roles"].append(role)
    return result


def protocol(count):
    value = json.loads((REPOSITORY / "benchmarks/semantic_observer/protocol-v1.json").read_bytes())
    value["all_selected_tasks"] = count
    value["primary_gates"]["qualified_tasks_required"] = count
    value["primary_gates"]["tasks_with_accepted_sites_min"] = max(1, count // 2)
    # Owned fixtures bind the actual implementation bytes, not an invented pin.
    value["implementation_sha256"] = {name: hashlib.sha256((REPOSITORY / name).read_bytes()).hexdigest()
                                       for name in value["implementation_sha256"]}
    return value


def write_json(path, value):
    path.write_bytes(reporting.canonical(value) + b"\n")


def seal(directory, count):
    files = []
    for path in sorted(directory.glob("*.json")):
        if path.name in reporting.DERIVED | {"INDEX.json"}:
            continue
        raw = path.read_bytes()
        files.append({"path": path.name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    write_json(directory / "INDEX.json", {"schema_version": 1, "run_id": "owned-fixture",
        "all_selected_tasks": count, "files": files})
    return hashlib.sha256((directory / "INDEX.json").read_bytes()).hexdigest()


def bundle(tmp_path, count=2):
    directory = tmp_path / "bundle"
    directory.mkdir()
    write_json(directory / "protocol.json", protocol(count))
    write_json(directory / "provenance.json", {"schema_version": 1, "fixture": True})
    for index in range(count):
        write_json(directory / f"task-{index:03d}.json", task(index))
    return directory, seal(directory, count)


def edit_task(directory, index, edit, count=2):
    path = directory / f"task-{index:03d}.json"
    value = json.loads(path.read_bytes())
    edit(value)
    write_json(path, value)
    return seal(directory, count)


def test_exact_match_gates_and_zero_abstain_accuracy(tmp_path):
    directory, expected = bundle(tmp_path)
    output = reporting.analyze_bundle(directory, expected)
    assert output["all_selected_tasks"] == 2
    for name in reporting.METHODS[:-1]:
        row = output["methods"][name]
        assert row["primary_gate_passed"] is True
        assert row["raw_repeat0_counts"]["accepted_primitive_sites"] == 4
        assert row["conditional_primitive_site_accuracy"] == {"numerator": 4, "denominator": 4, "value": 1.0}
        assert row["all_selected_macro_site_coverage"] == 1
    abstain = output["methods"]["always_abstain"]
    assert abstain["conditional_primitive_site_accuracy"]["value"] is None
    assert abstain["primary_gate_passed"] is None and not abstain["gate_applicable"]


def test_invalid_role_keeps_task_denominator_and_diagnostics(tmp_path):
    directory, _ = bundle(tmp_path)
    def change(value):
        for kind in ("plain", "traced"):
            value["roles"][0][kind]["process_denials"] = ["owned-denial"]
        update_parity(value["roles"][0])
    output = reporting.analyze_bundle(directory, edit_task(directory, 0, change))
    row = output["methods"]["selective"]
    assert row["qualified_tasks"] == 1 and row["independent_tasks"] == 2
    assert row["all_selected_macro_site_coverage"] == .5
    assert row["raw_repeat0_counts"]["accepted_primitive_sites"] == 4
    assert row["qualified_repeat0_counts"]["accepted_primitive_sites"] == 2
    assert not row["primary_gate_passed"]


def test_mismatch_is_negative_and_events_do_not_inflate_sites_or_tasks(tmp_path):
    directory, _ = bundle(tmp_path)
    def change(value):
        value["roles"][1]["traced"]["observation"] = observation(decimal="2", count=100)
    output = reporting.analyze_bundle(directory, edit_task(directory, 0, change))
    row = output["methods"]["currentfresh"]
    assert row["raw_repeat0_counts"]["mismatching_primitive_sites"] == 1
    assert row["raw_repeat0_counts"]["mismatching_primitive_events"] == 100
    assert row["conditional_primitive_site_accuracy"]["value"] == .75
    assert row["independent_tasks"] == 2 and not row["primary_gate_passed"]


def test_empty_role_follows_frozen_scorer_zero_coverage_rule(tmp_path):
    directory, _ = bundle(tmp_path)
    expected = edit_task(directory, 0, lambda v: v["roles"][0]["traced"].update(observation=observation(empty=True)))
    row = reporting.analyze_bundle(directory, expected)["methods"]["selective"]
    assert row["all_selected_macro_site_coverage"] == .5
    assert row["qualified_repeat0_counts"]["accepted_primitive_sites"] == 2


def test_prediction_failure_is_retained_without_substitute(tmp_path):
    directory, _ = bundle(tmp_path)
    def change(value):
        value["prediction"] = None
        value["prediction_failure"] = {"phase": "source_load", "error_type": "UnicodeDecodeError"}
    output = reporting.analyze_bundle(directory, edit_task(directory, 0, change))
    assert len(output["tasks"]) == 2
    assert output["tasks"][0]["prediction_failure"]["phase"] == "source_load"
    for row in output["methods"].values():
        assert row["qualified_tasks"] == 1 and row["all_selected_macro_site_coverage"] <= .5


def test_all_failures_remain_rows_and_undefined_accuracy(tmp_path):
    directory, _ = bundle(tmp_path)
    for index in range(2):
        expected = edit_task(directory, index, lambda v: v.update(prediction=None, prediction_failure={"phase": "owned"}))
    output = reporting.analyze_bundle(directory, expected)
    for row in output["methods"].values():
        assert row["independent_tasks"] == 2 and row["qualified_tasks"] == 0
        assert row["all_selected_macro_site_coverage"] == 0
        assert row["conditional_primitive_site_accuracy"]["value"] is None


def test_repeat_disagreement_fails_stability_without_increasing_n(tmp_path):
    directory, _ = bundle(tmp_path)
    def change(value):
        record = value["prediction"]["methods"]["selective"]
        run = record["runs"][2]
        run["versions"]["after"]["facts"][0]["expected"]["decimal"] = "2"
        run["semantic_output_sha256"] = reporting._hypothesis_digest(run["versions"])
        record["repeats_semantically_equal"] = False
    row = reporting.analyze_bundle(directory, edit_task(directory, 0, change))["methods"]["selective"]
    assert row["stable_prediction_tasks"] == 1
    assert row["independent_tasks"] == 2 and row["all_selected_macro_site_coverage"] == .5
    assert not row["primary_gate_passed"]


@pytest.mark.parametrize("tamper", ["parity", "closure", "repeat_digest", "prediction_flag"])
def test_untrusted_stored_flags_are_recomputed(tmp_path, tamper):
    directory, _ = bundle(tmp_path)
    def change(value):
        if tamper == "parity":
            value["roles"][0]["parity"]["passed"] = False
        elif tamper == "closure":
            value["roles"][0]["plain_closure"]["returncode"] = -6
        elif tamper == "repeat_digest":
            value["prediction"]["methods"]["selective"]["runs"][0]["semantic_output_sha256"] = "d" * 64
        else:
            value["prediction"]["methods"]["selective"]["repeats_semantically_equal"] = False
    expected = edit_task(directory, 0, change)
    with pytest.raises(ValueError):
        reporting.analyze_bundle(directory, expected)


def test_eight_task_macro_and_four_accepting_gate_are_protocol_bound(tmp_path):
    directory, _ = bundle(tmp_path, count=8)
    for index in range(5):
        def change(value):
            for name in reporting.METHODS:
                record = value["prediction"]["methods"][name]
                for run in record["runs"]:
                    for version in run["versions"].values():
                        version["facts"] = []
                    run["semantic_output_sha256"] = reporting._hypothesis_digest(run["versions"])
        expected = edit_task(directory, index, change, count=8)
    row = reporting.analyze_bundle(directory, expected)["methods"]["selective"]
    assert row["qualified_tasks"] == 8 and row["tasks_with_accepted_sites"] == 3
    assert row["all_selected_macro_site_coverage"] == 3 / 8
    assert row["gate_checks"]["all_selected_macro_site_coverage"] is True
    assert row["gate_checks"]["tasks_with_accepted_sites"] is False


@pytest.mark.parametrize("filename", ["INDEX.json", "task-000.json"])
def test_index_and_indexed_byte_tamper_rejected(tmp_path, filename):
    directory, expected = bundle(tmp_path)
    with (directory / filename).open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError):
        reporting.analyze_bundle(directory, expected)


@pytest.mark.parametrize("extra", ["notes.txt", "subdirectory", "symlink"])
def test_unindexed_assets_and_symlinks_rejected(tmp_path, extra):
    directory, expected = bundle(tmp_path)
    if extra == "subdirectory":
        (directory / extra).mkdir()
    elif extra == "symlink":
        (directory / extra).symlink_to(directory / "protocol.json")
    else:
        (directory / extra).write_text("owned")
    with pytest.raises(ValueError):
        reporting.validate_bundle(directory, expected)


@pytest.mark.parametrize("name", ["../escape.json", "/absolute.json", "a//b.json", "a\\b.json", "./a.json"])
def test_unsafe_index_paths_rejected(tmp_path, name):
    directory, _ = bundle(tmp_path)
    index = json.loads((directory / "INDEX.json").read_bytes())
    index["files"][0]["path"] = name
    write_json(directory / "INDEX.json", index)
    with pytest.raises(ValueError):
        reporting.validate_bundle(directory, hashlib.sha256((directory / "INDEX.json").read_bytes()).hexdigest())


def test_frozen_sources_checked_before_any_dynamic_scoring_import(tmp_path, monkeypatch):
    directory, _ = bundle(tmp_path)
    path = directory / "protocol.json"
    value = json.loads(path.read_bytes())
    value["implementation_sha256"]["benchmarks/semantic_observer/score.py"] = "f" * 64
    write_json(path, value)
    expected = seal(directory, 2)
    def forbidden(*args, **kwargs):
        pytest.fail("scoring import occurred before all source bindings were verified")
    monkeypatch.setattr(reporting, "_execute_verified", forbidden)
    with pytest.raises(ValueError, match="frozen implementation changed"):
        reporting.analyze_bundle(directory, expected)


def test_duplicate_json_keys_and_indexed_missing_files_rejected(tmp_path):
    directory, _ = bundle(tmp_path)
    (directory / "provenance.json").write_bytes(b'{"a":1,"a":2}')
    with pytest.raises(ValueError, match="duplicate JSON"):
        reporting.validate_bundle(directory, seal(directory, 2))


def test_deterministic_bilingual_render_and_check_detects_changed_derived_file(tmp_path):
    directory, expected = bundle(tmp_path)
    first = reporting.report(directory, expected)
    raw = {name: (directory / name).read_bytes() for name in reporting.DERIVED}
    assert reporting.report(directory, expected, check=True) == first
    reporting.report(directory, expected)
    assert raw == {name: (directory / name).read_bytes() for name in reporting.DERIVED}
    assert b"currentfresh" in raw["REPORT.md"] and b"currentfresh" in raw["REPORT_zh.md"]
    (directory / "REPORT.md").write_bytes(raw["REPORT.md"] + b"\n")
    with pytest.raises(ValueError, match="generated report differs"):
        reporting.report(directory, expected, check=True)


def test_calibration_optional_and_original_fix_diagnostics_not_repair_claim(tmp_path):
    directory, _ = bundle(tmp_path)
    write_json(directory / "calibration.json", {"known_tasks": 2, "qualified_role_pairs": 0})
    output = reporting.analyze_bundle(directory, seal(directory, 2))
    assert output["calibration"]["qualified_role_pairs"] == 0
    assert output["tasks"][0]["original_fix_test_diagnostic"]["generated_repair_success"] is False
    assert output["policy"]["new_generated_repairs"] is False


def test_cli_requires_independently_recorded_index_hash(tmp_path):
    with pytest.raises(SystemExit) as error:
        reporting.main(["--bundle", str(tmp_path)])
    assert error.value.code == 2


def test_protocol_denominator_or_missing_threshold_rejected(tmp_path):
    directory, _ = bundle(tmp_path)
    path = directory / "protocol.json"
    value = json.loads(path.read_bytes())
    del value["primary_gates"]["tasks_with_accepted_sites_min"]
    write_json(path, value)
    with pytest.raises(ValueError, match="primary gates"):
        reporting.analyze_bundle(directory, seal(directory, 2))


def test_missing_source_role_and_duplicate_task_rejected(tmp_path):
    directory, _ = bundle(tmp_path)
    expected = edit_task(directory, 0, lambda value: value["roles"].pop())
    with pytest.raises(ValueError, match="both source roles"):
        reporting.analyze_bundle(directory, expected)


def test_verified_bytes_not_reopened_when_source_swaps_before_compile(tmp_path, monkeypatch):
    directory, expected = bundle(tmp_path)
    value = json.loads((directory / "protocol.json").read_bytes())
    repository = tmp_path / "owned-checkout"
    for name in value["implementation_sha256"]:
        path = repository / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((REPOSITORY / name).read_bytes())
    real_compile = builtins.compile
    target = repository / "benchmarks/semantic_observer/score.py"
    swapped = []
    def swap(source, filename, *args, **kwargs):
        if filename == str(target):
            target.write_bytes(b'raise RuntimeError("unverified replacement executed")\n')
            swapped.append(True)
        return real_compile(source, filename, *args, **kwargs)
    monkeypatch.setattr(builtins, "compile", swap)
    with pytest.raises(ValueError, match="frozen implementation changed"):
        reporting.analyze_bundle(directory, expected, repository=repository)
    assert swapped == [True]


def test_repeated_mixed_call_events_remain_ordered_and_do_not_become_qualified(tmp_path):
    directory, _ = bundle(tmp_path)
    def change(value):
        for role in value["roles"]:
            for kind in ("plain", "traced"):
                reports = role[kind]["phase_reports"]
                extra = {**reports[1], "outcome": "failed", "error_type": "AssertionError"}
                reports.insert(2, extra)
                role[kind]["pytest_exit_code"] = 1
                role[kind + "_closure"]["returncode"] = 1
            update_parity(role)
    output = reporting.analyze_bundle(directory, edit_task(directory, 0, change))
    diagnostic = output["tasks"][0]["original_fix_test_diagnostic"]
    assert diagnostic["before_call_count"] == diagnostic["after_call_count"] == 2
    assert [r["outcome"] for r in diagnostic["before_phase_events"] if r["phase"] == "call"] == ["passed", "failed"]
    assert len(diagnostic["before_phase_events"]) == 4
    assert output["tasks"][0]["role_parity"]["base_tests"]["passed"] is False
    assert output["methods"]["selective"]["qualified_tasks"] == 1


def test_all_actual_methods_zero_accept_is_never_accuracy_or_gate_success(tmp_path):
    directory, _ = bundle(tmp_path)
    for index in range(2):
        def change(value):
            for record in value["prediction"]["methods"].values():
                for run in record["runs"]:
                    for version in run["versions"].values():
                        version["facts"] = []
                    run["semantic_output_sha256"] = reporting._hypothesis_digest(run["versions"])
        expected = edit_task(directory, index, change)
    output = reporting.analyze_bundle(directory, expected)
    for name in reporting.METHODS[:-1]:
        row = output["methods"][name]
        assert row["qualified_tasks"] == 2
        assert row["conditional_primitive_site_accuracy"]["value"] is None
        assert row["all_selected_macro_site_coverage"] == 0
        assert row["primary_gate_passed"] is False


def test_worker_truthy_strings_and_nonboolean_instrumentation_rejected(tmp_path):
    directory, _ = bundle(tmp_path)
    expected = edit_task(directory, 0, lambda value: value["roles"][0]["plain"].update(source_before_after_verified="yes"))
    with pytest.raises(ValueError, match="invalid worker flags"):
        reporting.analyze_bundle(directory, expected)


def test_original_prediction_costs_preserved_with_distinct_median_and_end_to_end_boundaries(tmp_path):
    directory, _ = bundle(tmp_path)
    measurement = {"timings_seconds": {"source_validation_and_load": 1.1,
        "methods_including_preparation": 5.5, "final_validation": .1, "end_to_end": 6.7},
        "closure": {"closed": True, "returncode": 0, "wall_seconds": 7,
                    "sampled_peak_rss_mib": 50, "output_bytes": 512,
                    "rss_sample_observed": True}}
    def change(value):
        value["prediction_measurement"] = deepcopy(measurement)
        value["prediction"]["preparation_seconds"] = .123
        for name in reporting.METHODS[:-1]:
            for run, capture, replay, total in zip(value["prediction"]["methods"][name]["runs"],
                                                  (.1, .2, .9), (.01, .03, .07), (.12, .25, 1.1)):
                run["timings_seconds"].update(capture_including_projection=capture,
                    replay_including_projection=replay, total_method=total)
    output = reporting.analyze_bundle(directory, edit_task(directory, 0, change))
    assert output["tasks"][0]["prediction_measurement"] == measurement
    assert output["tasks"][0]["common_preparation_seconds"] == .123
    raw = output["tasks"][0]["methods"]["currentfresh"]["timings_seconds"]
    assert [row["capture_including_projection"] for row in raw] == [.1, .2, .9]
    assert output["methods"]["currentfresh"]["primary_gate_passed"] is True
    english = reporting.render(output).decode()
    chinese = reporting.render(output, chinese=True).decode()
    median_row = "| owned/task-0 | currentfresh | 10 | 200 | 30 | 250 |"
    boundary_row = "| owned/task-0 | 1100 | 123 | 5500 | 100 | 6700 | 7000 |"
    assert median_row in english and median_row in chinese
    assert boundary_row in english and boundary_row in chinese
    assert "excludes shared preparation" in english
    assert "without speed ratios" in english


def test_missing_prediction_measurements_are_explicit_and_not_zero(tmp_path):
    directory, expected = bundle(tmp_path)
    output = reporting.analyze_bundle(directory, expected)
    assert output["tasks"][0]["prediction_measurement"] is None
    assert output["tasks"][0]["common_preparation_seconds"] is None
    rendered = reporting.render(output).decode()
    assert "| owned/task-0 | " + " | ".join(["not reported / not run"] * 6) + " |" in rendered
    assert "not a claim about whether execution occurred" in rendered


def test_partial_failed_prediction_retains_measured_end_to_end_but_no_method_median(tmp_path):
    directory, _ = bundle(tmp_path)
    def change(value):
        value.update(prediction=None, prediction_failure={"phase": "actual_static_methods"},
                     prediction_measurement={"timings_seconds": {"end_to_end": .5},
                                             "closure": {"wall_seconds": .9}})
    output = reporting.analyze_bundle(directory, edit_task(directory, 0, change))
    assert output["tasks"][0]["prediction_measurement"]["timings_seconds"]["end_to_end"] == .5
    rendered = reporting.render(output).decode()
    assert "| owned/task-0 | currentfresh | " + " | ".join(["not reported / not run"] * 4) + " |" in rendered
    assert "| 500 | 900 |" in rendered
    assert output["methods"]["currentfresh"]["qualified_tasks"] == 1


def test_partial_repeat_timing_is_not_silently_replaced_with_two_repeat_median(tmp_path):
    directory, _ = bundle(tmp_path)
    def change(value):
        del value["prediction"]["methods"]["currentfresh"]["runs"][1]["timings_seconds"]["total_method"]
    output = reporting.analyze_bundle(directory, edit_task(directory, 0, change))
    rendered = reporting.render(output).decode()
    assert "| owned/task-0 | currentfresh | 10 | 20 | 30 | not reported / not run |" in rendered
    assert output["methods"]["currentfresh"]["primary_gate_passed"] is True


def test_actual_prediction_boundary_fields_are_retained_without_concealing_target_execution(tmp_path):
    directory, _ = bundle(tmp_path)
    measurement = {'timings_seconds': {'end_to_end': .2}, 'closure': {'wall_seconds': .3},
                   'scope': 'source validation through final validation; serialization separate',
                   'target_source_imported': False, 'target_interpreter_launched': False}
    def change(value):
        value['prediction_measurement'] = deepcopy(measurement)
    expected = edit_task(directory, 0, change)
    result = reporting.analyze_bundle(directory, expected)
    assert result['tasks'][0]['prediction_measurement'] == measurement
    for flag in ('target_source_imported', 'target_interpreter_launched'):
        bad = deepcopy(measurement)
        bad[flag] = True
        with pytest.raises(ValueError, match='source-only'):
            reporting._measurement(bad)
    with pytest.raises(ValueError, match='timing scope'):
        reporting._measurement({'scope': 1})
