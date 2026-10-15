"""Release archives must not publish the machine identities found in raw builds."""

from datetime import datetime, timezone
import base64
import csv
import hashlib
import io
from pathlib import Path
import stat
import struct
import subprocess
import tarfile
import zipfile

import pytest

from scripts.build_release import (
    check_metadata, check_private_paths, normalize_sdist, normalize_wheel,
    retained_release_assets, validate_artifacts,
)
import scripts.build_release as release_build


ROOT = Path(__file__).resolve().parents[1]
EPOCH = 1700000000


def test_sdist_repack_removes_machine_identity_without_rewriting_licenses(tmp_path):
    payloads = {
        "contextproof/LICENSE": (ROOT / "LICENSE").read_bytes(),
        "contextproof/benchmarks/upstream/LICENSE":
            (ROOT / "benchmarks/downstream/upstream/LICENSE").read_bytes(),
        "contextproof/src/contextproof/__init__.py":
            (ROOT / "src/contextproof/__init__.py").read_bytes(),
    }
    normalized = []
    for number, owner in enumerate(("private-builder-a", "private-builder-b")):
        raw, checked = tmp_path / f"raw-{number}.tar.gz", tmp_path / f"checked-{number}.tar.gz"
        with tarfile.open(raw, "w:gz") as archive:
            for name, content in reversed(list(payloads.items())):
                entry = tarfile.TarInfo(name)
                entry.size = len(content)
                entry.uid = entry.gid = 501 + number
                entry.uname = entry.gname = owner
                entry.linkname = owner
                entry.mtime = EPOCH + number
                entry.pax_headers = {"comment": owner, "atime": str(EPOCH + number)}
                archive.addfile(entry, io.BytesIO(content))
        normalize_sdist(raw, checked, EPOCH)
        normalized.append(checked.read_bytes())
        with tarfile.open(checked) as archive:
            members = archive.getmembers()
            assert {member.name: archive.extractfile(member).read()
                    for member in members} == payloads
            assert all((member.uid, member.gid, member.uname, member.gname, member.mtime)
                       == (0, 0, "", "", EPOCH) for member in members)
            assert all(not member.pax_headers and not member.linkname for member in members)
    assert hashlib.sha256(normalized[0]).digest() == hashlib.sha256(normalized[1]).digest()


def test_wheel_repack_removes_zip_identity_and_preserves_executable_payload(tmp_path):
    outputs = []
    for number in range(2):
        raw, checked = tmp_path / f"raw-{number}.whl", tmp_path / f"checked-{number}.whl"
        with zipfile.ZipFile(raw, "w") as archive:
            entry = zipfile.ZipInfo("contextproof.data/scripts/tool", (2024 + number, 1, 1, 0, 0, 0))
            entry.external_attr = (stat.S_IFREG | 0o755) << 16
            entry.comment = b"private-builder"
            uid_extra = bytes([1, 4]) + struct.pack("<I", 501 + number)
            entry.extra = struct.pack("<HH", 0x7875, len(uid_extra)) + uid_extra
            archive.writestr(entry, b"#!/usr/bin/env python3\nprint('ready')\n")
        normalize_wheel(raw, checked, EPOCH)
        outputs.append(checked.read_bytes())
        with zipfile.ZipFile(checked) as archive:
            entry = archive.infolist()[0]
            assert not entry.extra and not entry.comment and not archive.comment
            assert entry.date_time == datetime.fromtimestamp(EPOCH, timezone.utc).timetuple()[:6]
            assert entry.external_attr >> 16 & 0o777 == 0o755
            assert archive.read(entry) == b"#!/usr/bin/env python3\nprint('ready')\n"
    assert outputs[0] == outputs[1]


def test_release_guards_reject_identity_metadata_and_embedded_home_paths():
    with pytest.raises(ValueError, match="public maintainer"):
        check_metadata(b"Name: contextproof\nVersion: 1.0.0\nAuthor: Private Builder\n",
                       "contextproof", "1.0.0")
    for parts in (("", "Users", "private-builder", "source.py"),
                  ("", "home", "private-builder", "source.py")):
        with pytest.raises(ValueError, match="personal home path"):
            check_private_paths("/".join(parts).encode())


LOCK = "benchmarks/semantic_observer/inputs/owned/requirements-full-sha256.lock"
INDEX = "benchmarks/semantic_observer/results/owned/INDEX.json"


def owned_checkout(tmp_path):
    """A real tiny Git inventory, not the project's research input / 自编 Git 夹具。"""
    source = tmp_path / "source"
    source.mkdir()
    assets = {
        "README.md": b"# Owned reproduction\n",
        "README_zh.md": "# 自编复现夹具\n".encode(),
        "docs/en/SEMANTIC_OBSERVER.md": b"# Scope\nNegative results stay retained.\n",
        "docs/zh/SEMANTIC_OBSERVER.md": "# 范围\n保留负面结果。\n".encode(),
        "benchmarks/semantic_observer/inputs/owned/specification.json": b'{"tasks":1}\n',
        LOCK: b"owned-package==1.0 --hash=sha256:" + b"a" * 64 + b"\n",
        "benchmarks/semantic_observer/PROTOCOL.md": b"# Owned protocol\n",
        "benchmarks/semantic_observer/runner.py": b'"""Owned archive payload only."""\n',
        INDEX: b'{"schema_version":1,"fixture":true}\n',
        "benchmarks/semantic_observer/results/owned/task-000.json": b'{"qualified":false}\n',
        "benchmarks/semantic_observer/results/owned/REPORT.md": b"# Negative fixture\n",
        "benchmarks/semantic_observer/results/owned/REPORT_zh.md": "# 负面夹具\n".encode(),
    }
    for name, raw in assets.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    (source / "LICENSE").write_bytes((ROOT / "LICENSE").read_bytes())
    (source / "pyproject.toml").write_text(
        '[project]\nname="contextproof"\nversion="1.0.0"\n'
        'authors=[{name="hardwork-xu"}]\n')
    subprocess.run(["git", "init", "-q", str(source)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(source), "add", "."], check=True, capture_output=True)
    return source, assets


def owned_archives(directory, assets):
    """Write small actual archives with valid RECORD and metadata / 真实小型归档。"""
    directory.mkdir(parents=True, exist_ok=True)
    license_bytes = (ROOT / "LICENSE").read_bytes()
    metadata = (b"Metadata-Version: 2.4\nName: contextproof\nVersion: 1.0.0\n"
                b"Author: hardwork-xu\n\nOwned fixture.\n")
    info = "contextproof-1.0.0.dist-info/"
    payloads = {info + "METADATA": metadata, info + "licenses/LICENSE": license_bytes,
        info + "WHEEL": b"Wheel-Version: 1.0\nGenerator: owned-fixture\nTag: py3-none-any\n"}
    records = io.StringIO(newline="")
    writer = csv.writer(records)
    for name, raw in payloads.items():
        integrity = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
        writer.writerow([name, "sha256=" + integrity, str(len(raw))])
    writer.writerow([info + "RECORD", "", ""])
    payloads[info + "RECORD"] = records.getvalue().encode()
    wheel = directory / "contextproof-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, raw in payloads.items():
            archive.writestr(name, raw)
    sdist = directory / "contextproof-1.0.0.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        for name, raw in {"LICENSE": license_bytes, "PKG-INFO": metadata, **assets}.items():
            entry = tarfile.TarInfo("contextproof-1.0.0/" + name)
            entry.size = len(raw)
            entry.mtime = EPOCH
            archive.addfile(entry, io.BytesIO(raw))
    return wheel, sdist


def test_tracked_release_inventory_keeps_locks_results_and_bilingual_documents_only(tmp_path):
    source, assets = owned_checkout(tmp_path)
    untracked = source / "benchmarks/semantic_observer/inputs/owned/untracked-private.txt"
    untracked.write_bytes(b"must not define the tracked release inventory\n")
    assert retained_release_assets(source) == assets
    assert retained_release_assets(source)[LOCK] == assets[LOCK]


def test_actual_sdist_with_all_required_bytes_is_accepted(tmp_path):
    source, assets = owned_checkout(tmp_path)
    wheel, sdist = owned_archives(tmp_path / "artifacts", assets)
    assert validate_artifacts(wheel, sdist, {"name": "contextproof", "version": "1.0.0"},
        (source / "LICENSE").read_bytes(), EPOCH,
        release_assets=retained_release_assets(source)) == "owned-fixture"


@pytest.mark.parametrize("name,change", [
    (LOCK, "missing"), (LOCK, "bytes"), ("README_zh.md", "missing"),
    ("docs/en/SEMANTIC_OBSERVER.md", "bytes"),
    ("docs/zh/SEMANTIC_OBSERVER.md", "bytes"), (INDEX, "missing"),
    ("benchmarks/semantic_observer/results/owned/task-000.json", "bytes"),
    ("benchmarks/semantic_observer/results/owned/REPORT_zh.md", "missing"),
])
def test_actual_sdist_rejects_missing_or_changed_reproduction_payload(tmp_path, name, change):
    source, assets = owned_checkout(tmp_path)
    archive_assets = dict(assets)
    if change == "missing":
        del archive_assets[name]
    else:
        archive_assets[name] += b"changed archive bytes\n"
    wheel, sdist = owned_archives(tmp_path / "artifacts", archive_assets)
    with pytest.raises(ValueError, match="source reproduction asset missing/changed") as error:
        validate_artifacts(wheel, sdist, {"name": "contextproof", "version": "1.0.0"},
            (source / "LICENSE").read_bytes(), EPOCH,
            release_assets=retained_release_assets(source))
    assert name in str(error.value)


def test_release_inventory_rejects_parent_repository_and_missing_tracked_file(tmp_path):
    source, _ = owned_checkout(tmp_path)
    nested = source / "nested"
    nested.mkdir()
    with pytest.raises(ValueError, match="exact Git source root"):
        retained_release_assets(nested)
    (source / LOCK).unlink()
    with pytest.raises(ValueError, match="missing or linked"):
        retained_release_assets(source)


def test_release_inventory_rejects_tracked_symlink_instead_of_reading_external_bytes(tmp_path):
    source, _ = owned_checkout(tmp_path)
    external = tmp_path / "external-owned.md"
    external.write_bytes(b"owned external fixture\n")
    path = source / "docs/zh/linked.md"
    path.symlink_to(external)
    subprocess.run(["git", "-C", str(source), "add", "docs/zh/linked.md"],
                   check=True, capture_output=True)
    with pytest.raises(ValueError, match="missing or linked"):
        retained_release_assets(source)


@pytest.mark.parametrize("changed_source", [False, True])
def test_release_entrypoint_enforces_assets_before_copying_any_output(tmp_path, monkeypatch,
                                                                    changed_source):
    source, assets = owned_checkout(tmp_path)
    real_run = subprocess.run
    def reviewed_frontend(command, **kwargs):
        if command[:3] == [release_build.sys.executable, "-m", "build"]:
            raw = Path(command[command.index("--outdir") + 1])
            incomplete = dict(assets)
            del incomplete[LOCK]
            owned_archives(raw, incomplete)
            if changed_source:
                (source / LOCK).write_bytes(assets[LOCK] + b"source drift\n")
            return subprocess.CompletedProcess(command, 0)
        return real_run(command, **kwargs)
    monkeypatch.setattr(release_build.subprocess, "run", reviewed_frontend)
    output = tmp_path / "release"
    expected = "changed during the build" if changed_source else "source reproduction asset missing/changed"
    with pytest.raises(ValueError, match=expected):
        release_build.build_release(source, output, EPOCH, no_isolation=True)
    assert not output.exists()
