"""Seal all static predictions before later target execution.

Never import task source, run dataset commands, or launch target interpreters.
Immutable private outputs retain failed tasks. A hash seal is not authentication
or evidence that another process has never seen the tasks.
在后续目标执行前封存静态预测；不导入上游、不运行数据命令或目标解释器。
失败仍占原任务分母；哈希封存不是身份认证，也不证明外部从未见过样本。
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time
import traceback

from benchmarks.known_task_execution.worker import validate_tree
from .methods import evaluate_pair
from .observer import MAX_SOURCE_BYTES, MAX_SOURCE_FILES, MAX_TOTAL_SOURCE_BYTES


FIXED_POLICY = {"anchor_limit": 32, "repeats": 3, "max_depth": 4, "max_nodes": 256}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    """Exclusive immutable private JSON / 独占创建私有 JSON，禁止覆盖。"""
    raw = canonical(value) + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)


def _diagnostic(path):
    """Raw traceback is private, never part of a scientific/public row."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        traceback.print_exc(file=stream)


def _directory_bytes(directory):
    return sum(path.stat().st_size for path in directory.rglob("*") if path.is_file())


def _absolute(path):
    result = Path(path)
    if not result.is_absolute():
        raise ValueError("an absolute private path is required")
    return result


def _relative(value):
    if (type(value) is not str or not value or "\\" in value or ":" in value
            or "\x00" in value or value.startswith("/")
            or any(part in {"", ".", ".."} for part in value.split("/"))):
        raise ValueError("unsafe relative production path")
    return value


def implementation_bindings(repository):
    """Bind the entire static core and actual prediction imports / 固定全部静态核心及预测实现。"""
    repository = _absolute(repository).resolve(strict=True)
    names = {"benchmarks/semantic_observer/__init__.py",
             "benchmarks/semantic_observer/observer.py",
             "benchmarks/semantic_observer/methods.py",
             "benchmarks/semantic_observer/predict.py",
             "benchmarks/known_task_execution/worker.py"}
    for name in ("benchmarks/__init__.py", "benchmarks/known_task_execution/__init__.py"):
        if (repository / name).is_file():
            names.add(name)
    names.update(path.relative_to(repository).as_posix()
                 for path in (repository / "src/contextproof").rglob("*.py"))
    if not any(name.startswith("src/contextproof/") for name in names):
        raise ValueError("actual static core is absent")
    result = {}
    for name in sorted(names):
        path = repository / name
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(repository):
            raise ValueError("implementation source escaped repository")
        result[name] = sha(path.read_bytes())
    return result


def validate_protocol(protocol, repository):
    bindings = protocol.get("implementation_sha256")
    actual = implementation_bindings(repository)
    if not isinstance(bindings, dict) or not actual.keys() <= bindings.keys():
        raise ValueError("prediction protocol lacks full implementation bindings")
    for name, expected in bindings.items():
        _relative(name)
        path = repository / name
        if (path.is_symlink() or not path.resolve(strict=True).is_relative_to(repository)
                or sha(path.read_bytes()) != expected):
            raise ValueError("prediction implementation changed")
    policy = protocol.get("prediction")
    if not isinstance(policy, dict) or any(type(policy.get(key)) is not int
                                          or policy[key] != value
                                          for key, value in FIXED_POLICY.items()):
        raise ValueError("prediction policy must retain frozen 32/3/4/256")
    for key, low, high in [("cpu_seconds", 1, 600), ("wall_seconds", 1, 1200),
                           ("max_rss_mib", 64, 4096), ("max_output_mib", 1, 256)]:
        if type(policy.get(key)) is not int or not low <= policy[key] <= high:
            raise ValueError("invalid explicit prediction resource cap: " + key)
    return policy


def _environment(task, config):
    # Preserve exact reviewed declarations; do not claim an import/dependency gate.
    # 原样绑定受审环境声明；本程序不把读取元数据说成运行时验证。
    return {"target_python": task.get("python"),
            "task_environment": task.get("environment"),
            "role_environment": config.get("environment"),
            "environment_sha256": config.get("environment_sha256"),
            "dependency_versions": config.get("dependency_versions"),
            "verification": "manifest_declared_only; target interpreter/dependencies not imported"}


def _roles(task):
    roles = task.get("roles")
    if (not isinstance(roles, list) or len(roles) != 2
            or any(not isinstance(role, dict) for role in roles)
            or {role.get("role") for role in roles} != {"base_tests", "fixed_tests"}):
        raise ValueError("exact base_tests and fixed_tests roles are required")
    return {role["role"]: role["config"] for role in roles}


def _load_role(task, role, config):
    root = _absolute(config["source_root"]).resolve(strict=True)
    expected = validate_tree(root, config["source_files"])
    paths = config.get("production_paths")
    if (not isinstance(paths, list) or not paths or len(paths) > MAX_SOURCE_FILES
            or len(paths) != len(set(paths))):
        raise ValueError("invalid bounded production path set")
    texts, files, total = {}, [], 0
    for name in sorted(paths):
        _relative(name)
        if not name.endswith(".py") or name not in expected or name in config.get("test_files", []):
            raise ValueError("production path must be a pinned non-test .py file")
        with (root / name).open("rb") as stream:
            raw = stream.read(MAX_SOURCE_BYTES + 1)
        total += len(raw)
        if len(raw) > MAX_SOURCE_BYTES or total > MAX_TOTAL_SOURCE_BYTES:
            raise ValueError("production source byte limit exceeded")
        digest = sha(raw)
        if digest != expected[name]["sha256"] or len(raw) != expected[name]["bytes"]:
            raise ValueError("production bytes changed after full-tree validation")
        texts[name] = raw.decode("utf-8")
        files.append({"path": name, "sha256": digest, "bytes": len(raw)})
    return texts, {"role": role, "source_root": str(root),
                   "config_sha256": sha(canonical(config)),
                   "source_files_sha256": sha(canonical(config["source_files"])),
                   "full_production_files": files,
                   "production_files_sha256": sha(canonical(files)),
                   "production_bytes": total, "environment": _environment(task, config)}


def predict_task(task, protocol, *, repository, diagnostic_path=None):
    """Pure-source task stage; exceptions become retained rows / 只读源码阶段，保留失败。"""
    started = time.perf_counter()
    phase, roles, bindings = "configuration", {}, []
    record = {"schema_version": 1, "task_id": task.get("task_id"),
              "task_config_sha256": sha(canonical(task)),
              "protocol_sha256": sha(canonical(protocol)),
              "started_utc": datetime.now(timezone.utc).isoformat(),
              "stage": "pre_target_static_prediction", "target_source_imported": False,
              "target_interpreter_launched": False, "mature_research_established": False,
              "timing_scope": "source/implementation validation, loading and methods; controller wall additionally includes imports and output serialization"}
    try:
        policy = validate_protocol(protocol, repository)
        roles = _roles(task)
        phase = "source_validation_and_loading"
        texts = {}
        for role in ("base_tests", "fixed_tests"):
            texts[role], binding = _load_role(task, role, roles[role])
            bindings.append(binding)
        loaded = time.perf_counter()
        phase = "actual_static_methods"
        result = evaluate_pair(texts["base_tests"], texts["fixed_tests"], **FIXED_POLICY)
        measured = time.perf_counter()
        phase = "final_source_and_implementation_validation"
        for config in roles.values():
            validate_tree(_absolute(config["source_root"]).resolve(strict=True), config["source_files"])
        validate_protocol(protocol, repository)
        record.update({"status": "predicted", "roles": bindings, "prediction": result,
                       "timings_seconds": {"source_validation_and_load": loaded - started,
                                           "methods_including_preparation": measured - loaded,
                                           "final_validation": time.perf_counter() - measured,
                                           "end_to_end": time.perf_counter() - started},
                       "resource_policy": policy})
    except Exception as error:
        record.update({"status": "failed", "roles": bindings,
                       "failure": {"phase": phase, "error_type": type(error).__name__},
                       "timings_seconds": {"end_to_end": time.perf_counter() - started}})
        if diagnostic_path is not None:
            _diagnostic(_absolute(diagnostic_path))
    return record


def _stop(child):
    if child.poll() is None:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _launch(task, protocol, directory, repository):
    directory.mkdir(mode=0o700)
    scratch = directory / "scratch"
    scratch.mkdir(mode=0o700)
    request = directory / "request.json"
    result_path = directory / "prediction.json"
    save(request, {"task": task, "protocol": protocol, "repository": str(repository)})
    command = [sys.executable, "-s", "-B", "-m", "benchmarks.semantic_observer.predict",
               "--child-request", str(request), "--child-request-sha256", sha(request.read_bytes()),
               "--child-output", str(result_path)]
    environment = {"PATH": str(Path(sys.executable).parent) + os.pathsep + os.defpath,
                   "HOME": str(scratch), "TMPDIR": str(scratch),
                   "XDG_CACHE_HOME": str(scratch), "PYTHONHASHSEED": "0",
                   "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                   "PYTHONPATH": str(repository) + os.pathsep + str(repository / "src"),
                   "LC_ALL": "C.UTF-8", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"}
    policy, started, peak, reason = protocol["prediction"], time.perf_counter(), 0, None
    fd = os.open(directory / "stderr.log", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stderr:
        child = subprocess.Popen(command, cwd=repository, env=environment,
                                 stdout=subprocess.DEVNULL, stderr=stderr, start_new_session=True)
        try:
            while child.poll() is None:
                rss = subprocess.run(["/bin/ps", "-o", "rss=", "-p", str(child.pid)],
                                     capture_output=True, text=True, timeout=2)
                value = rss.stdout.strip()
                if rss.returncode == 0 and value.isdigit():
                    peak = max(peak, int(value))
                if time.perf_counter() - started > policy["wall_seconds"]:
                    reason = "wall_limit"
                elif peak > policy["max_rss_mib"] * 1024:
                    reason = "rss_limit"
                elif _directory_bytes(directory) > policy["max_output_mib"] * 1024**2:
                    reason = "output_limit"
                if reason:
                    _stop(child)
                    break
                time.sleep(0.1)
        except BaseException:
            _stop(child)
            child.wait()
            raise
        returncode = child.wait()
    final_size = _directory_bytes(directory)
    if final_size > policy["max_output_mib"] * 1024**2:
        reason = "output_limit"
    (directory / "stderr.log").chmod(0o600)
    state = {"closed": True, "returncode": returncode, "termination_reason": reason,
             "wall_seconds": time.perf_counter() - started,
             "sampled_peak_rss_mib": peak / 1024,
             "rss_sample_observed": peak > 0, "output_bytes": final_size,
             "process_scope": "one owned static process/group; sampled RSS may miss peaks"}
    result = None
    if result_path.is_file() and not result_path.is_symlink():
        try:
            result = json.loads(result_path.read_bytes())
        except (OSError, ValueError):
            pass
    if (reason or returncode != 0 or not isinstance(result, dict)
            or result.get("task_config_sha256") != sha(canonical(task))
            or result.get("protocol_sha256") != sha(canonical(protocol))):
        result = {"schema_version": 1, "task_id": task["task_id"], "status": "failed",
                  "task_config_sha256": sha(canonical(task)),
                  "protocol_sha256": sha(canonical(protocol)),
                  "failure": {"phase": "bounded_child", "error_type": reason or "child_result_unavailable"}}
    return state, result


def predict(manifest, protocol, output, *, repository):
    """Sequentially seal every selected row, including failures / 串行封存全分母。"""
    output, repository = _absolute(output), _absolute(repository).resolve(strict=True)
    if output.exists() or output.is_symlink():
        raise ValueError("refuse existing prediction output")
    if output.resolve().is_relative_to(repository):
        raise ValueError("prediction output must remain outside public source")
    if any((parent / ".git").exists() for parent in [output, *output.parents]):
        raise ValueError("private prediction output must be outside Git")
    validate_protocol(protocol, repository)
    tasks = manifest.get("tasks")
    if (not isinstance(tasks, list) or not tasks or any(not isinstance(t, dict) for t in tasks)
            or any(type(t.get("task_id")) is not str or not t["task_id"] for t in tasks)
            or len({t["task_id"] for t in tasks}) != len(tasks)):
        raise ValueError("nonempty distinct frozen task list is required")
    for task in tasks:
        roles = task.get("roles")
        for role in roles if isinstance(roles, list) else []:
            if isinstance(role, dict) and isinstance(role.get("config"), dict):
                root = role["config"].get("source_root")
                if isinstance(root, str) and Path(root).is_absolute() and output.resolve().is_relative_to(Path(root).resolve()):
                    raise ValueError("prediction output must not contaminate a source role")
    output.mkdir(mode=0o700, parents=True)
    save(output / "manifest.json", manifest)
    save(output / "protocol.json", protocol)
    rows = []
    for index, task in enumerate(tasks):
        try:
            validate_protocol(protocol, repository)
            closure, result = _launch(task, protocol, output / f"input-{index:03d}", repository)
            validate_protocol(protocol, repository)
        except Exception as error:
            _diagnostic(output / f"controller-{index:03d}.log")
            closure = {"closed": True, "controller_failure": type(error).__name__}
            result = {"schema_version": 1, "task_id": task["task_id"], "status": "failed",
                      "task_config_sha256": sha(canonical(task)),
                      "protocol_sha256": sha(canonical(protocol)),
                      "failure": {"phase": "controller_or_implementation_validation", "error_type": type(error).__name__}}
        row = {"task_id": task["task_id"], "closure": closure, "result": result}
        name = f"task-{index:03d}.json"
        directory = output / f"input-{index:03d}"
        controller_log = output / f"controller-{index:03d}.log"
        artifact_bytes = _directory_bytes(directory) if directory.exists() else 0
        if controller_log.exists():
            artifact_bytes += controller_log.stat().st_size
        projected_total = artifact_bytes + len(canonical(row)) + 1
        limit = protocol["prediction"]["max_output_mib"] * 1024**2
        if projected_total > limit:
            result = {"schema_version": 1, "task_id": task["task_id"], "status": "failed",
                      "task_config_sha256": sha(canonical(task)),
                      "protocol_sha256": sha(canonical(protocol)),
                      "failure": {"phase": "total_task_artifacts", "error_type": "output_limit"}}
            row = {"task_id": task["task_id"], "closure": closure, "result": result,
                   "retained_child_artifacts": True, "projected_original_output_bytes": projected_total}
        save(output / name, row)
        rows.append({"task_id": task["task_id"], "filename": name,
                     "sha256": sha((output / name).read_bytes()),
                     "task_config_sha256": sha(canonical(task)), "status": result["status"],
                     "task_artifact_bytes": artifact_bytes + (output / name).stat().st_size,
                     "output_limit_bytes": limit,
                     "output_limit_exceeded": artifact_bytes + (output / name).stat().st_size > limit,
                     "artifacts": [{"filename": p.relative_to(output).as_posix(),
                                    "sha256": sha(p.read_bytes()), "bytes": p.stat().st_size}
                                   for p in sorted((output / f"input-{index:03d}").rglob("*"))
                                   if p.is_file()]})
    try:
        validate_protocol(protocol, repository)
        implementation_unchanged = True
    except Exception:
        implementation_unchanged = False
    seal = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
            "classification": "all-selected pre-target static prediction seal; not authentication",
            "all_selected_count": len(tasks), "rows": rows,
            "predicted_count": sum(row["status"] == "predicted" for row in rows),
            "failed_count": sum(row["status"] != "predicted" for row in rows),
            "manifest_sha256": sha(canonical(manifest)), "protocol_sha256": sha(canonical(protocol)),
            "saved_manifest_file_sha256": sha((output / "manifest.json").read_bytes()),
            "saved_protocol_file_sha256": sha((output / "protocol.json").read_bytes()),
            "implementation_sha256": protocol["implementation_sha256"],
            "implementation_unchanged": implementation_unchanged,
            "total_study_bytes_before_seal": _directory_bytes(output),
            "output_cap_scope": "per-task child directory, controller diagnostic and wrapper; shared manifest/protocol/seal separate",
            "all_selected_rows_sealed": True, "target_source_imported": False,
            "target_interpreter_launched": False, "mature_research_established": False,
            "limits": ["hash binding is not independent approval or proof of unseen exposure",
                       "environment declarations are bound, not target-import verified",
                       "static timings are not target execution performance"]}
    save(output / "SEAL.json", seal)
    return seal


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, help="Reviewed private manifest / 已审私有清单")
    parser.add_argument("--manifest-sha256", help="Exact input-file SHA / 输入文件精确SHA")
    parser.add_argument("--protocol", type=Path, help="Frozen protocol / 固定协议")
    parser.add_argument("--protocol-sha256", help="Exact input-file SHA / 输入文件精确SHA")
    parser.add_argument("--output", type=Path, help="New private output / 新私有输出")
    parser.add_argument("--child-request", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--child-request-sha256", help=argparse.SUPPRESS)
    parser.add_argument("--child-output", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.child_request is not None:
        raw = _absolute(args.child_request).read_bytes()
        if sha(raw) != args.child_request_sha256 or args.child_output is None:
            raise ValueError("child request identity changed")
        request = json.loads(raw)
        policy = validate_protocol(request["protocol"], Path(request["repository"]))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_CPU, (policy["cpu_seconds"], policy["cpu_seconds"]))
        child_output = _absolute(args.child_output)
        result = predict_task(request["task"], request["protocol"],
                              repository=Path(request["repository"]),
                              diagnostic_path=child_output.parent / "diagnostic.log")
        projected = _directory_bytes(child_output.parent) + len(canonical(result)) + 1
        if projected > policy["max_output_mib"] * 1024**2:
            result = {"schema_version": 1, "task_id": request["task"].get("task_id"),
                      "task_config_sha256": sha(canonical(request["task"])),
                      "protocol_sha256": sha(canonical(request["protocol"])), "status": "failed",
                      "failure": {"phase": "child_serialization", "error_type": "output_limit"},
                      "projected_original_output_bytes": projected}
        save(child_output, result)
        return 0
    if any(value is None for value in (args.manifest, args.protocol, args.output,
                                       args.manifest_sha256, args.protocol_sha256)):
        parser.error("manifest/protocol/output and both exact file hashes are required")
    raw_manifest, raw_protocol = _absolute(args.manifest).read_bytes(), _absolute(args.protocol).read_bytes()
    if sha(raw_manifest) != args.manifest_sha256 or sha(raw_protocol) != args.protocol_sha256:
        raise ValueError("reviewed input file identity changed")
    result = predict(json.loads(raw_manifest), json.loads(raw_protocol), args.output,
                     repository=Path(__file__).resolve().parents[2])
    print(json.dumps({"all_selected": result["all_selected_count"],
                      "predicted": result["predicted_count"], "failed": result["failed_count"],
                      "seal_file_sha256": sha((args.output / "SEAL.json").read_bytes())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
