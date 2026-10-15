"""Static prediction sealing on authored files only / 仅自编文件的静态预测封存测试。"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import stat

import pytest

from benchmarks.semantic_observer import predict as prediction


REPOSITORY = Path(__file__).resolve().parents[1]


def protocol():
    return {"schema_version": 1, "classification": "owned static pipeline controls",
            "implementation_sha256": prediction.implementation_bindings(REPOSITORY),
            "prediction": {**prediction.FIXED_POLICY, "cpu_seconds": 5, "wall_seconds": 20,
                           "max_rss_mib": 1024, "max_output_mib": 16}}


def task(tmp_path, task_id="owned-real-path", *, production=None):
    roles = []
    for role, value in (("base_tests", 1), ("fixed_tests", 2)):
        root = tmp_path / task_id / role
        root.mkdir(parents=True)
        texts = production if production is not None else {
            "package/a.py": f"X={value}\ndef entry():\n    return X\n",
            "package/b.py": "Y=3\ndef helper():\n    return Y\n"}
        files = []
        for name, source in {**texts, "test_original.py": "raise RuntimeError('must not execute tests')\n"}.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = source.encode() if isinstance(source, str) else source
            path.write_bytes(raw)
            files.append({"path": name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
        roles.append({"role": role, "config": {
            "source_root": str(root), "source_files": files,
            "production_paths": list(texts), "test_files": ["test_original.py"],
            "dependency_versions": {"owned-test-runtime": "1.0"},
            "environment_sha256": "a" * 64}})
    return {"task_id": task_id, "python": "/must/not/launch/target/python",
            "environment": {"classification": "owned metadata only", "sha256": "b" * 64},
            "roles": roles}


def test_actual_methods_get_all_production_texts_with_exact_frozen_limits(tmp_path, monkeypatch):
    original, calls = prediction.evaluate_pair, []

    def observe(before, after, **options):
        calls.append((set(before), set(after), options))
        return original(before, after, **options)

    monkeypatch.setattr(prediction, "evaluate_pair", observe)
    selected = task(tmp_path)
    result = prediction.predict_task(selected, protocol(), repository=REPOSITORY)
    assert result["status"] == "predicted"
    assert calls == [({"package/a.py", "package/b.py"}, {"package/a.py", "package/b.py"},
                      {"anchor_limit": 32, "repeats": 3, "max_depth": 4, "max_nodes": 256})]
    assert not result["target_source_imported"] and not result["target_interpreter_launched"]
    for role in result["roles"]:
        assert role["production_bytes"] > 0
        assert len(role["full_production_files"]) == 2
        assert role["environment"]["task_environment"] == selected["environment"]
        assert role["environment"]["environment_sha256"] == "a" * 64
    assert result["timings_seconds"]["end_to_end"] >= result["timings_seconds"]["methods_including_preparation"]


def test_source_is_never_imported_and_test_assertions_are_never_executed(tmp_path):
    marker = tmp_path / "FORBIDDEN_SIDE_EFFECT"
    source = f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\nX=1\ndef entry():\n    return X\n"
    result = prediction.predict_task(task(tmp_path, production={"a.py": source}), protocol(),
                                     repository=REPOSITORY)
    assert result["status"] == "predicted"
    assert not marker.exists()


@pytest.mark.parametrize("mutation", ["changed", "extra", "missing", "bytecode", "symlink"])
def test_full_source_identity_failures_are_retained_rows(tmp_path, mutation):
    selected = task(tmp_path)
    root = Path(selected["roles"][0]["config"]["source_root"])
    if mutation == "changed":
        (root / "package/a.py").write_text("X=999\n")
    elif mutation == "extra":
        (root / "surprise.txt").write_text("extra bytes")
    elif mutation == "missing":
        (root / "package/a.py").unlink()
    elif mutation == "bytecode":
        (root / "bad.pyc").write_bytes(b"bytecode")
    else:
        (root / "alias.py").symlink_to(root / "package/a.py")
    result = prediction.predict_task(selected, protocol(), repository=REPOSITORY)
    assert result["status"] == "failed"
    assert result["failure"]["phase"] == "source_validation_and_loading"
    assert result["task_id"] == selected["task_id"]


def test_invalid_utf8_is_not_replaced_or_decoded_lossily(tmp_path):
    selected = task(tmp_path, production={"a.py": b"X='\xff'\n"})
    result = prediction.predict_task(selected, protocol(), repository=REPOSITORY)
    assert result["status"] == "failed"
    assert result["failure"]["error_type"] == "UnicodeDecodeError"


@pytest.mark.parametrize("role_names", [None, [], ["base_tests"], ["base_tests", "base_tests"],
                                        ["base", "gold"]])
def test_missing_or_wrong_role_pairs_fail_without_dropping_task(tmp_path, role_names):
    selected = task(tmp_path)
    if role_names is None:
        selected["roles"] = None
    else:
        selected["roles"] = [{**selected["roles"][min(index, 1)], "role": name}
                             for index, name in enumerate(role_names)]
    result = prediction.predict_task(selected, protocol(), repository=REPOSITORY)
    assert result["status"] == "failed"
    assert result["failure"]["phase"] == "configuration"


def test_immutable_output_and_complete_seal_keep_a_failed_task_next_to_a_success(tmp_path):
    bad, good = task(tmp_path, "bad"), task(tmp_path, "good")
    Path(bad["roles"][0]["config"]["source_root"], "package/a.py").write_text("tampered\n")
    output = tmp_path / "predictions"
    frozen = protocol()
    result = prediction.predict({"tasks": [bad, good]}, frozen, output, repository=REPOSITORY)
    assert result["all_selected_count"] == 2
    assert result["failed_count"] == result["predicted_count"] == 1
    assert [row["task_id"] for row in result["rows"]] == ["bad", "good"]
    assert result["all_selected_rows_sealed"] and result["implementation_unchanged"]
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    for row in result["rows"]:
        path = output / row["filename"]
        assert prediction.sha(path.read_bytes()) == row["sha256"]
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert json.loads(path.read_bytes())["closure"]["closed"]
        for item in row["artifacts"]:
            path = output / item["filename"]
            assert prediction.sha(path.read_bytes()) == item["sha256"]
        assert any(item["filename"].endswith("/prediction.json") for item in row["artifacts"])
    diagnostic = output / "input-000/diagnostic.log"
    assert "validate_tree" in diagnostic.read_text() and "ValueError" in diagnostic.read_text()
    assert stat.S_IMODE(diagnostic.stat().st_mode) == 0o600
    old = (output / "SEAL.json").read_bytes()
    with pytest.raises(ValueError):
        prediction.predict({"tasks": [bad, good]}, frozen, output, repository=REPOSITORY)
    assert (output / "SEAL.json").read_bytes() == old


def test_every_failed_task_still_has_its_own_immutable_file_and_seal_entry(tmp_path):
    first, second = task(tmp_path, "first"), task(tmp_path, "second")
    first["roles"] = None
    second["roles"] = []
    result = prediction.predict({"tasks": [first, second]}, protocol(), tmp_path / "all-failed",
                                repository=REPOSITORY)
    assert result["all_selected_count"] == result["failed_count"] == 2
    assert result["predicted_count"] == 0
    assert len({row["filename"] for row in result["rows"]}) == 2
    assert all(row["status"] == "failed" for row in result["rows"])
    assert result["mature_research_established"] is False


@pytest.mark.parametrize("payload_size, failure_phase", [
    (240000, "total_task_artifacts"), (600000, "child_serialization")])
def test_total_output_cap_includes_request_child_and_controller_wrapper(tmp_path, payload_size, failure_phase):
    selected = task(tmp_path)
    selected["environment"]["owned_padding"] = "x" * payload_size
    frozen = protocol()
    frozen["prediction"]["max_output_mib"] = 1
    output = tmp_path / "bounded-output"
    result = prediction.predict({"tasks": [selected]}, frozen, output, repository=REPOSITORY)
    row = json.loads((output / "task-000.json").read_bytes())
    assert row["result"]["status"] == "failed"
    assert row["result"]["failure"]["phase"] == failure_phase
    assert row["result"]["failure"]["error_type"] == "output_limit"
    assert result["failed_count"] == 1 and result["predicted_count"] == 0
    assert result["rows"][0]["task_artifact_bytes"] <= 1024**2
    assert not result["rows"][0]["output_limit_exceeded"]


def test_wrong_implementation_or_nonfrozen_settings_rejected_before_output(tmp_path):
    frozen = protocol()
    frozen["implementation_sha256"]["benchmarks/semantic_observer/methods.py"] = "0" * 64
    output = tmp_path / "never-created"
    with pytest.raises(ValueError):
        prediction.predict({"tasks": [task(tmp_path)]}, frozen, output, repository=REPOSITORY)
    assert not output.exists()
    altered = protocol()
    altered["prediction"]["anchor_limit"] = 64
    with pytest.raises(ValueError):
        prediction.validate_protocol(altered, REPOSITORY)


def test_unreviewed_cli_input_file_hash_is_rejected(tmp_path):
    manifest, frozen = tmp_path / "manifest.json", tmp_path / "protocol.json"
    manifest.write_text(json.dumps({"tasks": []}))
    frozen.write_text(json.dumps(protocol()))
    output = tmp_path / "no-run"
    with pytest.raises(ValueError):
        prediction.main(["--manifest", str(manifest), "--manifest-sha256", "0" * 64,
                         "--protocol", str(frozen), "--protocol-sha256", "0" * 64,
                         "--output", str(output)])
    assert not output.exists()


def test_private_output_cannot_write_into_source_or_public_repository(tmp_path):
    selected = task(tmp_path)
    frozen = protocol()
    source_output = Path(selected["roles"][0]["config"]["source_root"]) / "prediction-output"
    with pytest.raises(ValueError):
        prediction.predict({"tasks": [selected]}, frozen, source_output, repository=REPOSITORY)
    with pytest.raises(ValueError):
        prediction.predict({"tasks": [selected]}, frozen, REPOSITORY / "forbidden-private-output",
                           repository=REPOSITORY)


def test_production_scope_cannot_include_tests_or_unpinned_files(tmp_path):
    selected = task(tmp_path)
    selected["roles"][0]["config"]["production_paths"] = ["test_original.py"]
    result = prediction.predict_task(selected, protocol(), repository=REPOSITORY)
    assert result["status"] == "failed"
    selected["roles"][0]["config"]["production_paths"] = ["not-pinned.py"]
    result = prediction.predict_task(selected, protocol(), repository=REPOSITORY)
    assert result["status"] == "failed"


def test_input_manifest_is_not_mutated(tmp_path):
    selected = task(tmp_path)
    original = deepcopy(selected)
    prediction.predict_task(selected, protocol(), repository=REPOSITORY)
    assert selected == original
