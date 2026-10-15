"""Offline input construction and counterexamples / 离线输入构造与反例。"""

import io
import json
from pathlib import Path
import shutil
import sys
import tarfile
import zipfile

import pytest

from benchmarks.semantic_observer import prepare as p


ASSETS = (
    Path(__file__).resolve().parents[1]
    / "benchmarks/semantic_observer/inputs/prospective8-20261015"
)
SPEC_SHA = "af1ca2c413cde8dfac13ce216943603934574c4b9c7ea6f91eaa37ef38d5f265"
INDEX_SHA = "0ab9b99349c561e7822aa3785f1b5d674d72bfa4c6f9fc89bdc1d11a753ed363"


def records(files):
    return [
        {"path": name, "sha256": p.digest(raw), "bytes": len(raw)}
        for name, raw in sorted(files.items())
    ]


def tar_bytes(entries):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as out:
        for name, raw in entries:
            item = tarfile.TarInfo(name)
            if raw is None:
                item.type = tarfile.SYMTYPE
                item.linkname = "../../outside"
                out.addfile(item)
            elif raw is Ellipsis:
                item.type = tarfile.DIRTYPE
                out.addfile(item)
            else:
                item.size = len(raw)
                out.addfile(item, io.BytesIO(raw))
    return stream.getvalue()


def write_json(path, value):
    raw = json.dumps(value).encode()
    path.write_bytes(raw)
    return p.digest(raw)


@pytest.mark.parametrize(
    "name",
    [
        "",
        "../a",
        "a/../b",
        "/a",
        "a//b",
        "a/./b",
        "a\\b",
        "C:/a",
        "a/.git/config",
        "a/.GIT",
        "a\0b",
    ],
)
def test_unsafe_relative_paths_refused(name):
    with pytest.raises(ValueError, match="unsafe"):
        p.safe_relative(name)


def test_bounded_read_requests_only_limit_plus_one(tmp_path, monkeypatch):
    path = tmp_path / "input"
    path.write_bytes(b"original")
    reads = []
    original_open = Path.open

    class Limited(io.BytesIO):
        def read(self, size=-1):
            reads.append(size)
            assert size == 5
            return super().read(size)

    def open_hook(target, *args, **kwargs):
        if target == path:
            return Limited(b"x" * 100)
        return original_open(target, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_hook)
    with pytest.raises(ValueError, match="size/hash"):
        p.read_verified(path, p.digest(b"x" * 100), limit=4)
    assert reads == [5]


def test_verified_bytes_survive_source_replacement(tmp_path):
    path = tmp_path / "input.json"
    original = b'{"value":1}'
    path.write_bytes(original)
    verified = p.read_verified(path, p.digest(original))
    path.write_bytes(b'{"value":2}')
    assert p.parse_json(verified) == {"value": 1}
    assert p.digest(verified) == p.digest(original)
    assert path.read_bytes() != verified


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'{"a":1e999}'])
def test_ambiguous_or_nonfinite_json_refused(raw):
    with pytest.raises(ValueError):
        p.parse_json(raw)


@pytest.mark.parametrize(
    "kind",
    [
        "traversal",
        "symlink",
        "duplicate",
        "duplicate_root",
        "multiple_roots",
        "missing",
        "hash",
        "size",
        "expansion",
    ],
)
def test_archive_failures_retain_exact_file_set(kind):
    data = {"module.py": b"raise RuntimeError('data only')\n"}
    expected = p.file_index(records(data))
    entries = [("root", Ellipsis), ("root/module.py", data["module.py"])]
    kwargs = {}
    if kind == "traversal":
        entries += [("root/../escape", b"x")]
    elif kind == "symlink":
        entries += [("root/link", None)]
    elif kind == "duplicate":
        entries += [entries[-1]]
    elif kind == "duplicate_root":
        entries += [entries[0]]
    elif kind == "multiple_roots":
        entries += [("other/a", b"x")]
    elif kind == "missing":
        entries = entries[:1]
    elif kind == "hash":
        expected["module.py"]["sha256"] = "0" * 64
    elif kind == "size":
        expected["module.py"]["bytes"] += 1
    else:
        kwargs["max_tar_bytes"] = 128
    with pytest.raises(ValueError):
        p.extract_archive(tar_bytes(entries), expected, **kwargs)


def test_exact_archive_and_whole_test_overlay_do_not_execute_source():
    base = {
        "module.py": b"raise RuntimeError('base source never executes')\n",
        "tests/test_owned.py": b"assert False\n",
    }
    fixed = {
        **base,
        "module.py": b"raise RuntimeError('fixed source never executes')\n",
        "tests/test_owned.py": b"raise RuntimeError('original test is data here')\n",
    }
    expected = p.file_index(records(base))
    assert (
        p.extract_archive(tar_bytes([("root/" + k, v) for k, v in base.items()]), expected) == base
    )
    tests = p.file_index(records({"tests/test_owned.py": fixed["tests/test_owned.py"]}))
    overlay = [
        {
            "path": "tests/test_owned.py",
            "base_sha256_or_null": p.digest(base["tests/test_owned.py"]),
            "fixed_sha256_or_null": tests["tests/test_owned.py"]["sha256"],
            "fixed_bytes_or_null": len(fixed["tests/test_owned.py"]),
        }
    ]
    result = p.overlay_tests(base, fixed, overlay, tests)
    assert result["module.py"] == base["module.py"]
    assert result["tests/test_owned.py"] == fixed["tests/test_owned.py"]
    assert base["tests/test_owned.py"] == b"assert False\n"
    overlay[0]["path"] = "module.py"
    with pytest.raises(ValueError, match="production overlay"):
        p.overlay_tests(base, fixed, overlay, tests)


def test_output_in_git_or_through_asset_symlink_refused(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / ".git").write_text("gitdir: elsewhere")
    with pytest.raises(ValueError, match="outside Git"):
        p.outside_git(repository / "private")
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "link").symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        p.asset(tmp_path, "link/input")


def test_exact_cache_lookup_is_offline_and_checks_bytes(tmp_path, monkeypatch):
    raw = b"reviewed artifact data"
    record = {
        "filename": "owned-1-py3-none-any.whl",
        "url": "https://files.pythonhosted.org/a/owned.whl",
        "sha256": p.digest(raw),
        "bytes": len(raw),
    }
    directory = tmp_path / "dependencies/wheelhouse-final"
    directory.mkdir(parents=True)
    target = directory / record["filename"]
    target.write_bytes(raw)
    monkeypatch.setattr(
        p.urllib.request, "urlopen", lambda *a, **kw: pytest.fail("network attempted")
    )
    assert p.cached_artifact(tmp_path, record, kind="wheel", offline=True) == raw
    target.write_bytes(b"wrong")
    with pytest.raises(ValueError, match="size/hash"):
        p.cached_artifact(tmp_path, record, kind="wheel", offline=True)
    target.unlink()
    with pytest.raises(ValueError, match="offline cache"):
        p.cached_artifact(tmp_path, record, kind="wheel", offline=True)


@pytest.mark.parametrize(
    "url",
    [
        "http://files.pythonhosted.org/a.whl",
        "https://evil.test/a.whl",
        "https://user:secret@files.pythonhosted.org/a.whl",
        "https://files.pythonhosted.org/a.whl?token=secret",
    ],
)
def test_unreviewed_artifact_origins_refused(url):
    with pytest.raises(ValueError, match="URL"):
        p.validate_url(url, "wheel")


def make_wheel(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
    return stream.getvalue()


def test_wheel_full_identity_and_reviewed_startup_hook():
    files = {"module.py": b"raise RuntimeError('not imported')", "hook.pth": b"import module\n"}
    metadata = {"wheel_record_inventory": records(files)}
    record = {"name": "owned", "version": "1"}
    raw = make_wheel(files)
    with pytest.raises(ValueError, match="startup hook"):
        p.check_wheel(raw, record, metadata, [])
    hook = {
        "distribution": "owned",
        "version": "1",
        "path": "hook.pth",
        "sha256": p.digest(files["hook.pth"]),
        "related_module_path": "module.py",
        "related_module_sha256": p.digest(files["module.py"]),
    }
    p.check_wheel(raw, record, metadata, [hook])
    hook["related_module_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="shim"):
        p.check_wheel(raw, record, metadata, [hook])
    metadata["wheel_record_inventory"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="entry differs"):
        p.check_wheel(raw, record, metadata, [])


def test_public_asset_check_is_offline_and_binds_all_assets(monkeypatch):
    monkeypatch.setattr(
        p.urllib.request, "urlopen", lambda *a, **kw: pytest.fail("network attempted")
    )
    monkeypatch.setattr(p.subprocess, "run", lambda *a, **kw: pytest.fail("process attempted"))
    result = p.check_spec(ASSETS / "spec.json", SPEC_SHA, INDEX_SHA)
    assert result == {
        "status": "bound_input_assets_checked_not_execution",
        "tasks": 8,
        "roles": 16,
        "bound_assets": 86,
    }


@pytest.mark.parametrize("kind", ["missing", "extra", "changed", "symlink"])
def test_public_index_detects_missing_extra_changed_assets(tmp_path, kind):
    copied = tmp_path / "assets"
    shutil.copytree(ASSETS, copied)
    if kind == "missing":
        (copied / "REPRODUCING.md").unlink()
    elif kind == "extra":
        (copied / "unexpected").write_text("extra")
    elif kind == "changed":
        (copied / "REPRODUCING.md").write_text("changed")
    else:
        (copied / "unexpected").symlink_to(copied / "spec.json")
    with pytest.raises((ValueError, FileNotFoundError)):
        p.check_spec(copied / "spec.json", SPEC_SHA, INDEX_SHA)


def test_cli_asset_check_needs_no_output_or_subprocess(monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prepare",
            "--spec",
            str(ASSETS / "spec.json"),
            "--expected-spec-sha256",
            SPEC_SHA,
            "--check-spec",
            "--expected-index-sha256",
            INDEX_SHA,
        ],
    )
    monkeypatch.setattr(p.subprocess, "run", lambda *a, **kw: pytest.fail("process attempted"))
    p.main()
    assert json.loads(capsys.readouterr().out)["roles"] == 16


@pytest.fixture
def owned_input(tmp_path):
    assets = tmp_path / "assets"
    cache = tmp_path / "cache"
    assets.mkdir()
    cache.mkdir()
    base = {
        "module.py": b"raise RuntimeError('base is data')\n",
        "LICENSE": b"Owned test fixture.\n",
        "tests/test_owned.py": b"assert False\n",
    }
    fixed = {
        **base,
        "module.py": b"raise RuntimeError('fixed is data')\n",
        "tests/test_owned.py": b"raise RuntimeError('test is data')\n",
    }
    (assets / "LICENSE.txt").write_bytes(base["LICENSE"])
    version_rows = {}
    for label, commit, files in [("base", "a" * 40, base), ("fixed", "b" * 40, fixed)]:
        raw = tar_bytes([("root/" + k, v) for k, v in files.items()])
        archive_sha = p.digest(raw)
        (cache / (archive_sha + ".tar.gz")).write_bytes(raw)
        inv_sha = write_json(assets / (label + ".json"), {"files": records(files)})
        version_rows[label] = {
            "commit": commit,
            "archive_url": f"https://codeload.github.com/owned/source/tar.gz/{commit}",
            "archive_sha256": archive_sha,
            "archive_bytes": len(raw),
            "inventory_path": label + ".json",
            "inventory_sha256": inv_sha,
            "file_count": len(files),
            "expanded_bytes": sum(map(len, files.values())),
            "root_licenses": [
                {
                    "path": "LICENSE.txt",
                    "upstream_path": "LICENSE",
                    "sha256": p.digest(base["LICENSE"]),
                    "bytes": len(base["LICENSE"]),
                }
            ],
        }
    tests = records({"tests/test_owned.py": fixed["tests/test_owned.py"]})
    roles = []
    for label, files in [
        ("base_tests", {**base, "tests/test_owned.py": fixed["tests/test_owned.py"]}),
        ("fixed_tests", fixed),
    ]:
        rows = records(files)
        inv_sha = write_json(assets / (label + ".json"), {"files": rows})
        roles.append(
            {
                "role": label,
                "inventory_path": label + ".json",
                "inventory_sha256": inv_sha,
                "source_files_index_sha256": p.digest(p.canonical(rows)),
                "generated_metadata_or_null": None,
                "config_template": {
                    "task_id": "owned-01",
                    "role": label,
                    "production_paths": ["module.py"],
                    "production_packages": ["module"],
                    "import_roots": ["."],
                    "test_files": ["tests/test_owned.py"],
                    "dependency_versions": {},
                    "pytest_plugins": [],
                    "pytest_warning_filters": [],
                },
            }
        )
    (assets / "requirements.lock").write_bytes(b"\n")
    spec = {
        "schema_version": 1,
        "all_selected_count": 1,
        "source_roles_count": 2,
        "dependencies": [],
        "reviewed_startup_hooks": [],
        "runtime_reference": {
            "machine": "arm64",
            "ssl": "reference SSL",
            "binary_sha256": "0" * 64,
        },
        "full_hashlock_path": "requirements.lock",
        "full_hashlock_sha256": p.digest(b"\n"),
        "tasks": [
            {
                "task_id": "owned-01",
                "repository": "owned/source",
                "source_versions": version_rows,
                "original_fixed_tests": tests,
                "roles": roles,
                "test_overlay": [
                    {
                        "path": tests[0]["path"],
                        "base_sha256_or_null": p.digest(base[tests[0]["path"]]),
                        "fixed_sha256_or_null": tests[0]["sha256"],
                        "fixed_bytes_or_null": tests[0]["bytes"],
                    }
                ],
            }
        ],
    }
    sha = write_json(assets / "spec.json", spec)
    return assets / "spec.json", sha, cache, base, fixed


def test_full_owned_preparation_preserves_source_and_declares_runtime_deviation(
    owned_input, tmp_path, monkeypatch
):
    spec_path, sha, cache, base, fixed = owned_input
    output = tmp_path / "prepared"
    commands = []

    def command(args, root, label, env):
        commands.append(args)
        assert env["PIP_CONFIG_FILE"] == p.os.devnull
        assert env["PYTHONDONTWRITEBYTECODE"] == "1"
        if label == "python-probe":
            return b'{"implementation":"CPython","version":[3,12,2]}'
        if label == "venv":
            binary = output / "venv/bin/python"
            binary.parent.mkdir(parents=True)
            binary.symlink_to(sys.executable)
        if label == "runtime":
            return b'{"dependencies":{},"machine":"x86_64","system":"Linux","ssl":"other SSL"}'
        return b""

    monkeypatch.setattr(p, "command", command)
    monkeypatch.setattr(
        p.urllib.request, "urlopen", lambda *a, **kw: pytest.fail("network attempted")
    )
    manifest = p.prepare(spec_path, sha, output, cache=cache, offline=True)
    assert manifest["target_tests_executed"] is False
    assert manifest["SUT_imported"] is False
    assert json.loads((output / "runner-manifest.json").read_bytes()) == manifest
    roles = manifest["tasks"][0]["roles"]
    for role in roles:
        source = Path(role["config"]["source_root"])
        expected = base if role["role"] == "base_tests" else fixed
        assert (source / "module.py").read_bytes() == expected["module.py"]
        assert (source / "tests/test_owned.py").read_bytes() == fixed["tests/test_owned.py"]
        assert (source / "module.py").stat().st_mode & 0o777 == 0o444
        assert not (source / "__pycache__").exists()
    runtime = manifest["tasks"][0]["environment"]
    assert runtime["reference_runtime_deviation"] is True
    assert {"system", "machine", "ssl", "binary_sha256"} <= set(
        runtime["reference_identity_differences"]
    )
    install = next(args for args in commands if "install" in args)
    assert all(
        flag in install
        for flag in ["--no-index", "--require-hashes", "--no-deps", "--force-reinstall"]
    )
    assert all("pytest" not in args and "setup.py" not in args for args in commands)


def test_owned_preparation_failure_retains_partial_and_never_uses_existing_output(
    owned_input, tmp_path, monkeypatch
):
    spec_path, sha, cache, _, _ = owned_input
    output = tmp_path / "failed"
    monkeypatch.setattr(
        p, "command", lambda *args: b'{"implementation":"CPython","version":[3,11,9]}'
    )
    with pytest.raises(ValueError, match="CPython3.12"):
        p.prepare(spec_path, sha, output, cache=cache, offline=True)
    failure = json.loads((output / "PREPARATION_FAILED.json").read_bytes())
    assert failure["partial_outputs_retained"] is True
    assert failure["target_tests_executed"] is False
    assert (output / "sources/owned-01/base_tests/tests/test_owned.py").is_file()
    with pytest.raises(ValueError, match="existing preparation"):
        p.prepare(spec_path, sha, output, cache=cache, offline=True)
