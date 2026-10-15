"""Reconstruct fixed inputs, never run upstream tests / 重建固定输入，不运行上游测试。

Requires an externally trusted spec SHA. Output and cache stay outside Git.
Only reviewed binary wheels are installed in a new private virtual environment;
upstream packages, setup scripts and original assertions are never executed here.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import ssl
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request
import zipfile

MAX_JSON = 16 * 1024**2
MAX_ARCHIVE = 30 * 1024**2
MAX_SOURCE = 100 * 1024**2
MAX_MEMBER = 10 * 1024**2
MAX_MEMBERS = 30000
MAX_WHEELS = 100 * 1024**2
MAX_ENV = 512 * 1024**2
SHA = re.compile(r"[0-9a-f]{64}\Z")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode()


def safe_relative(name):
    """Reject ambiguous/escaping identities / 拒绝越界和含糊路径。"""
    require(
        type(name) is str
        and name
        and "\\" not in name
        and ":" not in name
        and "\0" not in name
        and not name.startswith("/"),
        "unsafe relative path",
    )
    require(
        all(p not in {"", ".", ".."} and p.casefold() != ".git" for p in name.split("/")),
        "unsafe relative path component",
    )
    return PurePosixPath(name)


def read_verified(path, expected, limit=MAX_JSON, size=None):
    """Hash and parse the same bounded bytes / 核验同一份有界读取字节。"""
    require(type(expected) is str and SHA.fullmatch(expected), "invalid expected SHA")
    path = Path(path)
    require(not path.is_symlink(), "symlink input refused")
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    require(len(raw) <= limit and digest(raw) == expected, "input size/hash mismatch")
    if size is not None:
        require(type(size) is int and size >= 0 and len(raw) == size, "input bytes differ")
    return raw


def parse_json(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, "duplicate JSON key")
            out[key] = value
        return out

    def nonfinite(_):
        raise ValueError("nonfinite JSON value")

    def finite_float(value):
        result = float(value)
        require(math.isfinite(result), "nonfinite JSON value")
        return result

    return json.loads(
        raw, object_pairs_hook=pairs, parse_constant=nonfinite, parse_float=finite_float
    )


def asset(root, name):
    rel = safe_relative(name)
    target = root.joinpath(*rel.parts)
    cursor = root
    for part in rel.parts:
        cursor /= part
        require(not cursor.is_symlink(), "symlink asset refused")
    return target


def file_index(rows):
    result = {}
    total = 0
    for row in rows:
        require(set(row) == {"path", "sha256", "bytes"}, "file record schema differs")
        safe_relative(row["path"])
        require(
            row["path"] not in result
            and type(row["bytes"]) is int
            and 0 <= row["bytes"] <= MAX_MEMBER
            and type(row["sha256"]) is str
            and SHA.fullmatch(row["sha256"]),
            "duplicate/invalid file identity",
        )
        total += row["bytes"]
        result[row["path"]] = row
    require(len(result) <= MAX_MEMBERS and total <= MAX_SOURCE, "source inventory cap")
    return result


def outside_git(path):
    path = Path(path)
    require(not path.is_symlink(), "symlink destination/cache refused")
    resolved = path.resolve()
    require(
        not any((p / ".git").exists() for p in [resolved, *resolved.parents]),
        "prepared inputs must stay outside Git",
    )
    return resolved


def validate_url(url, kind, repository=None, commit=None):
    parsed = urllib.parse.urlsplit(url)
    require(
        parsed.scheme == "https"
        and parsed.username is None
        and parsed.password is None
        and parsed.port in {None, 443}
        and not parsed.query
        and not parsed.fragment,
        "unreviewed download URL",
    )
    if kind == "archive":
        require(
            parsed.hostname == "codeload.github.com"
            and parsed.path == f"/{repository}/tar.gz/{commit}",
            "nonofficial archive URL",
        )
    else:
        require(
            parsed.hostname == "files.pythonhosted.org" and parsed.path.endswith(".whl"),
            "nonofficial wheel URL",
        )
    return parsed.hostname


def cached_artifact(cache, record, *, kind, offline, ca_file=None, repository=None, commit=None):
    """Only fixed free official bytes, with normal TLS / 只取固定官方字节，保持TLS校验。"""
    url = record["archive_url"] if kind == "archive" else record["url"]
    expected = record["archive_sha256"] if kind == "archive" else record["sha256"]
    size = record["archive_bytes"] if kind == "archive" else record["bytes"]
    host = validate_url(url, kind, repository, commit)
    cap = MAX_ARCHIVE if kind == "archive" else MAX_WHEELS
    require(type(size) is int and 0 < size <= cap, "artifact byte cap")
    suffix = ".tar.gz" if kind == "archive" else ".whl"
    path = cache / (expected + suffix)
    candidates = [path]
    if kind == "archive":
        rel = Path(repository.replace("/", "--")) / commit / "source.tar.gz"
        candidates += [cache / rel, cache / "sources" / rel]
    else:
        safe_relative(record["filename"])
        candidates += [cache / record["filename"], cache / "downloads" / record["filename"]]
        candidates += [
            cache / "dependencies" / folder / record["filename"]
            for folder in ("downloads", "wheelhouse-final", "wheelhouse-v2", "wheelhouse")
        ]
    for candidate in candidates:
        candidate = asset(cache, candidate.relative_to(cache).as_posix())
        if candidate.exists():
            return read_verified(candidate, expected, cap, size)
    require(not offline, "pinned artifact missing from offline cache")
    context = ssl.create_default_context(cafile=ca_file)
    request = urllib.request.Request(url, headers={"User-Agent": "fixed-input-preparer"})
    with urllib.request.urlopen(request, context=context, timeout=90) as response:
        final = urllib.parse.urlsplit(response.url)
        require(
            final.scheme == "https"
            and final.hostname == host
            and final.username is None
            and final.password is None,
            "unreviewed download redirect",
        )
        raw = response.read(size + 1)
    require(len(raw) == size and digest(raw) == expected, "download size/hash mismatch")
    with path.open("xb") as handle:
        handle.write(raw)
    return raw


def extract_archive(raw, expected, *, max_tar_bytes=None):
    """Bound decompression before tar parsing; never tar.extract / 先限量解压，禁止直接解包。"""
    expected = file_index(list(expected.values()))
    cap = max_tar_bytes if max_tar_bytes is not None else MAX_SOURCE + MAX_MEMBERS * 1024 + 1024**2
    require(type(cap) is int and cap > 0, "invalid tar cap")
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as zipped:
        tar_bytes = zipped.read(cap + 1)
    require(len(tar_bytes) <= cap, "decompressed tar cap")
    found, seen, prefix = {}, set(), None
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as archive:
        for number, member in enumerate(archive, 1):
            require(number <= MAX_MEMBERS, "archive member cap")
            parts = safe_relative(member.name.rstrip("/")).parts
            if prefix is None:
                prefix = parts[0]
            require(parts[0] == prefix, "archive needs one source root")
            require(member.isdir() or member.isfile(), "nonregular source member")
            require(parts not in seen, "duplicate archive identity")
            seen.add(parts)
            if len(parts) == 1:
                require(member.isdir(), "archive root must be directory")
                continue
            name = "/".join(parts[1:])
            if member.isdir():
                continue
            require(
                name in expected and member.size == expected[name]["bytes"],
                "archive file set/size differs",
            )
            with archive.extractfile(member) as stream:
                value = stream.read(member.size + 1)
            require(
                len(value) == member.size and digest(value) == expected[name]["sha256"],
                "archive file bytes differ",
            )
            found[name] = value
    require(found.keys() == expected.keys(), "archive files missing")
    return found


def overlay_tests(base, fixed, entries, tests):
    """Copy exact upstream fixed tests, no synthesized expectations / 只覆盖原固定测试。"""
    result = dict(base)
    for row in entries:
        name = row["path"]
        safe_relative(name)
        require(
            name.startswith(("tests/", "test/")) or name in tests or name == "conftest.py",
            "production overlay refused",
        )
        for files, key in [(base, "base_sha256_or_null"), (fixed, "fixed_sha256_or_null")]:
            require(
                (digest(files[name]) if name in files else None) == row[key],
                "test overlay source identity differs",
            )
        if row["fixed_sha256_or_null"] is None:
            result.pop(name, None)
        else:
            require(len(fixed[name]) == row["fixed_bytes_or_null"], "test overlay size differs")
            result[name] = fixed[name]
    for row in tests.values():
        name = row["path"]
        require(
            name in result
            and name in fixed
            and result[name] == fixed[name]
            and digest(result[name]) == row["sha256"],
            "original test bytes not retained",
        )
    return result


def write_role(root, values, expected):
    require(values.keys() == expected.keys(), "role file set differs")
    root.mkdir(parents=True)
    for name, raw in values.items():
        require(
            digest(raw) == expected[name]["sha256"] and len(raw) == expected[name]["bytes"],
            "role bytes differ",
        )
        path = root.joinpath(*safe_relative(name).parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(raw)
        path.chmod(0o444)
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_dir():
            path.chmod(0o555)
    root.chmod(0o555)


def check_wheel(raw, record, metadata, hooks):
    """Check complete file/license identities and exact startup hooks / 校验完整库存与许可。"""
    expected = {r["path"]: r for r in metadata["wheel_record_inventory"]}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = [i for i in archive.infolist() if not i.is_dir()]
        require(
            len(infos) == len(expected) and sum(i.file_size for i in infos) <= MAX_ENV,
            "wheel expansion/file count cap",
        )
        seen = set()
        for item in infos:
            safe_relative(item.filename)
            require(
                item.filename not in seen
                and item.filename in expected
                and (item.external_attr >> 16) & 0o170000 != 0o120000,
                "duplicate/unsafe wheel member",
            )
            seen.add(item.filename)
            value = archive.read(item)
            require(
                len(value) == expected[item.filename]["bytes"]
                and digest(value) == expected[item.filename]["sha256"],
                "wheel entry differs",
            )
            if item.filename.endswith(".pth"):
                allowed = [
                    h
                    for h in hooks
                    if h["distribution"] == record["name"]
                    and h["version"] == record["version"]
                    and h["path"] == item.filename
                ]
                require(
                    len(allowed) == 1 and digest(value) == allowed[0]["sha256"],
                    "unreviewed wheel startup hook",
                )
                hook = allowed[0]
                require(
                    digest(archive.read(hook["related_module_path"]))
                    == hook["related_module_sha256"],
                    "startup shim bytes differ",
                )


def save_new(path, value):
    raw = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False).encode() + b"\n"
    with path.open("xb") as handle:
        handle.write(raw)
    return digest(raw)


def check_spec(spec_path, expected_sha, expected_index_sha=None):
    """Offline asset consistency only / 离线校验绑定资产，不下载、不安装或运行。"""
    spec_path = Path(spec_path)
    spec = parse_json(read_verified(spec_path, expected_sha))
    root = spec_path.resolve().parent
    require(
        spec["schema_version"] == 1
        and type(spec["all_selected_count"]) is int
        and 0 < spec["all_selected_count"] == len(spec["tasks"]) <= 64
        and len({t["task_id"] for t in spec["tasks"]}) == len(spec["tasks"]),
        "task denominator",
    )
    assets = set()

    def bound(record, path_key="path", sha_key="sha256", size_key="bytes", limit=MAX_JSON):
        name = record[path_key]
        value = read_verified(asset(root, name), record[sha_key], limit, record.get(size_key))
        assets.add(name)
        return value

    for task in spec["tasks"]:
        for version in task["source_versions"].values():
            validate_url(version["archive_url"], "archive", task["repository"], version["commit"])
            inv = parse_json(bound(version, "inventory_path", "inventory_sha256", "unused_size"))
            files = file_index(inv["files"])
            require(
                len(files) == version["file_count"]
                and sum(r["bytes"] for r in files.values()) == version["expanded_bytes"],
                "original source inventory totals differ",
            )
            for lic in version["root_licenses"]:
                bound(lic)
                require(
                    lic["upstream_path"] in files
                    and files[lic["upstream_path"]]["sha256"] == lic["sha256"],
                    "source/license binding differs",
                )
        require(
            len(task["roles"]) == 2
            and {r["role"] for r in task["roles"]} == {"base_tests", "fixed_tests"},
            "two exact roles required",
        )
        for role in task["roles"]:
            inv = parse_json(bound(role, "inventory_path", "inventory_sha256", "unused_size"))
            files = file_index(inv["files"])
            require(
                digest(canonical(inv["files"])) == role["source_files_index_sha256"],
                "role inventory commitment differs",
            )
            c = role["config_template"]
            require(
                c["task_id"] == task["task_id"]
                and c["role"] == role["role"]
                and c["pytest_plugins"] in ([], ["pytest_mock.plugin"])
                and c["pytest_warning_filters"] in ([], ["error"])
                and "selectors" not in c
                and "pytest_options" not in c,
                "unsupported scientific configuration",
            )
            for name in [*c["production_paths"], *c["test_files"]]:
                safe_relative(name)
                require(name in files and name.endswith(".py"), "unbound production/test path")
            require(
                not set(c["production_paths"]) & set(c["test_files"]), "test/production overlap"
            )
            for row in task["original_fixed_tests"]:
                require(files[row["path"]]["sha256"] == row["sha256"], "original tests differ")
            generated = role["generated_metadata_or_null"]
            if generated:
                bound(generated, "artifact_path")
                require(
                    files[generated["path"]]["sha256"] == generated["sha256"],
                    "generated artifact/inventory differs",
                )
                bound(generated, "backend_driver_path", "backend_driver_sha256", "unused_size")
    names = set()
    for dep in spec["dependencies"]:
        validate_url(dep["url"], "wheel")
        name = dep["name"].lower().replace("_", "-")
        require(name not in names, "duplicate dependency")
        names.add(name)
        parse_json(bound(dep, "metadata_path", "metadata_sha256", "unused_size"))
        require(dep["actual_license_files"], "actual dependency license required")
        for lic in dep["actual_license_files"]:
            bound(lic)
    lock = bound(spec, "full_hashlock_path", "full_hashlock_sha256", "unused_size")
    expected_lock = (
        "\n".join(
            f"{d['name']}=={d['version']} --hash=sha256:{d['sha256']}"
            for d in sorted(spec["dependencies"], key=lambda r: r["name"].lower())
        )
        + "\n"
    )
    require(lock == expected_lock.encode(), "full wheel lock differs")
    if expected_index_sha is not None:
        index = parse_json(read_verified(root / "INDEX.json", expected_index_sha))
        require(index["spec_sha256"] == expected_sha, "asset index/spec binding differs")
        seen = set()
        for row in index["files"]:
            require(row["path"] not in seen, "duplicate asset index path")
            seen.add(row["path"])
            bound(row)
        require(all(not p.is_symlink() for p in root.rglob("*")), "symlink asset tree")
        require(
            {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
            == {"INDEX.json", *seen},
            "unexpected/missing indexed asset",
        )
    return {
        "status": "bound_input_assets_checked_not_execution",
        "tasks": len(spec["tasks"]),
        "roles": sum(len(t["roles"]) for t in spec["tasks"]),
        "bound_assets": len(assets),
    }


def command(cmd, root, label, env):
    result = subprocess.run(cmd, capture_output=True, timeout=600, env=env)
    (root / (label + ".log")).write_bytes(result.stdout + result.stderr)
    require(result.returncode == 0, "dependency command failed: " + label)
    return result.stdout


def prepare(
    spec_path,
    expected_sha,
    output,
    *,
    cache=None,
    offline=False,
    python=sys.executable,
    ca_file=None,
    allow_runtime_deviation=False,
    expected_index_sha=None,
):
    """Produce private runner inputs only / 只生成私有运行输入，不执行SUT。"""
    spec_path = Path(spec_path)
    check_spec(spec_path, expected_sha, expected_index_sha)
    spec_raw = read_verified(spec_path, expected_sha)
    spec = parse_json(spec_raw)
    base = spec_path.resolve().parent
    require(
        spec["schema_version"] == 1
        and type(spec["all_selected_count"]) is int
        and spec["all_selected_count"] == len(spec["tasks"]) <= 64
        and len({t["task_id"] for t in spec["tasks"]}) == len(spec["tasks"]),
        "task denominator",
    )
    output = outside_git(output)
    require(not output.exists(), "refuse existing preparation output")
    output.mkdir(parents=True, mode=0o700)
    try:
        cache = outside_git(cache) if cache else output / "cache"
        cache.mkdir(parents=True, exist_ok=True)
        role_rows = []
        source_cache = {}
        for task in spec["tasks"]:
            require(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", task["task_id"]), "unsafe task id")
            require(re.fullmatch(r"[\w.-]+/[\w.-]+", task["repository"]), "unsafe repo id")
            versions = {}
            for name in ("base", "fixed"):
                v = task["source_versions"][name]
                require(re.fullmatch(r"[0-9a-f]{40}", v["commit"]), "invalid commit pin")
                inv = parse_json(
                    read_verified(asset(base, v["inventory_path"]), v["inventory_sha256"])
                )
                expected = file_index(inv["files"])
                key = task["repository"], v["commit"]
                if key not in source_cache:
                    raw = cached_artifact(
                        cache,
                        v,
                        kind="archive",
                        offline=offline,
                        ca_file=ca_file,
                        repository=key[0],
                        commit=key[1],
                    )
                    source_cache[key] = extract_archive(raw, expected)
                versions[name] = source_cache[key]
                for lic in v["root_licenses"]:
                    value = read_verified(
                        asset(base, lic["path"]), lic["sha256"], MAX_MEMBER, lic["bytes"]
                    )
                    require(value == versions[name][lic["upstream_path"]], "source license differs")
            tests = {t["path"]: t for t in task["original_fixed_tests"]}
            overlay = overlay_tests(
                versions["base"], versions["fixed"], task["test_overlay"], tests
            )
            require(
                {r["role"] for r in task["roles"]} == {"base_tests", "fixed_tests"}
                and len(task["roles"]) == 2,
                "two exact roles required",
            )
            for role in task["roles"]:
                config = dict(role["config_template"])
                require(
                    config["task_id"] == task["task_id"]
                    and config["role"] == role["role"]
                    and set(config["test_files"]) == set(tests)
                    and "selectors" not in config
                    and "pytest_options" not in config,
                    "scope/config differs",
                )
                values = dict(overlay if role["role"] == "base_tests" else versions["fixed"])
                generated = role["generated_metadata_or_null"]
                if generated:
                    safe_relative(generated["path"])
                    require(generated["path"] not in values, "generated file overwrites source")
                    values[generated["path"]] = read_verified(
                        asset(base, generated["artifact_path"]),
                        generated["sha256"],
                        MAX_MEMBER,
                        generated["bytes"],
                    )
                inv = parse_json(
                    read_verified(asset(base, role["inventory_path"]), role["inventory_sha256"])
                )
                expected = file_index(inv["files"])
                require(
                    digest(canonical(inv["files"])) == role["source_files_index_sha256"],
                    "role inventory commitment differs",
                )
                root = output / "sources" / task["task_id"] / role["role"]
                write_role(root, values, expected)
                config.update(
                    source_root=str(root),
                    source_files=inv["files"],
                    source_files_index_sha256=role["source_files_index_sha256"],
                    generated_packaging_metadata_or_null=generated,
                )
                role_rows.append((task["task_id"], role["role"], config))
        require(sum(d["bytes"] for d in spec["dependencies"]) <= MAX_WHEELS, "wheel download cap")
        wheelhouse = output / "wheelhouse"
        wheelhouse.mkdir()
        for row in spec["dependencies"]:
            require(
                Path(row["filename"]).name == row["filename"] and row["filename"].endswith(".whl"),
                "unsafe wheel filename",
            )
            raw = cached_artifact(cache, row, kind="wheel", offline=offline, ca_file=ca_file)
            metadata = parse_json(
                read_verified(asset(base, row["metadata_path"]), row["metadata_sha256"])
            )
            check_wheel(raw, row, metadata, spec["reviewed_startup_hooks"])
            for lic in row["actual_license_files"]:
                read_verified(asset(base, lic["path"]), lic["sha256"], MAX_MEMBER, lic["bytes"])
            (wheelhouse / row["filename"]).write_bytes(raw)
        lock = read_verified(asset(base, spec["full_hashlock_path"]), spec["full_hashlock_sha256"])
        expected_lock = (
            "\n".join(
                f"{d['name']}=={d['version']} --hash=sha256:{d['sha256']}"
                for d in sorted(spec["dependencies"], key=lambda r: r["name"].lower())
            )
            + "\n"
        )
        require(lock == expected_lock.encode(), "full wheel lock differs")
        lock_path = output / "requirements.lock"
        lock_path.write_bytes(lock)
        for name in ("home", "temporary", "pip-cache"):
            (output / name).mkdir()
        env = {
            "PATH": os.environ.get("PATH", os.defpath),
            "HOME": str(output / "home"),
            "TMPDIR": str(output / "temporary"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PIP_CONFIG_FILE": os.devnull,
        }
        if "SYSTEMROOT" in os.environ:
            env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
        probe = "import sys,platform,json;print(json.dumps({'version':list(sys.version_info[:3]),'implementation':platform.python_implementation()}))"
        identity = parse_json(
            command([str(python), "-I", "-B", "-c", probe], output, "python-probe", env)
        )
        require(
            identity["implementation"] == "CPython" and identity["version"][:2] == [3, 12],
            "CPython3.12 required",
        )
        require(
            identity["version"] == [3, 12, 2] or allow_runtime_deviation,
            "reference is CPython3.12.2; explicitly declare a patch-version deviation",
        )
        venv = output / "venv"
        command([str(python), "-I", "-B", "-m", "venv", str(venv)], output, "venv", env)
        target = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        command(
            [
                str(target),
                "-I",
                "-B",
                "-m",
                "pip",
                "--isolated",
                "install",
                "--no-index",
                "--find-links",
                str(wheelhouse),
                "--require-hashes",
                "--no-deps",
                "--no-compile",
                "--force-reinstall",
                "--disable-pip-version-check",
                "--cache-dir",
                str(output / "pip-cache"),
                "-r",
                str(lock_path),
            ],
            output,
            "offline-install",
            env,
        )
        command(
            [str(target), "-I", "-B", "-m", "pip", "--isolated", "check"], output, "pip-check", env
        )
        probe = "import sys,platform,ssl,importlib.metadata as m,json;print(json.dumps({'python':sys.version,'executable':sys.executable,'system':platform.system(),'machine':platform.machine(),'ssl':ssl.OPENSSL_VERSION,'dependencies':{d.metadata['Name']:d.version for d in m.distributions()}}))"
        runtime = parse_json(
            command([str(target), "-I", "-B", "-c", probe], output, "runtime", env)
        )

        def normalize(value):
            return value.lower().replace("_", "-")

        require(
            {normalize(k): v for k, v in runtime["dependencies"].items()}
            == {normalize(r["name"]): r["version"] for r in spec["dependencies"]},
            "installed dependency closure differs",
        )
        require(
            sum(p.stat().st_size for p in venv.rglob("*") if p.is_file() and not p.is_symlink())
            <= MAX_ENV,
            "environment byte cap",
        )
        runtime["binary_sha256"] = digest(target.resolve().read_bytes())
        reference = spec["runtime_reference"]
        comparisons = {
            "version": (identity["version"], [3, 12, 2]),
            "system": (runtime["system"], "Darwin"),
            "machine": (runtime["machine"], reference["machine"]),
            "ssl": (runtime["ssl"], reference["ssl"]),
            "binary_sha256": (runtime["binary_sha256"], reference["binary_sha256"]),
        }
        differences = {
            k: {"actual": a, "reference": b} for k, (a, b) in comparisons.items() if a != b
        }
        runtime.update(
            reference_runtime_deviation=bool(differences),
            reference_identity_differences=differences,
            wheel_lock_sha256=digest(lock),
            preparation_only=True,
        )
        tasks = []
        for source_task in spec["tasks"]:
            roles = []
            for task_id, role, config in role_rows:
                if task_id != source_task["task_id"]:
                    continue
                require(
                    {normalize(k): v for k, v in config["dependency_versions"].items()}
                    == {normalize(k): v for k, v in runtime["dependencies"].items()},
                    "frozen task dependencies differ",
                )
                config["python"] = str(target)
                roles.append({"role": role, "config": config})
            tasks.append(
                {
                    "task_id": source_task["task_id"],
                    "python": str(target),
                    "environment": runtime,
                    "roles": roles,
                }
            )
        manifest = {
            "schema_version": 1,
            "tasks": tasks,
            "all_selected_count": len(tasks),
            "source_spec_sha256": digest(spec_raw),
            "recorded_utc": datetime.now(timezone.utc).isoformat(),
            "classification": "reconstructed_inputs_not_SUT_execution",
            "target_tests_executed": False,
            "SUT_imported": False,
            "reference_primary_run_not_overwritten": True,
        }
        save_new(output / "runner-manifest.json", manifest)
        return manifest
    except Exception as error:
        save_new(
            output / "PREPARATION_FAILED.json",
            {
                "error_class": type(error).__name__,
                "reason": str(error),
                "target_tests_executed": False,
                "partial_outputs_retained": True,
            },
        )
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path, help="fixed public spec / 固定公开规范")
    parser.add_argument(
        "--expected-spec-sha256", required=True, help="trusted external SHA / 外部可信摘要"
    )
    parser.add_argument(
        "--output", type=Path, help="new private output outside Git / Git外新私有目录"
    )
    parser.add_argument(
        "--cache-directory",
        "--cache",
        dest="cache",
        type=Path,
        help="exact pinned artifact lookup outside Git; no recursive search / Git外精确缓存",
    )
    parser.add_argument(
        "--check-spec", action="store_true", help="offline asset check only / 仅离线校验资产"
    )
    parser.add_argument(
        "--expected-index-sha256", help="optional trusted whole-asset INDEX SHA / 可选资产目录摘要"
    )
    parser.add_argument(
        "--offline", action="store_true", help="use pinned cached bytes only / 仅用固定缓存"
    )
    parser.add_argument(
        "--python", default=sys.executable, help="reference CPython3.12.2 / 参考解释器"
    )
    parser.add_argument("--ca-file", help="legitimate TLS CA bundle / 合法TLS证书包")
    parser.add_argument(
        "--allow-runtime-deviation",
        action="store_true",
        help="record an unverified3.12 patch-version deviation / 记录未验证补丁版本偏离",
    )
    args = parser.parse_args()
    try:
        if args.check_spec:
            print(
                json.dumps(
                    check_spec(args.spec, args.expected_spec_sha256, args.expected_index_sha256)
                )
            )
            return
        if args.output is None:
            parser.error("--output is required unless --check-spec / 准备输入需要--output")
        result = prepare(
            args.spec,
            args.expected_spec_sha256,
            args.output,
            cache=args.cache,
            offline=args.offline,
            python=args.python,
            ca_file=args.ca_file,
            allow_runtime_deviation=args.allow_runtime_deviation,
            expected_index_sha=args.expected_index_sha256,
        )
    except (
        ValueError,
        OSError,
        subprocess.SubprocessError,
        EOFError,
        tarfile.TarError,
        zipfile.BadZipFile,
    ) as error:
        parser.exit(2, "Preparation failed / 准备失败: " + str(error) + "\n")
    print(
        json.dumps(
            {
                "status": "inputs_prepared_upstream_unrun",
                "tasks": len(result["tasks"]),
                "manifest": str(args.output / "runner-manifest.json"),
            }
        )
    )


if __name__ == "__main__":
    main()
