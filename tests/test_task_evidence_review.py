"""Independently authored counterexamples for task-execution evidence integrity."""
import copy
import json
from pathlib import Path
import platform
import py_compile
import sys
import tempfile

import pytest

from benchmarks.task_evidence.suite import digest, verified_texts
from benchmarks.task_evidence.worker import compile_function
from scripts.run_task_evidence import isolated, validate_runs
from scripts import run_task_evidence as runner


@pytest.mark.parametrize("postponed", [False, True])
def test_original_nested_annotation_evaluation_is_preserved(postponed):
    source = ("from __future__ import annotations\n" if postponed else "") + (
        "def selected():\n"
        "    class Local:\n"
        "        value: marker()\n"
        "    return Local.__annotations__['value']\n"
    )
    effects = []
    def marker():
        effects.append("evaluated")
        return int
    namespace = {"marker": marker}
    code, name = compile_function(source, "selected", "controlled_upstream.py")
    exec(code, namespace)
    observed = namespace[name]()
    if postponed:
        assert observed == "marker()"
        assert effects == []
    else:
        assert observed is int
        assert effects == ["evaluated"]


@pytest.mark.parametrize("artifact", ["bytecode", "native"])
def test_unhashed_import_artifacts_cannot_override_verified_python(tmp_path, artifact):
    root = tmp_path.resolve()
    source = root / "src/review_module.py"
    source.parent.mkdir()
    source.write_text("answer = 1\n")
    pin = {"source_files": {"src/review_module.py": digest(source.read_bytes())}}
    if artifact == "bytecode":
        py_compile.compile(str(source), doraise=True)
    else:
        (source.parent / "review_module.so").write_bytes(b"controlled unverified artifact")
    with pytest.raises(ValueError, match="unverified bytecode or native"):
        verified_texts(root, pin)


def test_verified_source_retains_crlf_and_nonphysical_unicode_separator(tmp_path):
    root = tmp_path.resolve()
    source = root / "src/module.py"
    source.parent.mkdir()
    raw = "# Comment with unicode separator \u2028 inside one physical line\r\nvalue = 1\r\n".encode()
    source.write_bytes(raw)
    pin = {"source_files": {"src/module.py": digest(raw)}}
    observed = verified_texts(root, pin)["src/module.py"]
    assert observed.encode() == raw


def run_fixture():
    invocation = {"kwargs": {"value": 1}}
    case = {"id": "case-a", "repository": "controlled", "invocations": [invocation]}
    worker = {"case_id": "case-a", "trace_enabled": True, "passed": True, "invocations": [
        {"invocation": invocation, "passed": True, "failure": None,
         "lines": [["src/module.py", 1]], "generated_lines": []}]}
    control = copy.deepcopy(worker)
    control["trace_enabled"] = False
    control["invocations"][0]["lines"] = []
    row = {"id": "case-a", "repository": "controlled", "runs": {
        "before": [copy.deepcopy(worker), copy.deepcopy(worker)],
        "after": [copy.deepcopy(worker), copy.deepcopy(worker)]}, "untraced_runs": {
        "before": [copy.deepcopy(control), copy.deepcopy(control)],
        "after": [copy.deepcopy(control), copy.deepcopy(control)]}}
    corpora = {("controlled", state): {"src/module.py": "value = 1\n"}
               for state in ["before", "after"]}
    return {"cases": [case]}, [row], corpora


@pytest.mark.parametrize("mutation", [
    "empty", "row_identity", "worker_identity", "repeat_count", "invocation_identity",
    "unknown_path", "out_of_bounds", "duplicate_line", "contradictory_pass",
    "missing_controls", "untraced_has_lines", "wrong_trace_flag",
])
def test_invalid_execution_records_never_become_successful_summaries(mutation):
    manifest, rows, corpora = run_fixture()
    validate_runs(manifest, rows, corpora)
    invocation = rows[0]["runs"]["after"][0]["invocations"][0]
    if mutation == "empty":
        rows.clear()
    elif mutation == "row_identity":
        rows[0]["id"] = "wrong"
    elif mutation == "worker_identity":
        rows[0]["runs"]["after"][0]["case_id"] = "wrong"
    elif mutation == "repeat_count":
        rows[0]["runs"]["before"].pop()
    elif mutation == "invocation_identity":
        invocation["invocation"] = {"kwargs": {"value": 2}}
    elif mutation == "unknown_path":
        invocation["lines"] = [["src/not_manifested.py", 1]]
    elif mutation == "out_of_bounds":
        invocation["lines"] = [["src/module.py", 2]]
    elif mutation == "duplicate_line":
        invocation["lines"].append(["src/module.py", 1])
    elif mutation == "contradictory_pass":
        invocation["failure"] = {"type": "AssertionError"}
    elif mutation == "missing_controls":
        del rows[0]["untraced_runs"]
    elif mutation == "untraced_has_lines":
        rows[0]["untraced_runs"]["after"][0]["invocations"][0]["lines"] = [["src/module.py", 1]]
    elif mutation == "wrong_trace_flag":
        rows[0]["runs"]["before"][0]["trace_enabled"] = False
    with pytest.raises(ValueError):
        validate_runs(manifest, rows, corpora)


@pytest.mark.parametrize("state", ["before", "after"])
def test_trace_dependent_assertion_outcome_never_receives_eligible_credit(tmp_path, state):
    manifest, rows, corpora = run_fixture()
    case = manifest["cases"][0]
    case.update({"anchors": [], "test_path": "test_controlled.py", "test_start": 1, "test_end": 1})
    manifest["graph_policy"] = {"max_depth": 4, "max_nodes": 256}
    test_file = tmp_path / "controlled/after/test_controlled.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("assert True\n")
    for control in rows[0]["untraced_runs"][state]:
        control["passed"] = False
        control["invocations"][0]["passed"] = False
        control["invocations"][0]["failure"] = {"type": "AssertionError", "message": "controlled"}
    validate_runs(manifest, rows, corpora)
    output = runner.evaluate(manifest, tmp_path, rows, corpora)
    assert len(output) == 1
    assert output[0]["trace_outcomes_consistent"] is False
    assert output[0]["eligible"] is False


@pytest.mark.skipif(platform.system() != "Darwin" or not Path("/usr/bin/sandbox-exec").exists(),
                    reason="runtime restriction is explicitly macOS Seatbelt only")
def test_sandbox_denies_controlled_file_outside_allowlist(tmp_path):
    script_dir = tmp_path.resolve()
    with tempfile.TemporaryDirectory(prefix="task-evidence-review-", dir="/private/tmp") as outside:
        sentinel = Path(outside) / "controlled.txt"
        sentinel.write_text("CONTROLLED_REVIEW_SENTINEL")
        script = script_dir / "probe.py"
        script.write_text(
            "import json\nfrom pathlib import Path\ntry:\n"
            f"    Path({str(sentinel)!r}).read_text()\n"
            "    result = 'ALLOWED'\nexcept PermissionError:\n"
            "    result = 'denied'\nprint(json.dumps({'outside_read': result}))\n")
        assert isolated(script, [], [script_dir]) == {"outside_read": "denied"}


@pytest.mark.skipif(platform.system() != "Darwin" or not Path("/usr/bin/sandbox-exec").exists(),
                    reason="runtime restriction is explicitly macOS Seatbelt only")
def test_published_worker_errors_scrub_task_owned_paths(tmp_path):
    script_dir = tmp_path.resolve()
    script = script_dir / "probe.py"
    script.write_text("import json\nprint(json.dumps({'harness_error':'ControlledError', 'message':"
                      + repr(str(script_dir / "private-scratch-name")) + "}))\n")
    result = isolated(script, [], [script_dir])
    assert result["harness_error"] == "ControlledError"
    assert str(script_dir) not in json.dumps(result)


def test_later_case_checksum_failure_preserves_finished_first_case(tmp_path, monkeypatch):
    sources = tmp_path / "sources"
    test_dir = sources / "controlled/after"
    test_dir.mkdir(parents=True)
    test = test_dir / "test_controlled.py"
    test.write_text("def test_controlled(): pass\n")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    cases = [{"id": name, "repository": "controlled", "test_path": test.name,
              "test_sha256": digest(test.read_bytes()) if name == "first" else "0" * 64}
             for name in ["first", "second"]]
    monkeypatch.setattr(runner, "isolated", lambda *args: {"controlled_child": "completed"})
    progress = tmp_path / "progress.json"
    with pytest.raises(ValueError, match="test file checksum"):
        runner.execute({"cases": cases}, sources, scratch, progress)
    recorded = json.loads(progress.read_text())
    assert recorded["completed_children"] == 8
    assert recorded["expected_children"] == 16
    assert [case["id"] for case in recorded["runs"]] == ["first"]
    assert len(recorded["runs"][0]["runs"]["after"]) == 2
    assert len(recorded["runs"][0]["untraced_runs"]["after"]) == 2


def test_main_failure_records_stage_without_publishing_summary(tmp_path, monkeypatch):
    bench = tmp_path / "controlled-benchmark"
    bench.mkdir()
    protocol = b"Controlled authored fixture\n"
    (bench / "PROTOCOL.md").write_bytes(protocol)
    (bench / "manifest.json").write_text(json.dumps({"protocol_sha256": digest(protocol),
                                                    "repositories": {}, "cases": []}))
    sources = tmp_path / "controlled-sources"
    sources.mkdir()
    output = tmp_path / "output"
    monkeypatch.setattr(runner, "BENCH", bench)
    monkeypatch.setattr(runner, "source_provenance", lambda raw: {"controlled": True})
    monkeypatch.setattr(runner, "preflight", lambda work: {"controlled": "denied"})
    def fail_execution(*args):
        raise ValueError("controlled failure at " + str(sources / "private-name"))
    monkeypatch.setattr(runner, "execute", fail_execution)
    monkeypatch.setattr(sys, "argv", ["run_task_evidence", "--sources", str(sources),
                                      "--output", str(output)])
    with pytest.raises(ValueError, match="controlled failure"):
        runner.main()
    status = json.loads((output / "status.json").read_text())
    assert status["status"] == "failed"
    assert status["stage"] == "execution"
    assert str(sources) not in json.dumps(status)
    assert not (output / "summary.json").exists()
