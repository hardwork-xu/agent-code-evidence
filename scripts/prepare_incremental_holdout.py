#!/usr/bin/env python3
"""Freeze source-only holdout data; never import or run the measured resolver.

冻结独立仓库源码、许可与锚点；不运行上游代码，也不查看图或计时结果。
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "benchmarks/incremental_holdout"
EXCLUDED_PARTS = {"test", "tests", "fixtures", "vendor", "vendored", "_vendor", "generated"}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sha256(text):
    return digest(text.encode("utf-8"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".pending")
    pending.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    pending.replace(path)


def api(route, cache):
    """Cache each public GitHub response before further dependent requests."""
    path = cache / "github-api" / (sha256(route) + ".json")
    if path.exists():
        record = json.loads(path.read_text())
        if record["route"] != route:
            raise ValueError("API cache identity mismatch")
        return record["response"]
    for attempt in range(4):
        try:
            result = subprocess.run(["gh", "api", route], capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            if attempt == 3:
                raise RuntimeError("GitHub request repeatedly timed out: " + route) from None
            continue
        if not result.returncode:
            response = json.loads(result.stdout)
            write(path, {"route": route, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                         "response": response})
            return response
        if attempt == 3:
            raise RuntimeError("GitHub read failed after retries: " + route)
    raise AssertionError("unreachable")


def pin_repository(repository, cache, protocol):
    meta = api("repos/" + repository, cache)
    release = api("repos/" + repository + "/releases/latest", cache)
    if meta["fork"] or meta["archived"] or release["draft"] or release["prerelease"]:
        raise ValueError("repository/release is ineligible: " + repository)
    license_id = (meta.get("license") or {}).get("spdx_id")
    if license_id not in {"MIT", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "ISC"}:
        raise ValueError("permissive license must be reviewed: " + repository)
    activity = datetime.fromisoformat(meta["pushed_at"].replace("Z", "+00:00"))
    cutoff = datetime.fromisoformat(protocol["date"]).replace(tzinfo=timezone.utc)
    if (cutoff - activity).days > 731:
        raise ValueError("upstream activity older than two years: " + repository)
    head = api(f"repos/{repository}/commits/{release['tag_name']}", cache)
    versions = []
    for index in range(protocol["natural"]["versions"]):
        versions.append({"commit": head["sha"], "date": head["commit"]["committer"]["date"],
                         "parents": [p["sha"] for p in head["parents"]],
                         "archive_url": f"https://codeload.github.com/{repository}/tar.gz/{head['sha']}"})
        if index + 1 < protocol["natural"]["versions"]:
            if not head["parents"]:
                raise ValueError("insufficient first-parent history")
            head = api(f"repos/{repository}/commits/{head['parents'][0]['sha']}", cache)
    return {"repository": repository, "prefixes": protocol["natural"]["prefixes"][repository],
            "selection_kind": "github-latest-stable-release", "tag": release["tag_name"],
            "release_url": release["html_url"], "release_published_at": release["published_at"],
            "repository_pushed_at": meta["pushed_at"], "repository_fork": meta["fork"],
            "repository_archived": meta["archived"], "license_spdx": license_id,
            "versions": list(reversed(versions))}


def archive_path(cache, repo, version):
    return cache / f"{repo['repository'].replace('/', '--')}--{version['commit']}.tar.gz"


def download_archive(cache, repo, version, max_archive_bytes):
    """Fetch missing pinned archives without reselecting the release/history."""
    cache.mkdir(parents=True, exist_ok=True)
    path = archive_path(cache, repo, version)
    if not path.exists():
        pending = path.with_suffix(".partial")
        subprocess.run(["curl", "-q", "-L", "--fail", "--silent", "--show-error", "--retry", "3",
                        "--max-time", "120", "--output", str(pending), version["archive_url"]],
                       check=True, timeout=500)
        if pending.stat().st_size > max_archive_bytes:
            raise ValueError("archive resource limit exceeded")
        if version.get("archive_sha256") and digest(pending.read_bytes()) != version["archive_sha256"]:
            raise ValueError("downloaded archive checksum mismatch")
        pending.replace(path)
    if path.stat().st_size > max_archive_bytes:
        raise ValueError("archive resource limit exceeded")


def read_sources(path, prefixes, *, max_file_bytes=2097152):
    texts, licenses, excluded = {}, {}, Counter()
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            parts = PurePosixPath(member.name)
            if parts.is_absolute() or ".." in parts.parts:
                raise ValueError("unsafe archive path")
            relative = "/".join(parts.parts[1:])
            if not member.isfile() or len(parts.parts) < 2:
                continue
            license_name = parts.name.lower().startswith(("license", "licence", "copying", "notice"))
            is_license = license_name and (len(parts.parts) == 2 or
                         any(relative.startswith(prefix) for prefix in prefixes) or
                         parts.parts[1].lower() in {"licenses", "license", "licences"})
            if member.size > max_file_bytes:
                if relative.endswith((".py", ".pyi")) or is_license:
                    raise ValueError("oversized source/license member: " + relative)
                continue
            if is_license:
                if relative in licenses:
                    raise ValueError("duplicate license path")
                licenses[relative] = archive.extractfile(member).read()
            if not relative.endswith((".py", ".pyi")):
                continue
            if not any(relative.startswith(prefix) for prefix in prefixes):
                excluded["outside_package"] += 1
                continue
            if any(part.lower() in EXCLUDED_PARTS for part in parts.parts[1:]) or parts.name.startswith("test_"):
                excluded["test_vendor_generated"] += 1
                continue
            raw = archive.extractfile(member).read()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                excluded["non_utf8"] += 1
                continue
            if relative in texts:
                raise ValueError("duplicate source path")
            texts[relative] = text
    if not texts or not licenses:
        raise ValueError("missing source or license")
    return texts, licenses, dict(excluded)


def anchors_for(texts, limit=24, *, audit=None):
    unique, failures, declarations = {}, [], 0
    for path, source in sorted(texts.items()):
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError, RecursionError) as error:
            failures.append({"path": path, "error_type": type(error).__name__})
            continue
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            declarations += 1
            start = min([node.lineno, *(item.lineno for item in node.decorator_list)])
            text = "".join(source.splitlines(keepends=True)[start - 1:node.end_lineno])
            key = sha256(path + ":" + node.name)
            unique.setdefault(key, {"id": key, "path": path, "symbol": node.name, "kind": "function",
                                    "start_line": start, "end_line": node.end_lineno, "text": text,
                                    "text_sha256": sha256(text), "file_sha256": sha256(source)})
    if audit is not None:
        audit.update({"top_level_declarations": declarations, "unique_identities": len(unique),
                      "duplicate_declarations": declarations - len(unique), "parse_failures": failures})
    return sorted(unique.values(), key=lambda anchor: anchor["id"])[:limit]


def validate_manifest(manifest, protocol, *, protocol_bytes=None, root=ROOT):
    raw = (DATA / "protocol.json").read_bytes() if protocol_bytes is None else protocol_bytes
    if manifest.get("protocol_sha256") != digest(raw) or not manifest.get("sources_frozen_at_utc"):
        raise ValueError("manifest/protocol not frozen together")
    if "initial_manifest_sha256" in manifest:
        initial_data = root / "benchmarks/incremental_holdout"
        initial_protocol = (initial_data / "initial-protocol.json").read_bytes()
        initial_manifest = (initial_data / "initial-manifest.json").read_bytes()
        if (digest(initial_protocol) != manifest.get("initial_protocol_sha256") or
                digest(initial_manifest) != manifest["initial_manifest_sha256"] or
                digest(initial_protocol) not in protocol.get("supersedes_protocol_sha256", [])):
            raise ValueError("initial protocol/manifest lineage mismatch")
        if json.loads(initial_manifest)["repositories"] != manifest["repositories"]:
            raise ValueError("source/anchor selection changed after baseline amendment")
    natural = protocol["natural"]
    repositories = manifest["repositories"]
    if [item["repository"] for item in repositories] != natural["repositories"]:
        raise ValueError("repository selection drift")
    excluded = {name.lower() for name in natural["excluded_development_repositories"]}
    if any(repo["repository"].lower() in excluded for repo in repositories):
        raise ValueError("development repository in holdout")
    for repo in repositories:
        if repo["prefixes"] != natural["prefixes"][repo["repository"]]:
            raise ValueError("source prefix drift")
        versions = repo["versions"]
        if len(versions) != natural["versions"] or len({v["commit"] for v in versions}) != len(versions):
            raise ValueError("incomplete/duplicated version sequence")
        for index, version in enumerate(versions):
            if index and version["parents"][0] != versions[index - 1]["commit"]:
                raise ValueError("broken first-parent chain")
            if not version.get("files") or len(version.get("archive_sha256", "")) != 64 or not version.get("licenses"):
                raise ValueError("missing source/license integrity metadata")
            for license_record in version["licenses"]:
                relative = PurePosixPath(license_record["local"])
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("unsafe license path")
                license_file = root / relative
                if digest(license_file.read_bytes()) != license_record["sha256"]:
                    raise ValueError("license checksum mismatch")
        anchors = repo["anchors"]
        if len(anchors) != natural["anchors_per_repository"] or len({a["id"] for a in anchors}) != len(anchors):
            raise ValueError("anchor count or uniqueness drift")
        if [a["id"] for a in anchors] != sorted(a["id"] for a in anchors):
            raise ValueError("anchor order drift")
        for anchor in anchors:
            if (anchor["id"] != sha256(anchor["path"] + ":" + anchor["symbol"]) or
                    anchor["file_sha256"] != versions[0]["files"].get(anchor["path"]) or
                    anchor["kind"] != "function" or
                    type(anchor["start_line"]) is not int or type(anchor["end_line"]) is not int or
                    not 1 <= anchor["start_line"] <= anchor["end_line"] or len(anchor["text_sha256"]) != 64):
                raise ValueError("anchor metadata drift")


def source_loader(cache, repo, version):
    path = archive_path(cache, repo, version)
    def load():
        if digest(path.read_bytes()) != version["archive_sha256"]:
            raise ValueError("source archive checksum mismatch")
        texts, _, _ = read_sources(path, repo["prefixes"])
        if {p: sha256(s) for p, s in texts.items()} != version["files"]:
            raise ValueError("source manifest mismatch")
        return texts
    return load


def prepare(cache):
    protocol_bytes = (DATA / "protocol.json").read_bytes()
    protocol = json.loads(protocol_bytes)
    manifest_path = DATA / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest["protocol_sha256"] != digest(protocol_bytes):
            raise ValueError("protocol changed: preserve old manifest and document amendment")
        if manifest.get("sources_frozen_at_utc"):
            validate_manifest(manifest, protocol)
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda item: download_archive(
                    cache, *item, protocol["natural"]["resource_limits"]["max_archive_bytes"]),
                    [(repo, version) for repo in manifest["repositories"] for version in repo["versions"]]))
            for repo in manifest["repositories"]:
                first = None
                for version in repo["versions"]:
                    texts = source_loader(cache, repo, version)()
                    first = texts if first is None else first
                expected = [{k: v for k, v in a.items() if k != "text"} for a in anchors_for(first)]
                if expected != repo["anchors"]:
                    raise ValueError("anchor selection drift")
            print("Frozen manifest, sources, anchors and licenses verified; no resolver executed.", flush=True)
            return
    else:
        repositories = []
        for name in protocol["natural"]["repositories"]:
            repositories.append(pin_repository(name, cache, protocol))
            print("Pinned", name, flush=True)
        manifest = {"schema_version": 1, "pinned_at_utc": datetime.now(timezone.utc).isoformat(),
                    "protocol_sha256": digest(protocol_bytes), "repositories": repositories}
        write(manifest_path, manifest)
    limits = protocol["natural"]["resource_limits"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda item: download_archive(cache, *item, limits["max_archive_bytes"]),
                      [(repo, version) for repo in manifest["repositories"] for version in repo["versions"]]))
    for repo in manifest["repositories"]:
        previous, first, transition_counts = None, None, []
        for version in repo["versions"]:
            path = archive_path(cache, repo, version)
            raw_hash = digest(path.read_bytes())
            if version.get("archive_sha256", raw_hash) != raw_hash:
                raise ValueError("archive bytes changed")
            texts, licenses, excluded = read_sources(path, repo["prefixes"], max_file_bytes=limits["max_file_bytes"])
            size = sum(len(text.encode("utf-8")) for text in texts.values())
            if len(texts) > limits["max_production_files"] or size > limits["max_production_bytes"]:
                raise ValueError("production source resource limit exceeded")
            files = {p: sha256(s) for p, s in sorted(texts.items())}
            changed = None if previous is None else sorted(p for p in files.keys() | previous.keys() if files.get(p) != previous.get(p))
            version.update({"archive_sha256": raw_hash, "archive_bytes": path.stat().st_size,
                            "files": files, "source_bytes": size, "excluded": excluded,
                            "changed_source_paths_from_previous": changed, "licenses": []})
            for name, raw in sorted(licenses.items()):
                dest = DATA / "licenses" / repo["repository"].replace("/", "--") / version["commit"] / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(raw)
                version["licenses"].append({"path": name, "sha256": digest(raw), "bytes": len(raw),
                                            "local": dest.relative_to(ROOT).as_posix(),
                                            "url": f"https://raw.githubusercontent.com/{repo['repository']}/{version['commit']}/{name}"})
            first = texts if first is None else first
            previous = files
            if changed is not None:
                transition_counts.append(len(changed))
            print(repo["repository"], version["commit"][:8], len(texts), "source files", flush=True)
        audit = {}
        selected = anchors_for(first, protocol["natural"]["anchors_per_repository"], audit=audit)
        if len(selected) != protocol["natural"]["anchors_per_repository"]:
            raise ValueError("insufficient anchor identities: " + repo["repository"])
        if not any(transition_counts):
            raise ValueError("no production source change in fixed interval: " + repo["repository"])
        repo["anchors"] = [{k: v for k, v in anchor.items() if k != "text"} for anchor in selected]
        repo["anchor_selection_audit"] = audit
        repo["source_changed_transitions"] = sum(bool(count) for count in transition_counts)
        repo["source_unchanged_transitions"] = sum(not count for count in transition_counts)
        write(manifest_path, manifest)
    manifest["sources_frozen_at_utc"] = datetime.now(timezone.utc).isoformat()
    write(manifest_path, manifest)
    validate_manifest(manifest, protocol)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True, help="Private archive/API cache outside Git")
    args = parser.parse_args()
    prepare(args.cache_dir)


if __name__ == "__main__":
    main()
