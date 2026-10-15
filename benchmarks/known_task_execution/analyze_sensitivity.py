"""Reanalyse sealed scalar pilot scores / 重算已封存标量，不执行上游程序。

Real inputs require a separately sealed final eligibility ledger and approval.
真实输入必须先有最终资格清单和批准文件；本模块不重跑检索、不生成修复。
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import sys
import time


SHA = re.compile(r"[0-9a-f]{64}\Z")
METHODS = ("bm25_windows", "bm25_declarations", "anchors_only", "graph_expand",
           "window_expand", "file_expand")
BUDGETS = (8000, 16000, 32000)
INPUT_LIMIT = 16 * 1024**2


@dataclass(frozen=True)
class VerifiedBytes:
    """An immutable verified read / 同一份已核验字节供解析和来源记录使用。"""
    raw: bytes
    sha256: str


def read_verified(path, expected=None, expected_size=None, limit=INPUT_LIMIT):
    """Read at most limit+1 bytes once, hash that read / 单次有界读取后核验。"""
    if type(limit) is not int or limit < 0:
        raise ValueError("invalid byte limit")
    with Path(path).open("rb") as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("input exceeds bounded byte limit")
    if expected_size is not None and (type(expected_size) is not int or len(raw) != expected_size):
        raise ValueError("input byte size mismatch")
    actual = hashlib.sha256(raw).hexdigest()
    if expected is not None and (not isinstance(expected, str) or not SHA.fullmatch(expected) or expected != actual):
        raise ValueError("input SHA256 mismatch")
    return VerifiedBytes(raw=raw, sha256=actual)


def digest(path):
    return read_verified(path).sha256


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key: " + key)
        out[key] = value
    return out


def parse_verified_json(verified):
    """Parse only already verified immutable bytes / 不重新读取源文件。"""
    def nonfinite(value):
        raise ValueError("nonfinite JSON number: " + value)
    def number(value):
        result = float(value)
        if not math.isfinite(result):
            return nonfinite(value)
        return result
    return json.loads(verified.raw, object_pairs_hook=_pairs, parse_constant=nonfinite, parse_float=number)


def read_json(path, expected=None):
    """Bounded read-and-parse convenience / 有界读取并解析。"""
    return parse_verified_json(read_verified(path, expected))


def read_bindings(root, bindings):
    """Keep raw bytes and digest of every fixed input / 固定输入只读取一次。"""
    bound = {}
    for record in bindings:
        rel = Path(record["relative_path"])
        if rel.is_absolute() or ".." in rel.parts or not rel.name:
            raise ValueError("unsafe original input binding")
        if rel.name in bound:
            raise ValueError("duplicate original input binding basename")
        bound[rel.name] = read_verified(Path(root) / rel, record["sha256"], record["bytes"])
    return bound


def hash_value(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ValueError("invalid SHA256")
    return value


def integer(value):
    if type(value) is not int or value < 0:
        raise ValueError("expected nonnegative integer")
    return value


def utc(value):
    if not isinstance(value, str):
        raise ValueError("missing UTC timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    if parsed.utcoffset() != timedelta(0):
        raise ValueError("timestamp must have explicit UTC zero offset")
    return parsed.astimezone(timezone.utc)


def finite_equal(value, rational):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("nonfinite or nonnumeric stored metric")
    if abs(float(value) - float(rational)) > 1e-12:
        raise ValueError("stored metric disagrees with frozen counts")


def validate_scores(data, identities, methods=METHODS, budgets=BUDGETS):
    """Validate every original cell; no failed predictions removed / 不丢弃预测失败。"""
    expected = {(m, b) for m in methods for b in budgets}
    tasks = {}
    for task in data["tasks"]:
        name = task["instance_id"]
        if name in tasks or name not in identities or task["repo"] != identities[name]["repo"]:
            raise ValueError("duplicate/unknown/mismatched score task")
        cells, targets = {}, set()
        for cell in task["scores"]:
            key = (cell["method"], cell["budget"])
            if key not in expected or key in cells:
                raise ValueError("duplicate/unknown method-budget cell")
            line = cell["line"]
            pred, target, hit = (integer(line[k]) for k in ("predicted", "target", "intersection"))
            if hit > min(pred, target):
                raise ValueError("impossible intersection")
            targets.add(target)
            if target == 0:
                if line["status"] != "no_target" or hit or any(line[k] is not None for k in ("f1", "recall", "precision")):
                    raise ValueError("undefined labels must remain null")
                metrics = None
            else:
                if line["status"] != "scored":
                    raise ValueError("targetable label missing score status")
                metrics = {"f1": Fraction(2 * hit, pred + target),
                           "recall": Fraction(hit, target),
                           "precision": Fraction(hit, pred) if pred else Fraction(0)}
                for metric, number in metrics.items():
                    finite_equal(line[metric], number)
            cells[key] = metrics
        if set(cells) != expected or len(targets) != 1:
            raise ValueError("missing cell or method-dependent target denominator")
        tasks[name] = {"repo": task["repo"], "cells": cells,
                       "targetable": next(iter(targets)) > 0,
                       "prediction_status": task["prediction_status"]}
    if set(tasks) != set(identities):
        raise ValueError("missing original task")
    return tasks


def validate_eligibility(ledger, identities, protocol_sha, scores_sha, expected_test_counts=None):
    """Choose latest STARTED condition, including closed failures / 最新已启动条件不能择优。"""
    for flag in ("final_for_secondary_analysis", "all_started_conditions_closed", "all_original_tasks_included"):
        if ledger.get(flag) is not True:
            raise ValueError("final execution snapshot not sealed")
    snapshot_time = utc(ledger["snapshot_frozen_utc"])
    if ledger["original_pilot_protocol_sha256"] != protocol_sha or ledger["original_pilot_scores_sha256"] != scores_sha:
        raise ValueError("eligibility ledger primary binding mismatch")
    for key in ("original_task_execution_contract_sha256", "frozen_execution_evidence_sha256",
                "source_and_protocol_binding_validation_sha256"):
        hash_value(ledger[key])
    selected, rows, counts = set(), {}, [0, 0]
    for task in ledger["tasks"]:
        name = task["instance_id"]
        if name in rows or name not in identities:
            raise ValueError("duplicate/unknown execution task")
        for field in ("repo", "base_commit"):
            if task[field] != identities[name][field]:
                raise ValueError("execution task identity mismatch")
        for i, key in enumerate(("original_F2P", "original_P2P")):
            counts[i] += integer(task[key])
        conditions, eligible = {}, []
        for condition in task["conditions"]:
            key = condition["condition_key"]
            if key in conditions:
                raise ValueError("duplicate condition identity")
            conditions[key] = condition
            if type(condition["approved"]) is not bool or type(condition["started"]) is not bool:
                raise ValueError("invalid condition boolean")
            stamp = utc(condition["protocol_frozen_utc"])
            if stamp > snapshot_time:
                raise ValueError("condition newer than sealed snapshot")
            hash_value(condition["protocol_sha256"])
            if condition["started"] and condition["state"] != "closed":
                raise ValueError("started condition still running/unresolved")
            if not condition["started"] and condition["state"] != "not_started":
                raise ValueError("unstarted candidate has ambiguous state")
            if condition["qualification_status"] == "finite_qualified":
                if not (condition["approved"] and condition["started"] and condition["pair_records_complete"] is True):
                    raise ValueError("partial/unstarted condition cannot qualify")
                for binding in ("qualification_record_sha256_or_null", "environment_manifest_sha256_or_null", "source_identity_manifest_sha256_or_null"):
                    hash_value(condition[binding])
            if condition["approved"] and condition["started"]:
                eligible.append((stamp, condition["run_id"], key))
        latest = conditions[max(eligible)[2]] if eligible else None
        latest_key = latest["condition_key"] if latest else None
        if task["latest_approved_started_condition_key_or_null"] != latest_key:
            raise ValueError("latest condition mismatch/best-environment fallback")
        is_qualified = latest is not None and latest["qualification_status"] == "finite_qualified"
        if type(task["finite_qualified"]) is not bool or task["finite_qualified"] != is_qualified:
            raise ValueError("task qualification differs from latest condition")
        if (task["final_status"] == "finite_qualified") != is_qualified:
            raise ValueError("task status disagrees with qualification")
        if not is_qualified and not task["exclusion_reason_or_null"]:
            raise ValueError("nonqualified task needs explicit reason")
        if is_qualified:
            selected.add(name)
        rows[name] = task
    if set(rows) != set(identities) or (expected_test_counts is not None and tuple(counts) != tuple(expected_test_counts)):
        raise ValueError("original execution task/test denominators changed")
    return selected, rows


def average(values):
    values = list(values)
    return sum(values, Fraction(0)) / len(values) if values else None


def numeric(value):
    return None if value is None else float(value)


def view(tasks, names, repos, methods=METHODS, budgets=BUDGETS):
    """Task means then equal repository means / 先仓库内均值，再仓库等权均值。"""
    cells, exact = [], {}
    for method in methods:
        for budget in budgets:
            per_repo = []
            for repo in repos:
                ids = sorted(name for name in names if tasks[name]["repo"] == repo)
                valid = [tasks[name]["cells"][method, budget] for name in ids
                         if tasks[name]["cells"][method, budget] is not None]
                means = {k: average(v[k] for v in valid) for k in ("f1", "recall")}
                exact[repo, method, budget] = means
                per_repo.append({"repo": repo, "tasks": len(ids), "targetable": len(valid),
                                 "no_target": len(ids) - len(valid),
                                 **{k: numeric(v) for k, v in means.items()}})
            macro = {k: average(exact[r, method, budget][k] for r in repos
                                if exact[r, method, budget][k] is not None) for k in ("f1", "recall")}
            exact[None, method, budget] = macro
            cells.append({"method": method, "budget": budget, "per_repo": per_repo,
                          "contributing_repositories": [r for r in repos if exact[r, method, budget]["f1"] is not None],
                          "repo_macro": {k: numeric(v) for k, v in macro.items()}})
    comparisons = []
    for budget in budgets:
        for baseline in ("bm25_windows", "bm25_declarations"):
            effects, counts = [], Counter()
            for repo in list(repos) + [None]:
                numbers = {}
                for metric in ("f1", "recall"):
                    g, b = exact[repo, "graph_expand", budget][metric], exact[repo, baseline, budget][metric]
                    delta = None if g is None or b is None else g - b
                    numbers[metric + "_difference"] = numeric(delta)
                    numbers[metric + "_exact_ratio"] = None if delta is None else str(delta)
                    numbers[metric + "_sign"] = "undefined" if delta is None else "negative" if delta < 0 else "positive" if delta > 0 else "tie"
                if repo is not None:
                    counts[numbers["f1_sign"]] += 1
                    effects.append({"repo": repo, **numbers})
                else:
                    macro_numbers = numbers
            comparisons.append({"budget": budget, "baseline": baseline,
                                "per_repo": effects, "f1_repo_sign_counts": dict(counts), **macro_numbers})
    focus = [r for r in comparisons if r["budget"] == 16000]
    signs = [r[k + "_sign"] for r in focus for k in ("f1", "recall")]
    joint = None if len(focus) != 2 or "undefined" in signs else all(s == "negative" for s in signs)
    return {"method_budget_cells": cells, "comparisons_all_budgets": comparisons,
            "focus_16000": focus,
            "joint_strict_negative_F1_and_recall_both_baselines":
                joint}


def summarize(tasks, selected, eligibility_rows, methods=METHODS, budgets=BUDGETS):
    repos = sorted({t["repo"] for t in tasks.values()})
    all_ids = set(tasks)
    contributors = {tasks[n]["repo"] for n in selected if tasks[n]["targetable"]}
    common_repo_ids = {n for n in tasks if tasks[n]["repo"] in contributors}
    denominators, membership = [], []
    for repo in repos:
        ids = {n for n in tasks if tasks[n]["repo"] == repo}
        valid = ids & selected
        denominators.append({"repo": repo, "original_tasks": len(ids),
            "finite_qualified_tasks": len(valid),
            "nonqualified_tasks_by_reason": dict(Counter(eligibility_rows[n]["exclusion_reason_or_null"] for n in ids - selected)),
            "original_line_targetable_tasks": sum(tasks[n]["targetable"] for n in ids),
            "qualified_line_targetable_tasks": sum(tasks[n]["targetable"] for n in valid),
            "qualified_no_target_tasks": sum(not tasks[n]["targetable"] for n in valid),
            "label_error_or_missing_tasks": 0, "missing_score_cells": 0,
            "prediction_failure_tasks_retained": sum(tasks[n]["prediction_status"] != "predicted" for n in ids),
            "contributing_to_subset_macro": repo in contributors})
    for name in sorted(tasks):
        r = eligibility_rows[name]
        membership.append({"instance_id": name, "repo": tasks[name]["repo"],
            "finite_qualified": name in selected, "line_targetable": tasks[name]["targetable"],
            "line_label_state": "scored" if tasks[name]["targetable"] else "no_target_undefined",
            "latest_condition_key": r["latest_approved_started_condition_key_or_null"],
            "status": r["final_status"], "exclusion_reason": r["exclusion_reason_or_null"]})
    return {"original_tasks": len(tasks), "qualified_subset_tasks": len(selected),
            "per_repository_denominators": denominators, "membership": membership,
            "all39_reference_recomputed": view(tasks, all_ids, repos, methods, budgets),
            "latest_finite_qualified_secondary": view(tasks, selected, repos, methods, budgets),
            "all39_common_repository_composition_diagnostic": view(tasks, common_repo_ids, repos, methods, budgets),
            "new_holdout": False, "new_primary": False, "mature_research_established": False,
            "SUT_or_retrieval_executed": False,
            "limits": ["Post hoc selected known tasks, local-resource/test/dependency selection bias.",
                       "No necessary-context, retrieval benefit or generated-repair evidence.",
                       "87/5842 supplied test labels and retries are not independent tasks."]}


def main():
    arg = argparse.ArgumentParser(description=__doc__)
    for name in ("protocol", "protocol-sha256", "pilot-repository-root", "eligibility-ledger",
                 "eligibility-sha256", "approval", "approval-sha256", "run-id", "output"):
        arg.add_argument("--" + name, required=True, help="sealed input/identifier / 封存输入或标识")
    args = arg.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", args.run_id):
        raise ValueError("invalid analysis run identifier")
    started = time.monotonic()
    protocol_input = read_verified(args.protocol, args.protocol_sha256)
    approval_input = read_verified(args.approval, args.approval_sha256)
    program_input = read_verified(__file__)
    protocol = parse_verified_json(protocol_input)
    approval = parse_verified_json(approval_input)
    if approval.get("action") != "authorize_one_final_secondary_calculation" or approval.get("allow_real_inputs") is not True:
        raise ValueError("missing final calculation authorization")
    for key, value in (("protocol_sha256", protocol_input.sha256), ("eligibility_ledger_sha256", args.eligibility_sha256),
                       ("analysis_program_sha256", program_input.sha256)):
        if approval.get(key) != value:
            raise ValueError("approval fingerprint mismatch")
    if "CURRENT" in Path(args.eligibility_ledger).name.upper():
        raise ValueError("mutable CURRENT ledger forbidden")
    ledger_input = read_verified(args.eligibility_ledger, args.eligibility_sha256)
    ledger = parse_verified_json(ledger_input)
    root = Path(args.pilot_repository_root)
    bound = read_bindings(root, protocol["original_primary_immutable"]["source_bindings"])
    original_protocol = parse_verified_json(bound["protocol.json"])
    identities = {r["instance_id"]: r for r in original_protocol["selection"]["tasks"]}
    if len(identities) != 39 or tuple(original_protocol["methods"]) != METHODS or tuple(original_protocol["budgets"]) != BUDGETS:
        raise ValueError("original39/6/3 contract changed")
    scores = parse_verified_json(bound["scores.json"])
    tasks = validate_scores(scores, identities)
    selected, eligibility = validate_eligibility(ledger, identities, bound["protocol.json"].sha256,
                                                 bound["scores.json"].sha256, (87, 5842))
    result = summarize(tasks, selected, eligibility)
    result["run_id"] = args.run_id
    frozen_summary = parse_verified_json(bound["summary.json"])
    reference = {(r["method"], r["budget"]): r for r in frozen_summary["macro"]}
    for cell in result["all39_reference_recomputed"]["method_budget_cells"]:
        for key in ("f1", "recall"):
            old = reference[cell["method"], cell["budget"]]["line"][key]
            new = cell["repo_macro"][key]
            if old is None or new is None:
                if old is not new:
                    raise ValueError("all39 undefined reference changed")
            elif abs(old - new) > 1e-12:
                raise ValueError("all39 original primary reference changed")
    result["provenance"] = {"recorded_utc": datetime.now(timezone.utc).isoformat(),
        "analysis_program_sha256": program_input.sha256, "protocol_sha256": protocol_input.sha256,
        "final_eligibility_sha256": ledger_input.sha256, "approval_sha256": approval_input.sha256,
        "original_scores_sha256": bound["scores.json"].sha256,
        "original_summary_sha256": bound["summary.json"].sha256,
        "verified_original_inputs": {name: {"sha256": value.sha256, "bytes": len(value.raw)}
                                     for name, value in bound.items()},
        "python": sys.version, "platform": platform.platform(), "machine": platform.machine(),
        "analysis_seconds_not_SUT_performance": time.monotonic() - started,
        "command_path_roles": [Path(__file__).name, "--protocol", "$PROTOCOL", "--protocol-sha256", args.protocol_sha256,
            "--pilot-repository-root", "$PILOT_REPOSITORY_ROOT", "--eligibility-ledger", "$FINAL_LEDGER",
            "--eligibility-sha256", args.eligibility_sha256, "--approval", "$FINAL_APPROVAL",
            "--approval-sha256", args.approval_sha256, "--run-id", args.run_id, "--output", "$NEW_OUTPUT"],
        "path_handling": "Public output records role placeholders plus exact input hashes; local paths are not scientific data."}
    target = Path(args.output)
    output_raw = (json.dumps(result, indent=2, allow_nan=False) + "\n").encode("utf8")
    with target.open("xb") as handle:
        handle.write(output_raw)
    print(json.dumps({"status": "secondary_scalar_reanalysis_completed",
                      "output_sha256": hashlib.sha256(output_raw).hexdigest()}))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        raise SystemExit('Secondary analysis failed / 次级分析失败: ' + str(error)) from error
