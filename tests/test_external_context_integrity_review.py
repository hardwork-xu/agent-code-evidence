"""Independent sealed-bundle fixtures / 独立合成封存包，未使用真实评测标签。"""

import argparse
import csv
import io
import json
import tarfile

import pytest

from benchmarks.external_context import runner
from benchmarks.external_context.io import archive_texts, sha256, write_new


def synthetic_bundle(tmp_path, monkeypatch, *, insertion=False):
    task = {"instance_id": "synthetic-1", "repo": "synthetic/repo",
            "base_commit": "a" * 40}
    patch = ("--- a/x.py\n+++ b/x.py\n@@ -1,0 +2 @@\n+added\n" if insertion else
             "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n")
    dataset = tmp_path / "data.csv"
    with dataset.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, [*task, "problem_statement", "patch"])
        writer.writeheader()
        writer.writerow({**task, "problem_statement": "synthetic issue", "patch": patch})
    protocol = {"study_id": "synthetic-review", "methods": ["one", "two"],
                "budgets": [100, 200], "dataset": {"sha256": sha256(dataset.read_bytes())},
                "selection": {"selected_tasks": 1, "tasks": [task]}}
    protocol_path = tmp_path / "protocol.json"
    write_new(protocol_path, protocol)
    monkeypatch.setattr(runner, "PROTOCOL", protocol_path)
    run = tmp_path / "run"
    run.mkdir()
    write_new(run / "manifest.json", {
        "tasks": [task], "provenance": {"protocol_sha256": sha256(protocol_path.read_bytes())},
    })
    prediction = {**task, "status": "predicted", "source": {"source_lengths": {"x.py": 1}},
                  "outputs": [
                      {"method": method, "budget": budget, "status": "ok", "consumed": 90,
                       "blocks": [{"path": "x.py", "start_line": 1, "end_line": 1}]}
                      for method in protocol["methods"] for budget in protocol["budgets"]]}
    args = argparse.Namespace(dataset=dataset, run=run, output=tmp_path / "scores.json")
    return args, prediction


def seal_synthetic(args, prediction):
    """Seal test data before scoring, just like a fixture producer / 封存合成输入。"""
    write_new(args.run / "prediction-000.json", prediction)
    write_new(args.run / "prediction-seal.json", {
        "tasks": 1,
        "files": {"prediction-000.json": sha256((args.run / "prediction-000.json").read_bytes())},
        "manifest_sha256": sha256((args.run / "manifest.json").read_bytes()),
    })


def test_review_rectangular_method_budget_bundle_is_scored(tmp_path, monkeypatch):
    args, prediction = synthetic_bundle(tmp_path, monkeypatch)
    seal_synthetic(args, prediction)
    runner.score(args)
    result = json.loads(args.output.read_text())
    scores = result["tasks"][0]["scores"]
    assert {(s["method"], s["budget"]) for s in scores} == {
        ("one", 100), ("one", 200), ("two", 100), ("two", 200),
    }
    assert len(scores) == 4
    assert all(s["line"]["recall"] == 1 for s in scores)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unknown_method", "wrong_budget"])
def test_review_changed_method_denominators_rejected(tmp_path, monkeypatch, mutation):
    args, prediction = synthetic_bundle(tmp_path, monkeypatch)
    if mutation == "missing":
        prediction["outputs"].pop()
    elif mutation == "duplicate":
        prediction["outputs"][-1] = dict(prediction["outputs"][0])
    elif mutation == "unknown_method":
        prediction["outputs"][0]["method"] = "not-in-protocol"
    else:
        prediction["outputs"][0]["budget"] = 999
    seal_synthetic(args, prediction)
    with pytest.raises(ValueError):
        runner.score(args)
    assert not args.output.exists()


@pytest.mark.parametrize("field,value", [("repo", "unrelated/repo"), ("base_commit", "b" * 40)])
def test_review_sealed_identity_must_match_frozen_task(tmp_path, monkeypatch, field, value):
    args, prediction = synthetic_bundle(tmp_path, monkeypatch)
    prediction[field] = value
    seal_synthetic(args, prediction)
    with pytest.raises(ValueError):
        runner.score(args)
    assert not args.output.exists()


@pytest.mark.parametrize("insertion", [False, True])
def test_review_failure_keeps_every_combination_and_no_target_is_not_zero(
    tmp_path, monkeypatch, insertion,
):
    args, prediction = synthetic_bundle(tmp_path, monkeypatch, insertion=insertion)
    prediction.pop("outputs")
    prediction.pop("source")
    prediction.update(status="failed", failure_category="timeout")
    seal_synthetic(args, prediction)
    runner.score(args)
    result = json.loads(args.output.read_text())["tasks"][0]
    assert result["denominator_retained"] is True
    assert len(result["scores"]) == 4
    for score in result["scores"]:
        assert score["intent_to_evaluate_zero"] is True
        assert score["file"]["target"] == 1
        assert score["file"]["recall"] == 0
        assert score["line"]["f1"] == (None if insertion else 0)
        assert score["line"]["target"] == (0 if insertion else 1)


def test_review_failed_prediction_does_not_invent_missing_corpus(tmp_path, monkeypatch):
    args, prediction = synthetic_bundle(tmp_path, monkeypatch)
    prediction.pop("outputs")
    prediction.pop("source")
    prediction.update(status="failed", failure_category="timeout")
    seal_synthetic(args, prediction)
    runner.score(args)
    scores = json.loads(args.output.read_text())["tasks"][0]["scores"]
    assert all(s["line"]["target"] == 1 and s["line"]["f1"] == 0 for s in scores)
    assert all(s["out_of_corpus_target_lines"] is None for s in scores)


def test_review_invalid_diff_retained_as_unscorable_not_empty_success(tmp_path, monkeypatch):
    args, prediction = synthetic_bundle(tmp_path, monkeypatch)
    with args.dataset.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    rows[0]["patch"] = "@@ -1 +1 @@\n-old\n+new\n"
    with args.dataset.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    protocol = json.loads(runner.PROTOCOL.read_text())
    protocol["dataset"]["sha256"] = sha256(args.dataset.read_bytes())
    runner.PROTOCOL.write_text(json.dumps(protocol))
    manifest = json.loads((args.run / "manifest.json").read_text())
    manifest["provenance"]["protocol_sha256"] = sha256(runner.PROTOCOL.read_bytes())
    (args.run / "manifest.json").write_text(json.dumps(manifest))
    seal_synthetic(args, prediction)
    runner.score(args)
    records = json.loads(args.output.read_text())["tasks"]
    assert len(records) == 1
    assert records[0]["label_status"] == "unsupported_or_invalid_diff"
    assert records[0]["denominator_retained"] is True
    assert records[0]["scores"] == []


def test_review_duplicate_source_manifest_id_rejected_before_worker(tmp_path, monkeypatch):
    args, prediction = synthetic_bundle(tmp_path, monkeypatch)
    task = {k: prediction[k] for k in ("instance_id", "repo", "base_commit")}
    source = {**task, "status": "ready", "archive": "unused.tar", "archive_sha256": "0" * 64}
    sources = tmp_path / "sources.json"
    write_new(sources, {"tasks": [source, dict(source)]})
    args.sources = sources
    args.output = tmp_path / "new-predictions"
    protocol = json.loads(runner.PROTOCOL.read_text())
    protocol["resources"] = {"per_task_timeout_seconds": 1}
    runner.PROTOCOL.write_text(json.dumps(protocol))
    monkeypatch.setattr(runner, "provenance", lambda _: {"synthetic": True})
    calls = []

    def fake_worker(*args, **kwargs):
        calls.append(True)
        return 1, b"", b"synthetic failure", {"failed": False, "exceeded": False}

    monkeypatch.setattr(runner, "run_worker", fake_worker)
    with pytest.raises(ValueError):
        runner.predict(args)
    assert calls == []
    assert not args.output.exists()


def test_review_archive_links_never_become_source_text(tmp_path):
    path = tmp_path / "source.tar"
    with tarfile.open(path, "w") as archive:
        regular = tarfile.TarInfo("root/a.py")
        body = b"raise RuntimeError('this source must never execute')\n"
        regular.size = len(body)
        archive.addfile(regular, io.BytesIO(body))
        for name, kind in [("root/symbolic.py", tarfile.SYMTYPE),
                           ("root/hard.py", tarfile.LNKTYPE)]:
            link = tarfile.TarInfo(name)
            link.type = kind
            link.linkname = "../../outside.py"
            archive.addfile(link)
    texts, metadata = archive_texts(path, sha256(path.read_bytes()))
    assert texts == {"a.py": body.decode()}
    assert metadata["source_files"] == 1
    assert metadata["skipped"]["nonregular_python"] == 2
    assert not (tmp_path / "root").exists()


def test_review_undecodable_source_counts_toward_resource_limit(tmp_path):
    path = tmp_path / "source.tar"
    with tarfile.open(path, "w") as archive:
        for name, body in [("root/a.py", b"\xff"), ("root/b.py", b"pass\n")]:
            member = tarfile.TarInfo(name)
            member.size = len(body)
            archive.addfile(member, io.BytesIO(body))
    with pytest.raises(ValueError, match="resource"):
        archive_texts(path, sha256(path.read_bytes()), max_files=1)


def test_review_summary_keeps_failed_repo_zero_and_no_target_missing():
    from benchmarks.external_context.analyze import summarize
    from benchmarks.external_context.scoring import overlap

    methods = ["bm25_windows", "bm25_declarations", "graph_expand"]
    task_info = [
        ("success", "r1", "predicted", False),
        ("failed", "r1", "failed", False),
        ("insertion", "r1", "predicted", True),
        ("all-failed-repo", "r2", "failed", False),
        ("bad-label", "r3", "predicted", False),
    ]
    protocol = {
        "study_id": "synthetic-summary", "methods": methods, "budgets": [100],
        "primary_budget": 100,
        "selection": {"tasks": [{"instance_id": name, "repo": repo}
                                 for name, repo, _, _ in task_info]},
    }
    tasks = []
    for name, repo, status, no_target in task_info:
        task = {"instance_id": name, "repo": repo, "prediction_status": status, "scores": []}
        if name == "bad-label":
            task.update(label_status="unsupported_or_invalid_diff", failure_category="bad_hunk")
        else:
            if status == "failed":
                task["failure_category"] = "timeout"
            for method in methods:
                hit = name == "success" and method == "graph_expand"
                predicted = {1} if hit else set()
                task["scores"].append({
                    "method": method, "budget": 100,
                    "line": overlap(predicted, set() if no_target else {1}),
                    "file": overlap(predicted, {1}),
                })
        tasks.append(task)
    result = summarize({"tasks": tasks}, protocol)
    first = next(c for c in result["per_repo"]
                 if c["repo"] == "r1" and c["method"] == "graph_expand")
    assert first["selected"] == 3
    assert first["prediction_failures"] == 1
    assert first["line"]["scorable"] == 2
    assert first["line"]["no_target"] == 1
    assert first["line"]["ite"]["f1"] == 0.5
    assert first["line"]["successful_prediction_only"]["f1"] == 1.0
    failed = next(c for c in result["per_repo"]
                  if c["repo"] == "r2" and c["method"] == "graph_expand")
    assert failed["line"]["ite"]["f1"] == 0.0
    assert failed["line"]["successful_prediction_only"]["f1"] is None
    macro = next(c for c in result["macro"] if c["method"] == "graph_expand")
    assert macro["line"]["scorable_repositories"] == 2
    assert macro["line"]["f1"] == 0.25
    assert result["selected_tasks"] == 5
    assert result["repositories"] == 3
    assert result["failure_categories"] == {"timeout": 2, "bad_hunk": 1}
    assert result["advance_to_confirmatory"] is False
    assert result["mature_research_established"] is False
