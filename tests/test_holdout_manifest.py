"""Source-only holdout integrity tests / 独立样本的源码完整性检验。"""
import io
import json
from pathlib import Path
import tarfile

import pytest

from scripts import prepare_incremental_holdout as holdout


def archive(tmp_path, members):
    path = tmp_path / "sources.tar.gz"
    with tarfile.open(path, "w:gz") as output:
        for name, raw in members:
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            output.addfile(member, io.BytesIO(raw))
    return path


def test_source_filtering_does_not_import_and_preserves_license_bytes(tmp_path):
    license_bytes = b"Copyright\r\nPermission is hereby granted\r\n"
    path = archive(tmp_path, [
        ("repo/LICENSE", license_bytes),
        ("repo/pkg/core.py", b"raise RuntimeError('must never execute')\ndef keep(): return 1\n"),
        ("repo/pkg/core.pyi", b"def hint() -> int: ...\n"),
        ("repo/pkg/tests/test_x.py", b"def no(): pass\n"),
        ("repo/pkg/_vendor/copied.py", b"def no(): pass\n"),
        ("repo/docs/example.py", b"def no(): pass\n"),
        ("repo/pkg/bad.py", b"\xff"),
    ])
    texts, licenses, excluded = holdout.read_sources(path, ["pkg/"])
    assert set(texts) == {"pkg/core.py", "pkg/core.pyi"}
    assert licenses == {"LICENSE": license_bytes}
    assert excluded == {"test_vendor_generated": 2, "outside_package": 1, "non_utf8": 1}
    assert {a["symbol"] for a in holdout.anchors_for(texts)} == {"keep", "hint"}


@pytest.mark.parametrize("members", [
    [("repo/../escape.py", b"def bad(): pass\n")],
    [("repo/LICENSE", b"license"), ("repo/pkg/x.py", b"a" * 33)],
    [("repo/LICENSE", b"one"), ("repo/LICENSE", b"two")],
])
def test_rejects_unsafe_oversized_and_duplicate_archive_inputs(tmp_path, members):
    with pytest.raises(ValueError):
        holdout.read_sources(archive(tmp_path, members), ["pkg/"], max_file_bytes=32)


def test_anchor_deduplication_retains_ambiguous_source_and_parse_failures():
    source = "@decorate\ndef ambiguous(): return 1\ndef ambiguous(): return 2\nasync def other(): return 3\n"
    texts = {"pkg/a.py": source, "pkg/broken.py": "def broken(\n"}
    audit = {}
    selected = holdout.anchors_for(texts, audit=audit)
    assert len(selected) == 2
    ambiguous = next(a for a in selected if a["symbol"] == "ambiguous")
    assert ambiguous["start_line"] == 1
    assert "return 1" in ambiguous["text"]
    assert texts["pkg/a.py"] == source  # Selection cannot sanitize ambiguity away.
    assert audit == {"top_level_declarations": 3, "unique_identities": 2, "duplicate_declarations": 1,
                     "parse_failures": [{"path": "pkg/broken.py", "error_type": "SyntaxError"}]}
    assert [a["id"] for a in selected] == sorted(a["id"] for a in selected)


def miniature_manifest(tmp_path):
    raw = b"exact license bytes\r\n"
    (tmp_path / "LICENSE").write_bytes(raw)
    source = "def f(): return 1\n"
    anchor = {k: v for k, v in holdout.anchors_for({"pkg/x.py": source})[0].items() if k != "text"}
    versions = [{"commit": commit, "parents": [parent], "archive_sha256": "a" * 64,
                 "files": {"pkg/x.py": holdout.sha256(source)},
                 "licenses": [{"local": "LICENSE", "sha256": holdout.digest(raw)}]}
                for commit, parent in [("1" * 40, "0" * 40), ("2" * 40, "1" * 40)]]
    protocol = {"natural": {"repositories": ["owner/project"], "prefixes": {"owner/project": ["pkg/"]},
                            "excluded_development_repositories": ["old/project"], "versions": 2,
                            "anchors_per_repository": 1}}
    protocol_bytes = json.dumps(protocol).encode()
    manifest = {"protocol_sha256": holdout.digest(protocol_bytes), "sources_frozen_at_utc": "frozen",
                "repositories": [{"repository": "owner/project", "prefixes": ["pkg/"],
                                  "versions": versions, "anchors": [anchor]}]}
    return manifest, protocol, protocol_bytes


def test_frozen_manifest_checks_protocol_parent_anchor_and_license_integrity(tmp_path):
    manifest, protocol, raw = miniature_manifest(tmp_path)
    holdout.validate_manifest(manifest, protocol, protocol_bytes=raw, root=tmp_path)
    mutations = [
        lambda x: x.update(protocol_sha256="0" * 64),
        lambda x: x["repositories"][0]["versions"][1].update(parents=["9" * 40]),
        lambda x: x["repositories"][0]["anchors"][0].update(file_sha256="b" * 64),
        lambda x: x["repositories"][0]["versions"][0]["licenses"][0].update(local="../LICENSE"),
    ]
    for mutate in mutations:
        changed = json.loads(json.dumps(manifest))
        mutate(changed)
        with pytest.raises(ValueError):
            holdout.validate_manifest(changed, protocol, protocol_bytes=raw, root=tmp_path)
    (tmp_path / "LICENSE").write_bytes(b"changed")
    with pytest.raises(ValueError, match="license checksum"):
        holdout.validate_manifest(manifest, protocol, protocol_bytes=raw, root=tmp_path)


def test_source_loader_rejects_archive_and_source_checksum_drift(tmp_path):
    path = archive(tmp_path, [("repo/LICENSE", b"license"), ("repo/pkg/a.py", b"def f(): return 1\n")])
    repo = {"repository": "owner/project", "prefixes": ["pkg/"]}
    version = {"commit": "a" * 40, "archive_sha256": holdout.digest(path.read_bytes()),
               "files": {"pkg/a.py": holdout.sha256("def f(): return 1\n")}}
    path.rename(holdout.archive_path(tmp_path, repo, version))
    assert holdout.source_loader(tmp_path, repo, version)() == {"pkg/a.py": "def f(): return 1\n"}
    version["files"]["pkg/a.py"] = "b" * 64
    with pytest.raises(ValueError, match="source manifest"):
        holdout.source_loader(tmp_path, repo, version)()
    version["archive_sha256"] = "c" * 64
    with pytest.raises(ValueError, match="archive checksum"):
        holdout.source_loader(tmp_path, repo, version)()


def test_download_missing_frozen_archive_checks_bytes_before_publication(tmp_path, monkeypatch):
    repo = {"repository": "owner/project"}
    version = {"commit": "a" * 40, "archive_url": "https://codeload.github.com/owner/project/tar.gz/" + "a" * 40,
               "archive_sha256": holdout.digest(b"expected archive")}
    calls = []
    def fake_download(argv, **kwargs):
        calls.append(argv)
        Path(argv[argv.index("--output") + 1]).write_bytes(b"wrong archive")
    monkeypatch.setattr(holdout.subprocess, "run", fake_download)
    with pytest.raises(ValueError, match="downloaded archive checksum"):
        holdout.download_archive(tmp_path, repo, version, 1024)
    assert not holdout.archive_path(tmp_path, repo, version).exists()
    version["archive_sha256"] = holdout.digest(b"wrong archive")
    holdout.download_archive(tmp_path, repo, version, 1024)
    holdout.download_archive(tmp_path, repo, version, 1024)
    assert len(calls) == 2  # Existing pinned archives are reused, not repinned.
    assert calls[-1][-1] == version["archive_url"]


def test_baseline_amendment_requires_unchanged_initial_sources(tmp_path):
    manifest, protocol, initial_protocol = miniature_manifest(tmp_path)
    initial_manifest = json.dumps(manifest).encode()
    data = tmp_path / "benchmarks/incremental_holdout"
    data.mkdir(parents=True)
    (data / "initial-protocol.json").write_bytes(initial_protocol)
    (data / "initial-manifest.json").write_bytes(initial_manifest)
    protocol["supersedes_protocol_sha256"] = [holdout.digest(initial_protocol)]
    current_protocol = json.dumps(protocol).encode()
    manifest.update({"protocol_sha256": holdout.digest(current_protocol),
                     "initial_protocol_sha256": holdout.digest(initial_protocol),
                     "initial_manifest_sha256": holdout.digest(initial_manifest)})
    holdout.validate_manifest(manifest, protocol, protocol_bytes=current_protocol, root=tmp_path)
    manifest["repositories"][0]["anchors"][0]["symbol"] = "changed_after_freeze"
    with pytest.raises(ValueError, match="selection changed after baseline amendment"):
        holdout.validate_manifest(manifest, protocol, protocol_bytes=current_protocol, root=tmp_path)
