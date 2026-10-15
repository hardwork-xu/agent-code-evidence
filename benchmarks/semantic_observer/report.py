"""Recompute a pinned public observation bundle / 重算固定公开观测包。

Only finite, derived pre-op binding hypotheses are scored. Source identity is
not an immutable-runtime-value promise; disagreement is not a whole-graph bug.
只计分有限的派生绑定假设；不推断完整语义、修复成功、速度优势或研究成熟度。
The caller must supply the independently recorded INDEX byte SHA256. A hash
checks identity, not authenticity, source licensing or independent validation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
from statistics import median
import types


METHODS = ("currentfresh", "whole_guard", "selective", "always_abstain")
ROLES = {"base_tests": "before", "fixed_tests": "after"}
DERIVED = {"SUMMARY.json", "REPORT.md", "REPORT_zh.md"}
REQUIRED_BINDINGS = {
    "benchmarks/semantic_observer/score.py",
    "benchmarks/semantic_observer/run.py",
    "benchmarks/semantic_observer/methods.py",
    "benchmarks/semantic_observer/observer.py",
    "benchmarks/semantic_observer/worker.py",
    "benchmarks/known_task_execution/worker.py",
}
COUNT_KEYS = (
    "all_retained_sites", "all_retained_events",
    "observed_primitive_module_global_sites", "observed_primitive_module_global_events",
    "accepted_primitive_sites", "accepted_primitive_events",
    "matching_only_primitive_sites", "mismatching_primitive_sites",
    "mixed_match_mismatch_sites", "matching_primitive_events", "mismatching_primitive_events",
)


def canonical(value):
    """Finite deterministic UTF-8 JSON / 有限、确定的 UTF-8 JSON。"""
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _sha(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("invalid SHA256 / 无效 SHA256")
    return value


def _integer(value, lower=0, upper=1000000):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError("invalid integer / 无效整数")
    return value


def _object(value):
    if type(value) is not dict:
        raise ValueError("expected JSON object / 需要 JSON 对象")
    return value


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key / 重复 JSON 键")
        result[key] = value
    return result


def _load(raw):
    def constant(_):
        raise ValueError("non-finite JSON / 非有限 JSON")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                       parse_constant=constant)
    canonical(value)  # Reject exponent overflow as well as NaN/Infinity tokens.
    return value


def _relative(name):
    if (type(name) is not str or not name or "\\" in name or "\x00" in name
            or name != PurePosixPath(name).as_posix()
            or PurePosixPath(name).is_absolute()
            or any(part in {".", ".."} for part in name.split("/"))):
        raise ValueError("unsafe relative path / 不安全的相对路径")
    return name


def _file(root, name):
    _relative(name)
    candidate = root / name
    current = root
    for part in name.split("/"):
        current = current / part
        if current.is_symlink():
            raise ValueError("symlink forbidden / 禁止符号链接")
    if not candidate.is_file() or not candidate.resolve().is_relative_to(root):
        raise ValueError("missing or escaped file / 文件缺失或越界")
    return candidate


def validate_bundle(bundle, expected_index_sha256):
    """Require exact indexed bytes and file set / 核验精确字节及文件集合。"""
    _sha(expected_index_sha256)
    bundle = Path(bundle)
    if bundle.is_symlink():
        raise ValueError("bundle symlink forbidden")
    bundle = bundle.resolve(strict=True)
    index_raw = _file(bundle, "INDEX.json").read_bytes()
    if digest(index_raw) != expected_index_sha256:
        raise ValueError("INDEX SHA mismatch / INDEX 哈希不符")
    index = _object(_load(index_raw))
    if type(index.get("schema_version")) is not int or index["schema_version"] != 1:
        raise ValueError("unsupported INDEX schema")
    count = _integer(index.get("all_selected_tasks"), 1, 10000)
    if type(index.get("run_id")) is not str or not index["run_id"]:
        raise ValueError("missing run identity")
    if type(index.get("files")) is not list:
        raise ValueError("missing indexed files")
    files = {}
    for row in index["files"]:
        row = _object(row)
        if set(row) != {"path", "sha256", "bytes"}:
            raise ValueError("unexpected index entry fields")
        name = _relative(row["path"])
        if name in files or name in DERIVED | {"INDEX.json"}:
            raise ValueError("duplicate or derived indexed file")
        size = _integer(row["bytes"], 0, 256 * 1024**2)
        raw = _file(bundle, name).read_bytes()
        if len(raw) != size or digest(raw) != _sha(row["sha256"]):
            raise ValueError("indexed file bytes/SHA mismatch: " + name)
        files[name] = _load(raw)
    expected = {"protocol.json", "provenance.json"} | {
        f"task-{index:03d}.json" for index in range(count)}
    if set(files) not in (expected, expected | {"calibration.json"}):
        raise ValueError("incorrect indexed file set")
    actual = set()
    for path in bundle.rglob("*"):
        if path.is_symlink() or not path.is_file():
            raise ValueError("unexpected directory or symlink")
        actual.add(path.relative_to(bundle).as_posix())
    if not set(files) | {"INDEX.json"} <= actual or actual - set(files) - {"INDEX.json"} - DERIVED:
        raise ValueError("unindexed bundle assets / 存在未登记文件")
    return index, files


def _frozen_modules(protocol, repository):
    """Verify every source pin before loading scoring code / 导入计分前核验全部源码。"""
    repository = Path(repository).resolve(strict=True)
    bindings = _object(protocol.get("implementation_sha256"))
    if not REQUIRED_BINDINGS <= set(bindings):
        raise ValueError("protocol lacks frozen scoring/execution bindings")
    sources = {}
    for name, expected in bindings.items():
        path = _file(repository, name)
        if path.stat().st_size > 4 * 1024**2:
            raise ValueError("frozen source exceeds report read cap")
        with path.open("rb") as stream:
            raw = stream.read(4 * 1024**2 + 1)
        if len(raw) > 4 * 1024**2:
            raise ValueError("frozen source exceeds report read cap")
        if digest(raw) != _sha(expected):
            raise ValueError("frozen implementation changed: " + name)
        sources[name] = raw
    if sum(map(len, sources.values())) > 64 * 1024**2:
        raise ValueError("frozen source set exceeds report read cap")
    modules = []
    for name in ("run", "score"):
        path = repository / f"benchmarks/semantic_observer/{name}.py"
        modules.append(_execute_verified(name, sources[path.relative_to(repository).as_posix()], path))
    modules[0].validate_protocol(protocol, repository)
    return modules


def _execute_verified(name, source, path):
    """Execute the retained verified bytes, never reopen code / 只执行已核验字节。"""
    module = types.ModuleType("_semantic_report_frozen_" + name)
    module.__file__ = str(path)
    exec(compile(source, str(path), "exec", dont_inherit=True), module.__dict__)
    return module


def _gates(protocol, count):
    if (type(protocol.get("schema_version")) is not int or protocol["schema_version"] != 1
            or protocol.get("all_selected_tasks") != count
            or type(protocol.get("all_selected_tasks")) is not int):
        raise ValueError("protocol task denominator mismatch")
    gates = _object(protocol.get("primary_gates"))
    required = {"all_selected_macro_site_coverage_min", "invalid_or_zero_denominator_coverage",
                "max_mismatching_accepted_sites", "predictions_stable_across_repeats",
                "qualified_task_requires_both_roles", "qualified_tasks_required",
                "tasks_with_accepted_sites_min", "zero_accept_accuracy"}
    if set(gates) != required:
        raise ValueError("missing or unexpected primary gates")
    threshold = gates["all_selected_macro_site_coverage_min"]
    if (type(threshold) not in {float, int} or not math.isfinite(threshold)
            or not 0 <= threshold <= 1
            or type(gates["invalid_or_zero_denominator_coverage"]) is not int
            or gates["invalid_or_zero_denominator_coverage"] != 0
            or gates["zero_accept_accuracy"] is not None
            or gates["predictions_stable_across_repeats"] is not True
            or gates["qualified_task_requires_both_roles"] is not True):
        raise ValueError("unsupported gate interpretation")
    _integer(gates["max_mismatching_accepted_sites"])
    if _integer(gates["qualified_tasks_required"], 1, count) != count:
        raise ValueError("all selected tasks must remain required")
    _integer(gates["tasks_with_accepted_sites_min"], 1, count)
    prediction = _object(protocol.get("prediction"))
    repeats = _integer(prediction.get("repeats"), 1, 100)
    return gates, repeats


def _parity(run, role):
    plain, traced = role["plain"], role["traced"]
    result = run.paired_parity(plain, traced)
    qualifications = {
        kind: run.condition_qualified(role[kind], _object(role[kind + "_closure"]))
        for kind in ("plain", "traced")}
    result["condition_qualification"] = qualifications
    result["checks"] = {**result.get("checks", {}), "closed_regular_conditions":
                         all(row["passed"] for row in qualifications.values())}
    result["passed"] = result["passed"] and result["checks"]["closed_regular_conditions"]
    if canonical(result) != canonical(role["parity"]):
        raise ValueError("stored parity/qualification differs from recomputation")
    return result


def _hypothesis_digest(versions):
    # Exact frozen methods._semantic_key projection; graph closure is separate.
    # 与固定方法的假设投影一致；完整图另行报告。
    return digest(canonical({version: [
        {key: value for key, value in fact.items()
         if key not in {"supporting_graphs", "complete_graph"}}
        for fact in row["facts"]] for version, row in versions.items()}))


def _prediction_checks(prediction, repeats):
    if type(prediction) is not dict or set(_object(prediction.get("methods"))) != set(METHODS):
        raise ValueError("all four actual methods required")
    checks = {}
    for name in METHODS:
        record = _object(prediction["methods"][name])
        runs = record.get("runs")
        if (type(runs) is not list or [row.get("repeat") for row in runs] != list(range(repeats))
                or any(type(row.get("repeat")) is not int for row in runs)):
            raise ValueError("prediction repeats missing, reordered or duplicated")
        if name == "always_abstain" and any(version["facts"] for row in runs
                                             for version in row["versions"].values()):
            raise ValueError("always-abstain must contain zero hypotheses")
        digests = [_hypothesis_digest(row["versions"]) for row in runs]
        if any(row.get("semantic_output_sha256") != value for row, value in zip(runs, digests)):
            raise ValueError("stored hypothesis digest mismatch")
        stable = len(set(digests)) == 1
        if record.get("repeats_semantically_equal") is not stable:
            raise ValueError("stored prediction stability differs from recomputation")
        graphs = [digest(canonical({role: row["graphs"] for role, row in run["versions"].items()}))
                  for run in runs]
        checks[name] = {"hypotheses_stable": stable, "hypothesis_sha256": digests,
                        "graph_projection_stable": len(set(graphs)) == 1}
    return checks


def _test_changes(run, role_rows):
    before = role_rows["base_tests"]["plain"]
    after = role_rows["fixed_tests"]["plain"]
    if before is None or after is None:
        return {"available": False, "generated_repair_success": False}
    events = [run.normalized_phases(result) for result in (before, after)]
    states = [{}, {}]
    for groups, rows in zip(states, events):
        for row in rows:
            groups.setdefault((row["nodeid"], row["phase"]), []).append(row)
    changes = [{"nodeid": key[0], "phase": key[1], "before": states[0].get(key, []),
                "after": states[1].get(key, [])}
               for key in sorted(set(states[0]) | set(states[1]))
               if states[0].get(key) != states[1].get(key)]
    return {"available": True, "changes": changes,
            "before_phase_events": events[0], "after_phase_events": events[1],
            "before_call_count": sum(row["phase"] == "call" for row in events[0]),
            "after_call_count": sum(row["phase"] == "call" for row in events[1]),
            "selected_equal": before["selected"] == after["selected"],
            "scope": "original developer fix diagnostic only",
            "generated_repair_success": False}


def _worker_shape(value):
    """Reject type-coerced pass flags / 拒绝类型混淆的通过标记。"""
    if value is None:
        return
    value = _object(value)
    if (type(value.get("schema_version")) is not int or value["schema_version"] != 1
            or type(value.get("observe")) is not bool
            or type(value.get("source_before_after_verified")) is not bool
            or type(value.get("pytest_exit_code")) is not int):
        raise ValueError("invalid worker flags")
    for field in ("selected", "phase_reports", "collection_errors", "missing_selectors",
                  "network_denials", "process_denials"):
        if type(value.get(field)) is not list:
            raise ValueError("invalid worker event collection")
    _integer(value.get("thread_denials"))
    if any(type(name) is not str for name in value["selected"]):
        raise ValueError("invalid selected node identity")
    for row in value["phase_reports"]:
        if (type(row) is not dict or type(row.get("nodeid")) is not str
                or row.get("phase") not in {"setup", "call", "teardown"}
                or row.get("outcome") not in {"passed", "failed", "skipped"}
                or type(row.get("wasxfail")) is not bool
                or (row.get("error_type") is not None and type(row["error_type"]) is not str)):
            raise ValueError("invalid worker phase event")


def _seconds(value):
    if value is not None and (type(value) not in {int, float}
                              or not math.isfinite(value) or value < 0):
        raise ValueError("invalid measured seconds / 无效实测秒数")
    return value


def _measurement(value):
    """Retain optional original prediction costs / 保留可选原始预测成本。"""
    if value is None:
        return None
    value = _object(value)
    if not set(value) <= {"timings_seconds", "closure", "scope",
                          "target_source_imported", "target_interpreter_launched"}:
        raise ValueError("unexpected prediction measurement field")
    if "scope" in value and type(value["scope"]) is not str:
        raise ValueError("invalid prediction timing scope")
    for flag in ("target_source_imported", "target_interpreter_launched"):
        if flag in value and value[flag] is not False:
            raise ValueError("prediction stage was not source-only")
    for number in _object(value.get("timings_seconds", {})).values():
        _seconds(number)
    closure = _object(value.get("closure", {}))
    for name in ("wall_seconds", "sampled_peak_rss_mib"):
        if name in closure:
            _seconds(closure[name])
    if "output_bytes" in closure:
        _integer(closure["output_bytes"], 0, 1024**4)
    return value


def _task(row, run, scorer, repeats):
    if type(row.get("task_id")) is not str or not row["task_id"]:
        raise ValueError("missing task identity")
    roles = row.get("roles")
    if type(roles) is not list or len(roles) != 2 or {r.get("role") for r in roles} != set(ROLES):
        raise ValueError("exactly both source roles required")
    roles = {role["role"]: role for role in roles}
    parity, observations, status_counts = {}, {}, {}
    for value in _object(row.get("raw_artifact_sha256")).values():
        _sha(value)
    for name, role in roles.items():
        _worker_shape(role["plain"])
        _worker_shape(role["traced"])
        parity[name] = _parity(run, role)
        for kind in ("plain", "traced"):
            value = role[kind]
            if value is not None and (value.get("task_id") != row["task_id"]
                    or value.get("role") != name or value.get("observe") is not (kind == "traced")):
                raise ValueError("worker task/role/instrumentation identity mismatch")
        observation = role["traced"].get("observation") if role["traced"] is not None else None
        observations[ROLES[name]] = observation
        status_counts[name] = (observation.get("counts", {}).get("status_counts", {})
                               if observation is not None else None)
    prediction = row.get("prediction")
    failure = row.get("prediction_failure")
    if (prediction is None) == (failure is None):
        raise ValueError("require exactly one prediction or retained failure")
    output = {"task_id": row["task_id"], "role_parity": parity,
              "observer_status_counts": status_counts,
              "prediction_failure": failure, "methods": {},
              "prediction_measurement": _measurement(row.get("prediction_measurement")),
              "common_preparation_seconds": _seconds(prediction.get("preparation_seconds"))
                  if prediction is not None else None,
              "original_fix_test_diagnostic": _test_changes(run, roles)}
    if prediction is None:
        for name in METHODS:
            output["methods"][name] = {"prediction_stable": False, "score_repeats_equal": None,
                "execution_qualified": all(p["passed"] for p in parity.values()),
                "qualified": False, "repeat0": None, "all_selected_site_coverage": 0,
                "repeat_checks": None, "timings_seconds": []}
        return output
    stability = _prediction_checks(prediction, repeats)
    scored = scorer.score_pair(prediction, observations,
        role_parity_valid={ROLES[name]: parity[name]["passed"] for name in ROLES})
    output["score_input_sha256"] = {"methods": scored["input_method_sha256"],
                                   "observers": scored["input_observer_sha256"]}
    for name in METHODS:
        record = scored["methods"][name]
        primary = record["runs"][0]
        execution = (all(p["passed"] for p in parity.values())
                     and all(not r["validity_errors"] for r in primary["versions"].values()))
        stable = stability[name]["hypotheses_stable"] and record["score_repeats_equal"]
        qualified = execution and stable
        coverage = primary["task"]["primitive_site_coverage"]["value"]
        output["methods"][name] = {
            "prediction_stable": stable, "score_repeats_equal": record["score_repeats_equal"],
            "execution_qualified": execution, "qualified": qualified,
            "repeat0": {"task": primary["task"], "versions": {
                role: {key: value for key, value in result.items() if key != "sites"}
                for role, result in primary["versions"].items()}},
            "all_selected_site_coverage": coverage if qualified and coverage is not None else 0,
            "repeat_checks": stability[name],
            "binding_predictions_equal_currentfresh": stability[name]["hypothesis_sha256"][0]
                == stability["currentfresh"]["hypothesis_sha256"][0],
            "timings_seconds": [item.get("timings_seconds", {})
                                for item in prediction["methods"][name]["runs"]]}
    return output


def _aggregate(tasks, name, gates):
    rows = [task["methods"][name] for task in tasks]
    raw, qualified = Counter(), Counter()
    classification = Counter()
    for row in rows:
        if row["repeat0"] is not None:
            summary = row["repeat0"]["task"]
            raw.update({key: summary[key] for key in COUNT_KEYS})
            classification.update(summary["classification_event_counts"])
            # The frozen scorer makes task metrics undefined when either role
            # has zero primitive sites. Do not silently pool around that rule.
            if row["qualified"] and summary["score_qualified"]:
                qualified.update({key: summary[key] for key in COUNT_KEYS})
    coverage = sum(row["all_selected_site_coverage"] for row in rows) / len(tasks)
    accepted_tasks = sum(bool(row["qualified"] and row["repeat0"] is not None
                              and row["repeat0"]["task"]["score_qualified"]
                              and row["repeat0"]["task"]["accepted_primitive_sites"])
                         for row in rows)
    checks = {
        "all_selected_tasks_qualified": sum(row["qualified"] for row in rows)
            == gates["qualified_tasks_required"],
        "zero_observed_disagreements": raw["mismatching_primitive_sites"]
            <= gates["max_mismatching_accepted_sites"],
        "all_selected_macro_site_coverage": coverage >= gates["all_selected_macro_site_coverage_min"],
        "tasks_with_accepted_sites": accepted_tasks >= gates["tasks_with_accepted_sites_min"],
    }
    denominator = qualified["accepted_primitive_sites"]
    return {"independent_tasks": len(tasks), "primary_repeat": 0,
        "qualified_tasks": sum(row["qualified"] for row in rows),
        "execution_qualified_tasks": sum(row["execution_qualified"] for row in rows),
        "score_qualified_tasks": sum(bool(row["qualified"] and row["repeat0"] is not None
                                          and row["repeat0"]["task"]["score_qualified"])
                                     for row in rows),
        "stable_prediction_tasks": sum(row["prediction_stable"] for row in rows),
        "tasks_with_accepted_sites": accepted_tasks,
        "raw_repeat0_counts": {key: raw[key] for key in COUNT_KEYS},
        "qualified_repeat0_counts": {key: qualified[key] for key in COUNT_KEYS},
        "classification_event_counts": dict(sorted(classification.items())),
        "all_selected_macro_site_coverage": coverage,
        "conditional_primitive_site_accuracy": {
            "numerator": qualified["matching_only_primitive_sites"], "denominator": denominator,
            "value": qualified["matching_only_primitive_sites"] / denominator if denominator else None},
        "gate_checks": checks, "primary_gate_passed": all(checks.values()) if name != "always_abstain" else None,
        "gate_applicable": name != "always_abstain"}


def analyze_bundle(bundle, expected_index_sha256, *, repository=None):
    """Validate and recompute without writing / 核验并重算，不写文件。

    Prediction failures stay in the selected-task denominator. Repetitions are
    stability checks, not independent observations. 失败保留分母；重复不扩样本。
    """
    index, files = validate_bundle(bundle, expected_index_sha256)
    protocol = _object(files["protocol.json"])
    gates, repeats = _gates(protocol, index["all_selected_tasks"])
    repository = Path(repository) if repository is not None else Path(__file__).resolve().parents[2]
    run, scorer = _frozen_modules(protocol, repository)
    tasks = [_task(_object(files[f"task-{i:03d}.json"]), run, scorer, repeats)
             for i in range(index["all_selected_tasks"])]
    if len({task["task_id"] for task in tasks}) != len(tasks):
        raise ValueError("duplicate selected task identity")
    methods = {name: _aggregate(tasks, name, gates) for name in METHODS}
    # Recheck after scoring too: these are local byte bindings, not a sandbox.
    for name, expected in protocol["implementation_sha256"].items():
        if digest(_file(repository.resolve(), name).read_bytes()) != expected:
            raise ValueError("frozen implementation changed during report")
    return {"schema_version": 1, "run_id": index["run_id"],
        "classification": protocol.get("classification"),
        "index_sha256": expected_index_sha256,
        "protocol_raw_sha256": next(r["sha256"] for r in index["files"] if r["path"] == "protocol.json"),
        "provenance_raw_sha256": next(r["sha256"] for r in index["files"] if r["path"] == "provenance.json"),
        "analysis_source_sha256": digest(Path(__file__).read_bytes()),
        "frozen_implementation_sha256": protocol["implementation_sha256"],
        "all_selected_tasks": len(tasks), "static_repeats_per_method": repeats,
        "primary_gates": gates, "methods": methods, "tasks": tasks,
        "calibration": files.get("calibration.json"),
        "policy": {"event_semantics": "pre_op_binding_not_consumed_operand",
            "independent_unit": "one selected task; sites across versions are site-by-source-role observations, not independent tests",
            "invalid_or_zero_denominator_coverage": 0, "zero_accept_accuracy": None,
            "timing": "descriptive only; all retained repetitions; no speed claim",
            "semantic_ties": "equal predictions are ties, not quality improvements",
            "scope": "finite derived binding hypotheses; not full-graph semantics",
            "new_generated_repairs": False, "mature_research_established": False,
            "source_hash_is_authentication": False}}


def _number(value):
    return "undefined / 未定义" if value is None else format(value, ".6g")


def _cell(value):
    return str(value).replace("|", "&#124;").replace("\n", " ").replace("\r", " ")


def _time(value, chinese):
    return ("未记录／未运行" if chinese else "not reported / not run") if value is None else _number(value)


def _median_ms(rows, key, repeats):
    values = [_seconds(row.get(key)) for row in rows]
    if len(values) != repeats or any(value is None for value in values):
        return None
    return 1000 * median(values)


def _timing_lines(summary, chinese):
    """Keep method-only, shared and controller boundaries distinct / 分开成本边界。"""
    lines = ["", "描述性耗时（毫秒）" if chinese else "Descriptive timing (milliseconds)", "",
        ("每个方法单元格为全部保留重复的中位数。缺少任何一次计时则不计算中位数；逐次计时仍保留于 SUMMARY.json。"
         if chinese else "Each method cell is the median of all retained repeats. A missing repeat measurement makes the median unavailable; every raw repeat remains in SUMMARY.json."), "",
        ("| 任务 | 方法 | 初始化中位数 | 捕获中位数 | 回放中位数 | 方法合计中位数 |"
         if chinese else "| Task | Method | Median initialization | Median capture | Median replay | Median method total |"),
        "|---|---|---:|---:|---:|---:|"]
    for task in summary["tasks"]:
        for name in METHODS[:-1]:
            rows = task["methods"][name]["timings_seconds"]
            cells = [_time(_median_ms(rows, key, summary["static_repeats_per_method"]), chinese)
                     for key in ("initialization", "capture_including_projection",
                                 "replay_including_projection", "total_method")]
            lines.append("| " + " | ".join([_cell(task["task_id"]), name, *cells]) + " |")
    lines += ["", ("| 任务 | 源码校验与读取 | 公共准备 | 全部方法含公共准备 | 最终校验 | 子进程端到端 | 串行控制器墙钟 |"
        if chinese else "| Task | Source validation/load | Shared preparation | All methods including preparation | Final validation | Child end-to-end | Serial controller wall |"),
        "|---|---:|---:|---:|---:|---:|---:|"]
    for task in summary["tasks"]:
        measurement = task["prediction_measurement"] or {}
        timings = measurement.get("timings_seconds", {})
        values = [timings.get("source_validation_and_load"), task["common_preparation_seconds"],
                  timings.get("methods_including_preparation"), timings.get("final_validation"),
                  timings.get("end_to_end"), measurement.get("closure", {}).get("wall_seconds")]
        cells = [_time(1000 * _seconds(value) if value is not None else None, chinese) for value in values]
        lines.append("| " + " | ".join([_cell(task["task_id"]), *cells]) + " |")
    lines += ["", ("方法合计包含本方法初始化、捕获与回放及投影，不含跨方法公共准备、完整源码读取或进程成本；各列中位数不必相加等于合计中位数。公共准备只执行一次，不应逐方法重复加算。全部方法含公共准备计时覆盖三个方法的所有重复及 always-abstain 诊断。子进程端到端包含源码／实现校验、读取、全部方法和最终校验；控制器墙钟还包含子进程启动、导入及结果序列化至关闭的成本，不含此前请求准备、之后封存、公开导出或本报告生成。未记录／未运行表示计时不可得，不推断执行是否发生。这里只描述成本，不计算加速比、显著性或质量收益。"
        if chinese else "Method total includes that method's initialization, capture, replay and projection; it excludes shared preparation, full source loading and process costs. Column medians need not sum to the median total. Shared preparation runs once and must not be added once per method. All-method timing includes preparation, every repeat of the three methods, and the always-abstain diagnostic. Child end-to-end includes source/implementation validation, loading, all methods and final validation; controller wall additionally includes child startup, imports and output serialization through closure, excluding earlier request preparation and later sealing, public export or this report. Not reported / not run means timing is unavailable, not a claim about whether execution occurred. These are descriptive costs, without speed ratios, significance tests or quality gains."), ""]
    return lines


def render(summary, *, chinese=False):
    """Deterministic matching bilingual tables / 数字一致的确定性双语表格。"""
    n = summary["all_selected_tasks"]
    lines = ["# 有限绑定观测报告" if chinese else "# Finite binding observation report", "",
        ("全部选定任务" if chinese else "All selected tasks") + f": {n}; "
        + ("主计分重复" if chinese else "primary scoring repeat") + ": 0.", "",
        ("无效任务与零分母覆盖率记为 0；零接受准确率未定义。重复仅检验稳定性，不扩充任务数。"
         if chinese else "Invalid tasks and zero denominators contribute zero coverage; zero accepts have undefined accuracy. Repeats check stability and do not increase the task count."), "",
        ("| 方法 | 执行与预测合格任务 | 可计分任务 | 接受任务 | 原始接受站点×源码角色 | 原始不一致站点×源码角色 | 全任务宏覆盖率 | 条件站点准确率 | 主门槛 |"
         if chinese else "| Method | Execution/prediction qualified | Score-qualified tasks | Tasks accepting | Raw accepted site×source-role observations | Raw mismatching site×source-role observations | All-task macro coverage | Conditional site accuracy | Primary gate |"),
        "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    for name in METHODS:
        row = summary["methods"][name]
        gate = row["primary_gate_passed"]
        label = ("不适用" if chinese else "N/A") if gate is None else (
            ("通过" if gate else "未通过") if chinese else ("passed" if gate else "not passed"))
        lines.append(f"| {name} | {row['qualified_tasks']}/{n} | {row['score_qualified_tasks']}/{n} | {row['tasks_with_accepted_sites']} | "
            f"{row['raw_repeat0_counts']['accepted_primitive_sites']} | "
            f"{row['raw_repeat0_counts']['mismatching_primitive_sites']} | "
            f"{_number(row['all_selected_macro_site_coverage'])} | "
            f"{_number(row['conditional_primitive_site_accuracy']['value'])} | {label} |")
    lines += ["", ("| 任务 | 方法 | 配对与预测合格 | 原始接受站点 | 原始不一致站点 | 全任务覆盖率贡献 |"
        if chinese else "| Task | Method | Pair/prediction qualified | Raw accepted sites | Raw mismatching sites | All-task coverage contribution |"),
        "|---|---|---|---:|---:|---:|"]
    for task in summary["tasks"]:
        for name in METHODS:
            row = task["methods"][name]
            primary = row["repeat0"]["task"] if row["repeat0"] is not None else None
            lines.append(f"| {_cell(task['task_id'])} | {name} | {str(row['qualified']).lower()} | "
                f"{primary['accepted_primitive_sites'] if primary is not None else 'N/A'} | "
                f"{primary['mismatching_primitive_sites'] if primary is not None else 'N/A'} | "
                f"{_number(row['all_selected_site_coverage'])} |")
    lines += _timing_lines(summary, chinese)
    lines += ["", ("数字由 INDEX 固定的原始文件重算。执行与预测合格不表示存在可计分的 primitive 观测。原始计数可含不合格条件的诊断；条件准确率只计可计分的合格任务。站点×源码角色不是独立测试。完整状态、图前沿、重复与耗时见 SUMMARY.json。"
        if chinese else "Numbers are recomputed from INDEX-pinned inputs. Execution/prediction qualification does not imply scoreable primitive observations. Raw counts may include invalid-condition diagnostics; conditional accuracy pools only score-qualified tasks. Site×source-role observations are not independent tests. Full statuses, graph frontiers, repetitions and timings are in SUMMARY.json."), "",
        ("观测是执行前绑定，不证明操作数被消费；派生假设不一致不等于完整图失效。测试变化只描述原开发者修复。等价输出视为平局；耗时仅作描述。本报告不证明完整语义、生成修复效果、新颖性或成熟研究成果。"
         if chinese else "Observations are pre-op bindings, not proof of consumed operands; disagreement with a derived hypothesis is not a whole-graph bug. Test changes describe original developer fixes only. Equal outputs are ties and timing is descriptive. This report does not establish full semantics, generated-repair benefit, novelty or research maturity."), "",
        "INDEX SHA256: `" + summary["index_sha256"] + "`", "",
        ("报告分析源码 SHA256" if chinese else "Report analysis source SHA256")
        + ": `" + summary["analysis_source_sha256"] + "`", ""]
    return "\n".join(lines).encode("utf-8")


def report(bundle, expected_index_sha256, *, repository=None, check=False):
    """Write/check only three derived files / 仅写入或核验三个派生文件。"""
    summary = analyze_bundle(bundle, expected_index_sha256, repository=repository)
    outputs = {"SUMMARY.json": canonical(summary) + b"\n",
               "REPORT.md": render(summary), "REPORT_zh.md": render(summary, chinese=True)}
    bundle = Path(bundle)
    for name, raw in outputs.items():
        path = bundle / name
        if path.is_symlink():
            raise ValueError("derived output symlink forbidden")
        if check:
            if not path.is_file() or path.read_bytes() != raw:
                raise ValueError("generated report differs: " + name)
        else:
            path.write_bytes(raw)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True, help="Reviewed public bundle / 已审公开包")
    parser.add_argument("--expected-index-sha256", required=True, help="Independent INDEX byte SHA / 独立记录的 INDEX 字节哈希")
    parser.add_argument("--repository", type=Path, help="Checkout with exact frozen sources / 固定源码检出")
    parser.add_argument("--check", action="store_true", help="Compare retained derived bytes / 比较已有派生字节")
    args = parser.parse_args(argv)
    result = report(args.bundle, args.expected_index_sha256, repository=args.repository, check=args.check)
    print(json.dumps({"run_id": result["run_id"], "all_selected_tasks": result["all_selected_tasks"],
                      "checked": args.check}, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
