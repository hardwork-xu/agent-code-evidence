#!/usr/bin/env python3
"""Offline license-byte and frozen-corpus attribution checks. 离线检查许可与语料归属。

The inventory is a reviewed snapshot, not an automatic legal-origin detector.
Review new sources before explicitly running --write-inventory.
清单是经过审阅的快照，不是自动判定代码来源的工具；更新前须审阅来源。
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import xml.etree.ElementTree as ET


BASE_MANIFESTS = ("benchmarks/manifest.json", "benchmarks/v1/manifest.json")
HISTORY = "benchmarks/graph/history_manifest.json"
PROTOCOL = "benchmarks/revision_tasks/frozen/protocol.json"
TASKS = "benchmarks/revision_tasks/frozen/tasks.json"
HUMAN_PROTOCOL = "benchmarks/downstream/results/protocol.json"
CONTEXTS = ("benchmarks/revision_tasks/model-inputs/contexts.json",
            "benchmarks/revision_tasks/scope-sensitivity-inputs/contexts.json")
SUFFIXES = {".json", ".jsonl", ".txt", ".md", ".py"}


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_json(root: Path, path: str):
    return json.loads(safe_path(root, path).read_text(encoding="utf-8"))


def safe_path(root: Path, relative: str) -> Path:
    """Reject path escape and symlinks. 拒绝越界路径与符号链接。"""
    p = PurePosixPath(relative)
    if p.is_absolute() or ".." in p.parts or not p.parts or "\\" in relative:
        raise ValueError(f"unsafe attribution path: {relative}")
    path = root.joinpath(*p.parts)
    if any(part.is_symlink() for part in (path, *path.parents) if part != root.parent):
        raise ValueError(f"symlink in attribution path: {relative}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"attribution path escapes root: {relative}")
    return path


def source_pins(root: Path) -> dict:
    """Read the historical declarations without changing them. 只读历史声明。"""
    pins = {}
    names = {}
    for path in BASE_MANIFESTS:
        for repo in read_json(root, path)["repositories"]:
            names[repo["name"]] = repo
            for version in repo["versions"].values():
                key = repo["name"] + "@" + version["commit"]
                pins[key] = {"project": repo["name"], "repository": repo["repository"],
                             "commit": version["commit"], "license": repo["license"]}
    for repo in read_json(root, HISTORY)["repositories"]:
        for version in repo["versions"]:
            key = repo["name"] + "@" + version["commit"]
            pins[key] = {"project": repo["name"],
                         "repository": names[repo["name"]]["repository"],
                         "commit": version["commit"], "license": names[repo["name"]]["license"]}
    for name, repo in read_json(root, PROTOCOL)["repositories"].items():
        for version in repo["versions"].values():
            key = name + "@" + version["commit"]
            if key not in pins:
                raise ValueError(f"revision protocol has an unreviewed source: {key}")
    human = read_json(root, HUMAN_PROTOCOL)
    pins["human-eval@" + human["upstream_revision"]] = {
        "project": "human-eval", "repository": human["upstream_repository"],
        "commit": human["upstream_revision"], "license": "MIT"}
    return pins


def required_licenses(root: Path) -> dict:
    """License paths/hashes come from independent frozen inputs. 读取独立历史许可声明。"""
    result = {}
    by_name = {}
    for path in BASE_MANIFESTS:
        for repo in read_json(root, path)["repositories"]:
            for version in repo["versions"].values():
                records = {x if isinstance(x, str) else x["path"]:
                           None if isinstance(x, str) else x["sha256"]
                           for x in version["license_files"]}
                records = {p: h for p, h in records.items()
                           if p.startswith("LICENSE") or p == "ext/LICENSE"}
                result[repo["name"] + "@" + version["commit"]] = records
                by_name[repo["name"]] = records
    for repo in read_json(root, HISTORY)["repositories"]:
        for version in repo["versions"]:
            result.setdefault(repo["name"] + "@" + version["commit"],
                              dict.fromkeys(by_name[repo["name"]]))
    human = read_json(root, HUMAN_PROTOCOL)
    result["human-eval@" + human["upstream_revision"]] = {"LICENSE": None}
    return result


def verify_licenses(root: Path, manifest: dict, pins: dict,
                    required: dict | None = None) -> None:
    """Verify full license files and pinned origin metadata. 核验完整许可及固定来源。"""
    required = required_licenses(root) if required is None else required
    actual = {}
    for source in manifest["sources"]:
        key = source["project"] + "@" + source["commit"]
        if key in actual:
            raise ValueError(f"duplicate source: {key}")
        actual[key] = source
        if not re.fullmatch(r"[0-9a-f]{40}", source["commit"]):
            raise ValueError(f"source is not pinned: {key}")
        if key not in pins or any(source[k] != v for k, v in pins[key].items()):
            raise ValueError(f"source metadata differs from frozen declaration: {key}")
        files = source["license_files"]
        if not files:
            raise ValueError(f"license text missing: {key}")
        paths = [f["upstream_path"] for f in files]
        if len(set(paths)) != len(paths) or set(paths) != set(required[key]):
            raise ValueError(f"required license files missing or duplicated: {key}")
        total = 0
        for record in files:
            path = safe_path(root, record["path"])
            raw = path.read_bytes()
            total += len(raw)
            if len(raw) != record["bytes"] or digest(raw) != record["sha256"]:
                raise ValueError(f"license bytes changed: {record['path']}")
            expected = required[key][record["upstream_path"]]
            if expected and digest(raw) != expected:
                raise ValueError(f"license differs from historical hash: {record['path']}")
            url = source["repository"].replace("https://github.com/",
                                                "https://raw.githubusercontent.com/")
            if record["url"] != f"{url}/{source['commit']}/{record['upstream_path']}":
                raise ValueError(f"license URL is not pinned: {record['path']}")
        # Root license bodies exceed this size; a digest/URL alone never suffices.
        if total < 500:
            raise ValueError(f"license body missing (hash/reference alone is insufficient): {key}")
    if set(actual) != set(pins):
        raise ValueError("uncovered corpus sources: " + ", ".join(sorted(set(pins) - set(actual))))
    human = next(s for s in actual.values() if s["project"] == "human-eval")
    retained = safe_path(root, "benchmarks/downstream/upstream/LICENSE").read_bytes()
    if retained != safe_path(root, human["license_files"][0]["path"]).read_bytes():
        raise ValueError("retained HumanEval license differs from the pinned upstream bytes")


def context_fragments(context: str, condition: str) -> list[dict]:
    """Extract path/span metadata from each published renderer. 提取已发布片段的位置。"""
    if not context:
        if condition != "no_context":
            raise ValueError("unexpected empty source context")
        return []
    if condition == "archex":
        tree = ET.fromstring(context)
        result = []
        for chunk in tree.findall("./chunks/chunk"):
            start, end = map(int, chunk.attrib["lines"].split("-"))
            result.append({"path": chunk.attrib["file"], "start_line": start,
                           "end_line": end, "text": chunk.findtext("code", ""),
                           "encoding": "xml-cdata-with-renderer-whitespace"})
        return result
    if condition == "fresh_bm25":
        result = []
        pattern = r"(?m)^(\{[^\n]+\})\n```\n(.*?)\n```"
        for match in re.finditer(pattern, context, re.DOTALL):
            record = json.loads(match[1])
            if "path" not in record:
                continue
            result.append({"path": record["path"], "start_line": record["start_line"],
                           "end_line": record["end_line"], "text": match[2],
                           "encoding": "markdown-fence"})
        if not result:
            raise ValueError("BM25 context has no recognizable source fragments")
        return result
    if condition not in {"graph_current", "fresh_anchors", "stale_anchors"}:
        raise ValueError(f"unreviewed context condition: {condition}")
    payload = json.loads(context)
    nodes = payload.get("nodes", payload.get("source", []))
    result = []
    for node in nodes:
        if "text" in node:
            result.append({k: node[k] for k in ("path", "start_line", "end_line", "text")}
                          | {"encoding": "graph-display-escaped" if condition == "graph_current"
                             else "json-string"})
    return result


def fragment(root: Path, ref: str, record: dict, location: str, pins: dict) -> dict:
    path = record["path"]
    safe_path(root, path)  # upstream relative path, need not exist locally
    start, end = record["start_line"], record["end_line"]
    if not isinstance(start, int) or not isinstance(end, int) or not 1 <= start <= end:
        raise ValueError(f"invalid upstream line range at {location}")
    source = pins[ref]
    return {"source": ref, "upstream_path": path, "start_line": start, "end_line": end,
            "url": f"{source['repository']}/blob/{source['commit']}/{path}#L{start}-L{end}",
            "rendered_text_sha256": digest(record["text"].encode()),
            "encoding": record.get("encoding", "json-string"), "location": location}


def make_inventory(root: Path, pins: dict) -> dict:
    """Index excerpts and records, never rewrite historical artifacts. 仅建立索引。"""
    tasks = read_json(root, TASKS)
    by_id = {t["id"]: t for t in tasks}
    protocol = read_json(root, PROTOCOL)
    versions = {name: {side: name + "@" + data["commit"]
                       for side, data in repo["versions"].items()}
                for name, repo in protocol["repositories"].items()}
    fragments = []
    adaptations = []
    for i, task in enumerate(tasks):
        name = task["repository"]
        if name not in versions:
            raise ValueError(f"unreviewed task repository: {name}")
        provenance = task["provenance"]
        adaptations.append({"task_id": task["id"], "source": versions[name]["after"],
                            "location": f"{TASKS}#/{i}/code",
                            "code_sha256": digest(task["code"].encode()),
                            "upstream_test": task["upstream_test"],
                            "upstream_test_url": provenance["test_url"],
                            "adaptation": provenance["adaptation"]})
        for side, anchors in task["source_anchors"].items():
            ref = versions[name][side]
            for j, anchor in enumerate(anchors):
                for k, match in enumerate(anchor["matches"]):
                    loc = f"{TASKS}#/{i}/source_anchors/{side}/{j}/matches/{k}/text"
                    fragments.append(fragment(root, ref, match, loc, pins))
    for path in CONTEXTS:
        for i, entry in enumerate(read_json(root, path)):
            task = by_id[entry["task_id"]]
            side = "before" if entry["condition"] == "stale_anchors" else "after"
            ref = versions[task["repository"]][side]
            for j, record in enumerate(context_fragments(entry["context"], entry["condition"])):
                loc = f"{path}#/{i}/context:fragment:{j}"
                fragments.append(fragment(root, ref, record, loc, pins))
    corrections = read_json(root, "third_party/noncontiguous-excerpts.json")["fragments"]
    by_location = {r["location"]: r for r in corrections}
    found = set()
    for record in fragments:
        record["span_status"] = "renderer-reported"
        correction = by_location.get(record["location"])
        if correction is None:
            continue
        for key in ("source", "upstream_path", "rendered_text_sha256"):
            if record[key] != correction[key]:
                raise ValueError("stale noncontiguous-span correction: " + record["location"])
        if (record["start_line"], record["end_line"]) != (
                correction["reported_start_line"], correction["reported_end_line"]):
            raise ValueError("changed renderer span: " + record["location"])
        found.add(record["location"])
        record["span_status"] = "historical-noncontiguous-module-excerpt"
        record["url"] = record["url"].split("#L")[0]
        record["matched_nonempty_line_ranges"] = correction["matched_nonempty_line_ranges"]
        record["upstream_file_sha256"] = correction["upstream_file_sha256"]
    if found != set(by_location) or len(by_location) != len(corrections):
        raise ValueError("unmatched or duplicate noncontiguous-span correction")
    human_ref = next(k for k in pins if k.startswith("human-eval@"))
    human_tasks = []
    for i, task in enumerate(read_json(root, "benchmarks/downstream/upstream/tasks.json")):
        human_tasks.append({"task_id": task["task_id"], "source": human_ref,
                            "upstream_path": "data/HumanEval.jsonl.gz",
                            "location": f"benchmarks/downstream/upstream/tasks.json#/{i}",
                            "fields": {k: digest(task[k].encode()) for k in ("prompt", "test")}})
    # Freeze all old study files, including prompt replicas, outputs and metadata.
    # New studies outside these roots must declare their own attribution scope.
    roots = ("benchmarks/revision_tasks", "benchmarks/downstream", "benchmarks/v1",
             "benchmarks/graph", "benchmarks/results")
    paths = set(BASE_MANIFESTS)
    paths.update({"benchmarks/queries.json"})
    for directory in roots:
        paths.update(p.relative_to(root).as_posix() for p in (root / directory).rglob("*")
                     if p.is_file() and p.suffix in SUFFIXES and "__pycache__" not in p.parts)
    artifacts = []
    revision_refs = sorted(ref for sides in versions.values() for ref in sides.values())
    for path in sorted(paths):
        p = safe_path(root, path)
        if not p.exists():
            continue
        if path.startswith("benchmarks/revision_tasks/"):
            refs, kind = revision_refs, "revision-study-source-or-derived-record"
            # Task-named replicas retain an exact repository/side association.
            for task_id, task in by_id.items():
                if f"/{task_id}__" in path:
                    condition = path.split(f"/{task_id}__", 1)[1].split("/", 1)[0]
                    side = "before" if condition == "stale_anchors" else "after"
                    refs = [versions[task["repository"]][side]]
                    break
        elif path.startswith("benchmarks/downstream/"):
            refs, kind = [human_ref], "humaneval-adaptation-or-derived-record"
        else:
            refs, kind = [], "source-metadata-or-owned-synthetic-fixture"
        artifacts.append({"path": path, "sha256": digest(p.read_bytes()),
                          "classification": kind, "source_scope": refs})
    return {"schema_version": 1, "artifacts": artifacts, "source_fragments": fragments,
            "adapted_probes": adaptations, "humaneval_tasks": human_tasks,
            "scope_note": "Rendered spans link to pinned sources; display escaping and truncation "
            "are retained, not asserted byte-identical to full upstream files. Old drift/graph "
            "reports publish paths/hashes and owned synthetic fixtures, not the natural source trees. "
            "A source_scope on a record is a conservative attribution envelope, not a claim that "
            "every listed library appears in that record. New studies require an explicit review."}


def verify_source_report(root: Path, pins: dict, inventory: dict) -> None:
    """Keep offline source evidence and disclosed defects consistent. 核验来源记录一致性。"""
    report = read_json(root, "third_party/source-verification.json")
    fragments = inventory["source_fragments"]
    files = {}
    for record in report["files"]:
        key = record["source"], record["path"]
        source = pins[record["source"]]
        expected = source["repository"].replace("https://github.com/",
                                                "https://raw.githubusercontent.com/")
        if record["url"] != f"{expected}/{source['commit']}/{record['path']}":
            raise ValueError("source verification URL differs from pinned origin")
        if key in files or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"]):
            raise ValueError("duplicate or invalid source verification file")
        files[key] = record
    if set(files) != {(r["source"], r["upstream_path"]) for r in fragments}:
        raise ValueError("source verification does not cover the excerpt inventory")
    defects = [r for r in fragments
               if r["span_status"] == "historical-noncontiguous-module-excerpt"]
    if (report["source_files_fetched"] != len(files)
            or report["fragments_checked"] != len(fragments)
            or report["known_noncontiguous_span_defects"] != len(defects)
            or report["exact_declared_span_matches"]
            + report["declared_span_matches_ignoring_outer_renderer_whitespace"]
            + len(defects) != len(fragments)):
        raise ValueError("source verification counts differ from disclosed inventory")
    for record in defects:
        if record["upstream_file_sha256"] != files[record["source"],
                                                  record["upstream_path"]]["sha256"]:
            raise ValueError("span-defect source hash differs from verified file")


def assert_metadata_only(value, location: str = "") -> None:
    """Reject source bodies in the explicitly metadata-only corpus. 拒绝源码正文。"""
    if isinstance(value, dict):
        for key, item in value.items():
            loc = location + "/" + str(key)
            if key in {"text", "code", "source_text", "prompt", "rendered_prompt"} and item:
                raise ValueError("source body in metadata-only scope: " + loc)
            assert_metadata_only(item, loc)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            assert_metadata_only(item, location + "/" + str(i))
    elif isinstance(value, str):
        if re.search(r"(?m)^\s*(?:async\s+)?(?:def |class |from \S+ import |import \w)", value):
            raise ValueError("source-like string in metadata-only scope: " + location)
        if value.lstrip().startswith(("{", "[")):
            try:
                nested = json.loads(value)
            except ValueError:
                return
            assert_metadata_only(nested, location + "/encoded-json")


def check_metadata_corpus(root: Path) -> dict:
    """Check the later metadata-only study without pinning timing outputs.

    校验后续研究的来源哈希、完整许可和无源码正文条件，不锁死新增计时结果字节。
    """
    directory = root / "benchmarks/selective_reuse"
    if not directory.exists():
        return {"status": "absent", "projects": 0, "pinned_revisions": 0, "license_files": 0}
    manifest = read_json(root, "benchmarks/selective_reuse/natural-manifest.json")
    protocol_path = safe_path(root, "benchmarks/selective_reuse/protocol.json")
    protocol = json.loads(protocol_path.read_text())
    current_protocol_hash = digest(protocol_path.read_bytes())
    pinned_protocol_hash = manifest["protocol_sha256"]
    protocol_match = "current-protocol"
    if current_protocol_hash != pinned_protocol_hash:
        superseded = protocol.get("supersedes_protocol_sha256", [])
        amendments = protocol.get("amendments_before_primary", [])
        if (pinned_protocol_hash not in superseded or not amendments
                or not all(isinstance(a, str) and a.strip() for a in amendments)
                or not all(re.fullmatch(r"[0-9a-f]{64}", h) for h in superseded)):
            raise ValueError("metadata study protocol hash differs without documented lineage")
        protocol_match = "explicitly-superseded-protocol; amendments-recorded"
    if not manifest.get("sources_frozen_at_utc"):
        raise ValueError("metadata source preparation is incomplete")
    projects, revisions, licenses = set(), set(), set()
    for repo in manifest["repositories"]:
        owner_repo = repo["repository"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", owner_repo):
            raise ValueError("invalid metadata source repository")
        if owner_repo in projects:
            raise ValueError("duplicate metadata source repository")
        projects.add(owner_repo)
        if len(repo["versions"]) != protocol["natural"]["versions"]:
            raise ValueError("incomplete metadata source version sequence")
        previous = None
        for version in repo["versions"]:
            commit = version["commit"]
            parents = version.get("parents", [])
            if not parents or not all(re.fullmatch(r"[0-9a-f]{40}", p) for p in parents):
                raise ValueError("metadata source parent hashes missing or invalid")
            if previous is not None and parents[0] != previous:
                raise ValueError("metadata source versions are not an adjacent first-parent chain")
            previous = commit
            key = owner_repo + "@" + commit
            if not re.fullmatch(r"[0-9a-f]{40}", commit) or key in revisions:
                raise ValueError("unfixed or duplicate metadata source revision")
            revisions.add(key)
            expected_url = f"https://codeload.github.com/{owner_repo}/tar.gz/{commit}"
            if version["archive_url"] != expected_url:
                raise ValueError("metadata archive URL differs from pinned revision")
            if not re.fullmatch(r"[0-9a-f]{64}", version["archive_sha256"]):
                raise ValueError("metadata source archive hash missing")
            for path, file_hash in version["files"].items():
                safe_path(root, path)
                if not re.fullmatch(r"[0-9a-f]{64}", file_hash):
                    raise ValueError("invalid metadata source file hash")
            if not version["files"] or not version["licenses"]:
                raise ValueError("metadata source files/license texts missing")
            total = 0
            for record in version["licenses"]:
                local = record["local"]
                prefix = "benchmarks/selective_reuse/licenses/" + owner_repo.replace("/", "--")
                if local != prefix + "/" + commit + "/" + record["path"]:
                    raise ValueError("metadata license path differs from pinned source")
                raw = safe_path(root, local).read_bytes()
                if digest(raw) != record["sha256"]:
                    raise ValueError("metadata license bytes changed: " + local)
                if local in licenses:
                    raise ValueError("duplicate metadata license record")
                licenses.add(local)
                total += len(raw)
            if total < 500:
                raise ValueError("metadata license body missing; hashes alone do not suffice")
        oldest = repo["versions"][0]["files"]
        for anchor in repo["anchors"]:
            if anchor["path"] not in oldest or anchor["file_sha256"] != oldest[anchor["path"]]:
                raise ValueError("metadata anchor differs from declared source file")
            if not 1 <= anchor["start_line"] <= anchor["end_line"]:
                raise ValueError("invalid metadata anchor range")
    if projects != set(protocol["natural"]["repositories"]):
        raise ValueError("metadata source selection differs from fixed protocol")
    on_disk = {p.relative_to(root).as_posix() for p in (directory / "licenses").rglob("*")
               if p.is_file()}
    if on_disk != licenses:
        raise ValueError("unlisted or missing metadata license files")
    checked_records = 0
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or "licenses" in path.parts:
            continue
        relative = path.relative_to(root).as_posix()
        safe_path(root, relative)
        if path.suffix == ".json":
            assert_metadata_only(json.loads(path.read_text()), relative)
            checked_records += 1
        elif path.suffix == ".jsonl":
            for line in path.read_text().splitlines():
                if line.strip():
                    assert_metadata_only(json.loads(line), relative)
            checked_records += 1
        elif path.suffix == ".py" and path.name == "oracle_cases.py":
            # Explicitly reviewed, project-authored synthetic oracle definitions.
            continue
        elif path.suffix == ".md":
            # Prose is authored documentation; source quotes require source review.
            assert_metadata_only(path.read_text(), relative)
        else:
            raise ValueError("unreviewed file in metadata-only scope: " + relative)
    return {"status": "passed", "projects": len(projects), "pinned_revisions": len(revisions),
            "license_files": len(licenses), "metadata_records_checked": checked_records,
            "protocol_match": protocol_match, "current_protocol_sha256": current_protocol_hash,
            "selection_protocol_sha256": pinned_protocol_hash,
            "scope": "source hashes, anchors and measured statistics; no upstream source bodies"}


def check(root: Path, *, write_inventory: bool = False) -> dict:
    pins = source_pins(root)
    manifest = read_json(root, "third_party/manifest.json")
    verify_licenses(root, manifest, pins)
    inventory = make_inventory(root, pins)
    path = safe_path(root, "third_party/inventory.json")
    if write_inventory:
        path.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    elif inventory != read_json(root, "third_party/inventory.json"):
        raise ValueError("attribution inventory differs: review changed/new study files and sources; "
                         "do not automatically bless changes with --write-inventory")
    verify_source_report(root, pins, inventory)
    metadata = check_metadata_corpus(root)
    return {"status": "passed", "metadata_only_study": metadata,
            "known_historical_span_defects": sum(
                r["span_status"] == "historical-noncontiguous-module-excerpt"
                for r in inventory["source_fragments"]),
            "projects": len({p['project'] for p in pins.values()}),
            "pinned_revisions": len(pins),
            "license_files": sum(len(s["license_files"]) for s in manifest["sources"]),
            "artifacts": len(inventory["artifacts"]),
            "source_fragments": len(inventory["source_fragments"]),
            "adapted_probes": len(inventory["adapted_probes"]),
            "humaneval_tasks": len(inventory["humaneval_tasks"]),
            "scope": "offline integrity/coverage; not automatic copyright-origin discovery"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="repository root / 仓库根目录")
    parser.add_argument("--write-inventory", action="store_true",
                        help="after source review, record the inventory / 审阅来源后更新归属索引")
    args = parser.parse_args()
    try:
        result = check(args.root.resolve(), write_inventory=args.write_inventory)
    except (ValueError, KeyError, OSError, TypeError, ET.ParseError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
