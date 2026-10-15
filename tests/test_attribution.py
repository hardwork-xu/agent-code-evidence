"""Integrity failures must block source publication. 归属完整性失败须阻断源码发布。"""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("attribution_checker",
                                           ROOT / "scripts/check_attribution.py")
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


@pytest.fixture
def licenses(tmp_path):
    manifest = json.loads((ROOT / "third_party/manifest.json").read_text())
    for source in manifest["sources"]:
        for record in source["license_files"]:
            path = tmp_path / record["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / record["path"]).read_bytes())
    old = Path("benchmarks/downstream/upstream/LICENSE")
    (tmp_path / old).parent.mkdir(parents=True)
    (tmp_path / old).write_bytes((ROOT / old).read_bytes())
    return tmp_path, manifest, checker.source_pins(ROOT), checker.required_licenses(ROOT)


def test_complete_frozen_inventory_and_cli():
    result = checker.check(ROOT)
    assert result["projects"] == 14
    assert result["pinned_revisions"] == 42
    assert result["source_fragments"] > 1000
    assert result["adapted_probes"] == 30
    proc = subprocess.run([sys.executable, str(ROOT / "scripts/check_attribution.py")],
                          capture_output=True, text=True, check=True)
    assert json.loads(proc.stdout)["status"] == "passed"


def test_all_three_older_corpora_are_covered():
    pins = checker.source_pins(ROOT)
    projects = {v["project"] for v in pins.values()}
    assert {"click", "itsdangerous", "markupsafe", "babel", "dateutil", "filelock"} <= projects
    assert len([key for key in pins if key.startswith("requests@")]) == 7


def test_license_byte_change_is_detected(licenses):
    root, manifest, pins, required = licenses
    path = root / manifest["sources"][0]["license_files"][0]["path"]
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="license bytes changed"):
        checker.verify_licenses(root, manifest, pins, required)


def test_omitting_a_second_license_is_detected(licenses):
    root, manifest, pins, required = licenses
    packaging = next(s for s in manifest["sources"] if s["project"] == "packaging")
    packaging["license_files"] = [r for r in packaging["license_files"]
                                 if r["upstream_path"] != "LICENSE.BSD"]
    with pytest.raises(ValueError, match="required license files missing"):
        checker.verify_licenses(root, manifest, pins, required)


def test_omitting_an_entire_old_corpus_is_detected(licenses):
    root, manifest, pins, required = licenses
    manifest["sources"] = [s for s in manifest["sources"] if s["project"] != "click"]
    with pytest.raises(ValueError, match="uncovered corpus sources"):
        checker.verify_licenses(root, manifest, pins, required)


def test_current_manifest_cannot_override_frozen_license_hash(licenses):
    root, manifest, pins, required = licenses
    row = next(s for s in manifest["sources"] if s["project"] == "attrs")["license_files"][0]
    raw = (root / row["path"]).read_bytes() + b"\nmodified\n"
    (root / row["path"]).write_bytes(raw)
    row.update(sha256=checker.digest(raw), frozen_manifest_sha256=checker.digest(raw), bytes=len(raw))
    with pytest.raises(ValueError, match="historical hash"):
        checker.verify_licenses(root, manifest, pins, required)


def test_unpinned_url_is_detected(licenses):
    root, manifest, pins, required = licenses
    source = manifest["sources"][0]
    source["license_files"][0]["url"] = source["license_files"][0]["url"].replace(
        source["commit"], "main")
    with pytest.raises(ValueError, match="URL is not pinned"):
        checker.verify_licenses(root, manifest, pins, required)


def test_missing_license_body_is_detected(licenses):
    root, manifest, pins, required = licenses
    row = manifest["sources"][0]["license_files"][0]
    (root / row["path"]).unlink()
    with pytest.raises(FileNotFoundError):
        checker.verify_licenses(root, manifest, pins, required)


@pytest.mark.parametrize("path", ["../license", "/tmp/license", "licenses/../../secret",
                                 "licenses\\..\\secret"])
def test_paths_cannot_escape(tmp_path, path):
    with pytest.raises(ValueError, match="unsafe attribution path"):
        checker.safe_path(tmp_path, path)


def test_symlink_license_is_rejected(tmp_path):
    (tmp_path / "target").write_text("a body")
    (tmp_path / "license").symlink_to(tmp_path / "target")
    with pytest.raises(ValueError, match="symlink"):
        checker.safe_path(tmp_path, "license")


def test_unknown_renderer_is_not_silently_skipped():
    with pytest.raises(ValueError, match="unreviewed context condition"):
        checker.context_fragments("{}", "new_context_backend")


def test_fragment_range_is_validated(tmp_path):
    rec = {"path": "src/core.py", "start_line": 10, "end_line": 2, "text": "source"}
    with pytest.raises(ValueError, match="invalid upstream line range"):
        checker.fragment(tmp_path, "example@abc", rec, "contexts#/0", {})


def test_changed_study_bytes_require_review(monkeypatch):
    inventory = checker.make_inventory(ROOT, checker.source_pins(ROOT))
    changed = deepcopy(inventory)
    changed["artifacts"][0]["sha256"] = "0" * 64
    monkeypatch.setattr(checker, "make_inventory", lambda root, pins: changed)
    with pytest.raises(ValueError, match="inventory differs"):
        checker.check(ROOT)


@pytest.fixture
def metadata_corpus(tmp_path):
    directory = tmp_path / "benchmarks/selective_reuse"
    directory.mkdir(parents=True)
    commit = "a" * 40
    protocol = {"natural": {"repositories": ["example/project"], "versions": 1}}
    protocol_raw = json.dumps(protocol).encode()
    (directory / "protocol.json").write_bytes(protocol_raw)
    local = f"benchmarks/selective_reuse/licenses/example--project/{commit}/LICENSE"
    body = (ROOT / "LICENSE").read_bytes()
    (tmp_path / local).parent.mkdir(parents=True)
    (tmp_path / local).write_bytes(body)
    manifest = {"protocol_sha256": checker.digest(protocol_raw), "sources_frozen_at_utc": "fixed",
                "repositories": [{"repository": "example/project", "versions": [{
                    "commit": commit, "archive_sha256": "b" * 64, "parents": ["f" * 40],
                    "archive_url": f"https://codeload.github.com/example/project/tar.gz/{commit}",
                    "files": {"module.py": "c" * 64},
                    "licenses": [{"path": "LICENSE", "local": local,
                                  "sha256": checker.digest(body)}]}],
                    "anchors": [{"path": "module.py", "file_sha256": "c" * 64,
                                 "start_line": 1, "end_line": 3}]}]}
    (directory / "natural-manifest.json").write_text(json.dumps(manifest))
    return tmp_path, directory, local


def test_metadata_only_corpus_is_verified_without_freezing_timing_results(metadata_corpus):
    root, directory, _ = metadata_corpus
    (directory / "replay.json").write_text(json.dumps({"graph_sha256": "d" * 64,
                                                      "elapsed_ns": [200, 300]}))
    assert checker.check_metadata_corpus(root)["license_files"] == 1
    (directory / "replay.json").write_text(json.dumps({"graph_sha256": "d" * 64,
                                                      "elapsed_ns": [400, 500]}))
    assert checker.check_metadata_corpus(root)["status"] == "passed"


def test_metadata_only_scope_rejects_source_bodies(metadata_corpus):
    root, directory, _ = metadata_corpus
    (directory / "replay.json").write_text(json.dumps({"nodes": [{"text": "return 1"}]}))
    with pytest.raises(ValueError, match="source body in metadata-only"):
        checker.check_metadata_corpus(root)


def test_metadata_only_scope_rejects_encoded_source_body(metadata_corpus):
    root, directory, _ = metadata_corpus
    (directory / "replay.json").write_text(json.dumps({"payload": '{"text":"return 1"}'}))
    with pytest.raises(ValueError, match="source body in metadata-only"):
        checker.check_metadata_corpus(root)


def test_metadata_only_scope_requires_license_bytes(metadata_corpus):
    root, _, local = metadata_corpus
    (root / local).write_text("license checksum only")
    with pytest.raises(ValueError, match="metadata license bytes changed"):
        checker.check_metadata_corpus(root)


def test_metadata_protocol_change_requires_explicit_review(metadata_corpus):
    root, directory, _ = metadata_corpus
    path = directory / "protocol.json"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="protocol hash differs"):
        checker.check_metadata_corpus(root)


def test_unknown_metadata_artifact_requires_review(metadata_corpus):
    root, directory, _ = metadata_corpus
    (directory / "downloaded.py").write_text("upstream source could be here")
    with pytest.raises(ValueError, match="unreviewed file"):
        checker.check_metadata_corpus(root)


def test_historical_noncontiguous_spans_remain_visible():
    inv = checker.make_inventory(ROOT, checker.source_pins(ROOT))
    defects = [r for r in inv["source_fragments"]
               if r["span_status"] == "historical-noncontiguous-module-excerpt"]
    assert len(defects) == 17
    assert all("#L" not in row["url"] for row in defects)
    assert all(row["matched_nonempty_line_ranges"] for row in defects)


def test_documented_pre_measurement_protocol_lineage_is_explicit(metadata_corpus):
    root, directory, _ = metadata_corpus
    path = directory / "protocol.json"
    old_hash = checker.digest(path.read_bytes())
    protocol = json.loads(path.read_text())
    protocol["supersedes_protocol_sha256"] = [old_hash]
    protocol["amendments_before_primary"] = ["Documented baseline clarification before measurements."]
    path.write_text(json.dumps(protocol))
    result = checker.check_metadata_corpus(root)
    assert result["selection_protocol_sha256"] == old_hash
    assert result["protocol_match"].startswith("explicitly-superseded")


def test_broken_first_parent_chain_is_rejected(metadata_corpus):
    root, directory, _ = metadata_corpus
    manifest_path = directory / "natural-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["repositories"][0]["versions"][0]["parents"] = ["not-a-sha"]
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="parent hashes"):
        checker.check_metadata_corpus(root)


def test_source_verification_counts_cannot_hide_disclosed_defects(monkeypatch):
    original = checker.read_json

    def changed(root, path):
        value = original(root, path)
        if path == "third_party/source-verification.json":
            value["known_noncontiguous_span_defects"] = 0
        return value

    monkeypatch.setattr(checker, "read_json", changed)
    pins = checker.source_pins(ROOT)
    with pytest.raises(ValueError, match="verification counts"):
        checker.verify_source_report(ROOT, pins, checker.make_inventory(ROOT, pins))
