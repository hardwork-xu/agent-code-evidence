"""Independent scoring of derived value hypotheses / 派生值假设的独立计分。

No resolver, evaluator dataset, source execution or timing is used here. A match
concerns a pre-op module binding, not successful operand consumption. A mismatch
refutes the derived runtime-value hypothesis, not a product guarantee that a
whole graph is immutable or semantically sound.

不运行源码或计时；失配只反驳派生运行时值假设，不自动构成整图陈旧错误。
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
import re


ROLES = ("before", "after")
SITE_FIELDS = ("source_path", "source_sha256", "code_signature", "qualname", "function_name",
               "name", "bytecode_offset", "lineno", "end_lineno", "col_offset", "end_col_offset")
COUNT_FIELDS = ("eligible_load_global_events", "retained_observations", "retained_events",
                "dropped_observations", "uncertified_code_events", "exception_events",
                "unsupported_filename_events", "partial_position_events")
CLASSIFICATIONS = ("matching", "mismatching", "ambiguous_hypothesis", "ambiguous_owner",
    "source_sha_mismatch", "owner_span_mismatch", "unsupported_hypothesis", "unselected",
    "graph_absent", "graph_abstain", "policy_abstain", "unsupported_observed_value",
    "builtin", "missing", "uncertified_code", "unsupported_location", "unsupported_observation")


def _json(value):
    def check(item):
        kind = type(item)
        if item is None or kind is bool or kind is int or kind is str:
            return
        if kind is float and math.isfinite(item):
            return
        if kind is list:
            for child in item:
                check(child)
            return
        if kind is dict and all(type(key) is str for key in item):
            for child in item.values():
                check(child)
            return
        raise ValueError("Expected exact finite JSON data / 需要精确有限 JSON 数据")
    check(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
                      allow_nan=False).encode("ascii")


def _sha(value):
    return hashlib.sha256(_json(value)).hexdigest()


def _dict(value):
    if type(value) is not dict:
        raise ValueError("Expected JSON object / 需要 JSON 对象")
    return value


def _list(value):
    if type(value) is not list:
        raise ValueError("Expected JSON list / 需要 JSON 列表")
    return value


def _integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("Invalid count/location / 计数或位置无效")
    return value


def _digest(value):
    if type(value) is not str or re.fullmatch("[0-9a-f]{64}", value) is None:
        raise ValueError("Invalid SHA256 / SHA256 无效")
    return value


def _path(value):
    if (type(value) is not str or not value or value.startswith("/")
            or "\\" in value or ":" in value or "\x00" in value
            or any(part in {"", ".", ".."} for part in value.split("/"))):
        raise ValueError("Invalid relative source path / 相对源码路径无效")
    return value


def _value(value):
    """Validate the codec independently; do not call the observer to make truth.

    独立验证编码结构，不调用观测器或解析器生成真值。
    """
    value = _dict(value)
    status, kind = value.get("status"), value.get("type")
    if status == "unsupported":
        if (kind not in {"none", "bool", "int", "float", "str", "bytes", "other"}
                or type(value.get("reason")) is not str or not value["reason"]
                or set(value) - {"status", "type", "reason", "bits"}):
            raise ValueError("Invalid unsupported value / 不支持值的编码无效")
        if "bits" in value and (type(value["bits"]) is not str
                                or re.fullmatch("[0-9a-f]{16}", value["bits"]) is None):
            raise ValueError("Invalid float bits / 浮点字节无效")
        return value
    fields = {"none": {"value"}, "bool": {"value"}, "int": {"decimal"}, "float": {"hex"},
              "str": {"sha256", "length", "byte_length", "encoding"},
              "bytes": {"sha256", "length", "byte_length"}}
    if status != "supported" or kind not in fields or set(value) != fields[kind] | {"status", "type"}:
        raise ValueError("Invalid primitive value / 基本类型值编码无效")
    if kind == "none" and value["value"] is not None:
        raise ValueError("Invalid None value")
    if kind == "bool" and type(value["value"]) is not bool:
        raise ValueError("Invalid bool value")
    if kind == "int":
        decimal = value["decimal"]
        if (type(decimal) is not str or len(decimal) > 1235
                or re.fullmatch(r"0|-?[1-9][0-9]*", decimal) is None
                or int(decimal).bit_length() > 4096):
            raise ValueError("Invalid integer encoding")
    if kind == "float":
        text = value["hex"]
        if type(text) is not str or len(text) > 32:
            raise ValueError("Invalid float encoding")
        actual = float.fromhex(text)
        if not math.isfinite(actual) or float.hex(actual) != text:
            raise ValueError("Noncanonical/nonfinite float encoding")
    if kind in {"str", "bytes"}:
        _digest(value["sha256"])
        length, byte_length = _integer(value["length"]), _integer(value["byte_length"])
        if byte_length > 1_048_576 or length > byte_length:
            raise ValueError("Invalid primitive length")
        if kind == "bytes" and length != byte_length:
            raise ValueError("Invalid byte length")
        if kind == "str" and (value["encoding"] != "utf-8-surrogatepass"
                              or byte_length > 4 * length):
            raise ValueError("Invalid string encoding")
    return value


def _observation(report, parity):
    if report is None:
        return {"records": [], "raw_counts": None, "errors": ["observer_report_missing"],
                "input_sha256": None}
    report = _dict(report)
    if type(report.get("schema_version")) is not int or report["schema_version"] != 1:
        raise ValueError("Unsupported observer schema / 不支持的观测 schema")
    counts, integrity = _dict(report["counts"]), _dict(report["integrity"])
    for field in COUNT_FIELDS:
        _integer(counts[field])
    status_counts = _dict(counts["status_counts"])
    for count in status_counts.values():
        _integer(count)
    records, errors, aggregate_keys = [], [], set()
    runtime = _dict(report["runtime"])
    if (runtime.get("implementation") != "cpython" or type(runtime.get("version")) is not list
            or len(runtime["version"]) != 3 or runtime["version"][:2] != [3, 12]
            or any(type(part) is not int or part < 0 for part in runtime["version"])):
        errors.append("observer_runtime_unsupported")
    pins = _dict(report["source_pins"])
    for path, digest in pins.items():
        _path(path)
        _digest(digest)
    for row in _list(report["observations"]):
        _dict(row)
        for field in SITE_FIELDS:
            if field not in row:
                raise ValueError("Observation site field missing / 缺少观测位置字段")
        _path(row["source_path"])
        _digest(row["source_sha256"])
        if row["code_signature"] is not None:
            _digest(row["code_signature"])
        for field in ["qualname", "function_name", "name"]:
            if row[field] is not None and type(row[field]) is not str:
                raise ValueError("Non-exact observation identity")
        _integer(row["bytecode_offset"])
        for field in ["lineno", "end_lineno", "col_offset", "end_col_offset"]:
            if row[field] is not None:
                _integer(row[field], 1 if field in {"lineno", "end_lineno"} else 0)
        for flag in ["certified_code", "position_complete"]:
            if type(row[flag]) is not bool:
                raise ValueError("Invalid observation flag")
        for field in ["binding", "status", "event_kind"]:
            if type(row[field]) is not str:
                raise ValueError("Invalid observation state")
        _value(row["value"])
        count = _integer(row["count"], 1)
        first, last = _integer(row["first_event"], 1), _integer(row["last_event"], 1)
        if first > last or last > counts["eligible_load_global_events"] or count > last - first + 1:
            errors.append("observation_event_range_invalid")
        if row["event_kind"] != "pre_op_binding":
            errors.append("observation_event_semantics_invalid")
        if pins.get(row["source_path"]) != row["source_sha256"]:
            errors.append("observation_source_pin_mismatch")
        if row["certified_code"] and (row["code_signature"] is None or any(
                row[key] is None for key in ["qualname", "function_name", "name"])):
            errors.append("observation_certified_identity_missing")
        if row["binding"] == "module_global" and (row["status"] == "primitive") != (
                row["value"]["status"] == "supported"):
            errors.append("observation_primitive_status_inconsistent")
        allowed_status = {"module_global": {"primitive", "unsupported_value"},
            "builtin": {"builtin_fallback"}, "missing": {"missing_binding"},
            "uninspected": {"uncertified_code", "unsupported_name", "unsupported_namespace",
                            "namespace_entry_limit"}}
        if (row["status"] not in allowed_status.get(row["binding"], set()) or (
                row["binding"] != "module_global" and row["value"]["status"] != "unsupported")):
            errors.append("observation_binding_status_inconsistent")
        position = [row[field] for field in ["lineno", "end_lineno", "col_offset", "end_col_offset"]]
        if row["position_complete"] != all(type(part) is int for part in position):
            errors.append("observation_position_flag_inconsistent")
        if position[0] is not None and position[1] is not None and position[0] > position[1]:
            errors.append("observation_line_span_invalid")
        key = _sha({k: v for k, v in row.items() if k not in {"count", "first_event", "last_event"}})
        if key in aggregate_keys:
            errors.append("duplicate_observation_aggregate")
        aggregate_keys.add(key)
        records.append(row)
    retained = sum(row["count"] for row in records)
    retained_status = Counter()
    for row in records:
        retained_status[row["status"]] += row["count"]
    if (len(records) != counts["retained_observations"] or retained != counts["retained_events"]
            or retained + counts["dropped_observations"] != counts["eligible_load_global_events"]
            or sum(status_counts.values()) != counts["eligible_load_global_events"]
            or any(count > status_counts.get(status, 0) for status, count in retained_status.items())
            or counts["uncertified_code_events"] != status_counts.get("uncertified_code", 0)
            or counts["partial_position_events"] < sum(
                row["count"] for row in records if not row["position_complete"])):
        errors.append("observer_count_inconsistent")
    if counts["dropped_observations"]:
        errors.append("observer_dropped_events")
    if counts["uncertified_code_events"] or any(not row["certified_code"] for row in records):
        errors.append("observer_uncertified_code")
    if counts["unsupported_filename_events"]:
        errors.append("observer_unsupported_filename")
    if counts["partial_position_events"] or any(not row["position_complete"] for row in records):
        errors.append("observer_partial_position")
    if report.get("state") != "closed" or report.get("measurement_valid") is not True:
        errors.append("observer_measurement_invalid")
    if report.get("complete") is not True:
        errors.append("observer_incomplete")
    if report.get("event_semantics") != "pre_op_binding_not_consumed_operand":
        errors.append("observer_semantics_invalid")
    if report.get("no_observations") is not (counts["eligible_load_global_events"] == 0):
        errors.append("observer_zero_flag_inconsistent")
    if (any(integrity.get(key) is not True for key in ["source_initial_verified",
            "source_final_verified", "trace_intact_at_exit"])
            or integrity.get("other_threads_seen") is not False
            or integrity.get("observer_errors") != 0 or integrity.get("source_changed") != []
            or integrity.get("body_raised") is not False):
        errors.append("observer_integrity_invalid")
    if not parity:
        errors.append("instrumentation_parity_invalid")
    return {"records": records, "raw_counts": counts, "errors": sorted(set(errors)),
            "input_sha256": _sha(report)}


def _selected(index, row):
    # Removing CPython's synthetic <locals> segment is only for the descriptive
    # unselected/graph-absent label. It never authorizes a value comparison.
    # 只为未选中分类移除 <locals>，不据此接受值假设。
    static = ".".join(part for part in (row["qualname"] or "").split(".") if part != "<locals>")
    return index["selection"].get((row["source_path"], static), [])


def _classify(row, index, role, method):
    primitive = row["binding"] == "module_global" and row["value"]["status"] == "supported"
    if not row["certified_code"]:
        return "uncertified_code", primitive, []
    if not row["position_complete"]:
        return "unsupported_location", primitive, []
    if row["binding"] == "builtin":
        return "builtin", False, []
    if row["binding"] == "missing":
        return "missing", False, []
    if row["binding"] != "module_global":
        return "unsupported_observation", False, []
    if not primitive:
        return "unsupported_observed_value", False, []
    owner_key = (row["source_path"], row["qualname"], row["name"])
    facts = index["facts"].get(owner_key, [])
    selected = _selected(index, row)
    if not facts:
        if any(entry.get("declaration_counts", {}).get(role, 0) > 1 for entry in selected):
            return "ambiguous_owner", True, []
        if method == "always_abstain":
            return "policy_abstain", True, []
        abstained = owner_key in index["abstentions"]
        return ("graph_abstain" if abstained else "graph_absent" if selected else "unselected"), True, []
    exact_sha = [fact for fact in facts if fact["source_sha256"] == row["source_sha256"]]
    if not exact_sha:
        return "source_sha_mismatch", True, []
    contained = [fact for fact in exact_sha if fact["source_start_line"] <= row["lineno"]
                 <= row["end_lineno"] <= fact["source_end_line"]]
    if not contained:
        return "owner_span_mismatch", True, []
    if len(contained) != 1:
        return "ambiguous_hypothesis", True, sorted({fact["edge_id"] for fact in contained})
    fact = contained[0]
    if fact["expected"]["status"] != "supported":
        return "unsupported_hypothesis", True, [fact["edge_id"]]
    state = "matching" if _json(fact["expected"]) == _json(row["value"]) else "mismatching"
    return state, True, [fact["edge_id"]]


def _version(version):
    _dict(version)
    for field in ["facts", "abstentions", "graphs"]:
        _list(version[field])
    for fact in version["facts"]:
        _path(fact["source_path"])
        _digest(fact["source_sha256"])
        for field in ["qualname", "name", "edge_id"]:
            if type(fact[field]) is not str or not fact[field]:
                raise ValueError("Invalid derived hypothesis identity")
        if "runtime_qualname" in fact and type(fact["runtime_qualname"]) is not str:
            raise ValueError("Invalid runtime owner identity")
        if fact.get("operation") != "read":
            raise ValueError("Only resolved read hypotheses can be scored")
        start, end = _integer(fact["source_start_line"], 1), _integer(fact["source_end_line"], 1)
        if end < start:
            raise ValueError("Invalid hypothesis owner span")
        _value(fact["expected"])
    for graph in version["graphs"]:
        if type(graph["complete_graph"]) is not bool:
            raise ValueError("Invalid graph completeness flag")
        if graph["complete_graph"] != (_integer(graph["frontier_count"]) == 0):
            raise ValueError("Inconsistent graph completeness")
    return version


def _ratio(numerator, denominator, qualified):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if qualified and denominator else None}


def _summarize(sites, classification_events, qualified):
    primitive_sites = [site for site in sites if site["primitive_events"]]
    accepted = [site for site in primitive_sites if site["matching_events"] + site["mismatching_events"]]
    mismatched = [site for site in accepted if site["mismatching_events"]]
    matched = [site for site in accepted if not site["mismatching_events"]]
    primitive_events = sum(site["primitive_events"] for site in sites)
    matching_events = classification_events["matching"]
    mismatching_events = classification_events["mismatching"]
    accepted_events = matching_events + mismatching_events
    return {"all_retained_sites": len(sites), "all_retained_events": sum(site["events"] for site in sites),
        "observed_primitive_module_global_sites": len(primitive_sites),
        "observed_primitive_module_global_events": primitive_events,
        "accepted_primitive_sites": len(accepted), "accepted_primitive_events": accepted_events,
        "matching_only_primitive_sites": len(matched), "mismatching_primitive_sites": len(mismatched),
        "mixed_match_mismatch_sites": sum(bool(site["matching_events"] and site["mismatching_events"])
                                           for site in sites),
        "matching_primitive_events": matching_events, "mismatching_primitive_events": mismatching_events,
        "classification_event_counts": {state: classification_events[state] for state in CLASSIFICATIONS},
        "classification_site_counts": {state: sum(state in site["states"] for site in sites)
                                       for state in CLASSIFICATIONS},
        "score_qualified": qualified and bool(primitive_sites),
        "accuracy_qualified": qualified and bool(accepted), "zero_accept": not accepted,
        "no_observed_primitive_disagreement": not mismatched if qualified and accepted else None,
        "primitive_site_coverage": _ratio(len(accepted), len(primitive_sites), qualified),
        "conditional_primitive_site_accuracy": _ratio(len(matched), len(accepted), qualified),
        "primitive_event_coverage": _ratio(accepted_events, primitive_events, qualified),
        "conditional_primitive_event_accuracy": _ratio(matching_events, accepted_events, qualified)}


def _score_role(version, observed, selection, role, method):
    sites, events = {}, Counter()
    index = {"facts": {}, "selection": {}, "abstentions": set()}
    for fact in version["facts"]:
        key = (fact["source_path"], fact.get("runtime_qualname"), fact["name"])
        index["facts"].setdefault(key, []).append(fact)
    for entry in selection:
        if role in entry["versions_present"]:
            index["selection"].setdefault((entry["path"], entry["qualname"]), []).append(entry)
    for abstention in version["abstentions"]:
        index["abstentions"].add((abstention["source_path"], abstention.get("runtime_qualname"),
                                  abstention.get("name")))
    for row in observed["records"]:
        identity = {field: row[field] for field in SITE_FIELDS}
        key = _sha(identity)
        if key not in sites:
            sites[key] = {"site_id": key, **identity, "events": 0, "primitive_events": 0,
                          "matching_events": 0, "mismatching_events": 0,
                          "states": {}, "hypothesis_edge_ids": [], "scored_observations": []}
        site = sites[key]
        state, primitive, edge_ids = _classify(row, index, role, method)
        count = row["count"]
        events[state] += count
        site["events"] += count
        site["primitive_events"] += count if primitive else 0
        site["matching_events"] += count if state == "matching" else 0
        site["mismatching_events"] += count if state == "mismatching" else 0
        site["states"][state] = site["states"].get(state, 0) + count
        site["hypothesis_edge_ids"] = sorted(set(site["hypothesis_edge_ids"]) | set(edge_ids))
        site["scored_observations"].append({"classification": state, "count": count,
            "first_event": row["first_event"], "last_event": row["last_event"],
            "observed_binding": row["binding"], "observer_status": row["status"],
            "observed_value": row["value"], "hypotheses": [
                {"edge_id": fact["edge_id"], "expected": fact["expected"],
                 "source_start_line": fact["source_start_line"],
                 "source_end_line": fact["source_end_line"]}
                for fact in index["facts"].get((row["source_path"], row["qualname"], row["name"]), [])
                if fact["edge_id"] in edge_ids]})
    rows = [sites[key] for key in sorted(sites)]
    summary = _summarize(rows, events, not observed["errors"])
    return {"role": role, "validity_errors": observed["errors"],
            "raw_observer_counts": observed["raw_counts"],
            "summary": summary, "sites": rows,
            "whole_graph": {"graphs": len(version["graphs"]),
                "complete_graphs": sum(graph["complete_graph"] for graph in version["graphs"]),
                "incomplete_graphs": sum(not graph["complete_graph"] for graph in version["graphs"]),
                "frontier_entries": sum(graph["frontier_count"] for graph in version["graphs"])},
            "static_fact_counts": {"derived_hypotheses": len(version["facts"]),
                "supported": sum(f["expected"]["status"] == "supported" for f in version["facts"]),
                "unsupported": sum(f["expected"]["status"] != "supported" for f in version["facts"]),
                "abstentions": len(version["abstentions"])}}


def score_pair(method_result: dict, observations: dict, *, role_parity_valid: dict) -> dict:
    """Score each static repeat/role without counting repeats as independent tasks.

    Alignment requires exact path, SHA, runtime qualname and global name, then
    containment in one unique hypothesis owner's physical function span. This is
    owner/name alignment, not occurrence-exact static-edge reconstruction. True
    runtime sites remain distinct by code signature, opcode offset and positions.
    Invalid/partial/parity-failed observations retain diagnostics but no qualified
    metric. Zero accepts has undefined conditional accuracy, never a passing score.

    精确身份与唯一函数范围包含检查；不冒称静态 occurrence 精确映射。
    无效/不完整数据只保留诊断，零接受的准确率未定义。
    """
    _json(method_result)
    _json(observations)
    _json(role_parity_valid)
    if (set(_dict(observations)) != set(ROLES)
            or set(_dict(role_parity_valid)) != set(ROLES)
            or any(type(role_parity_valid[role]) is not bool for role in ROLES)):
        raise ValueError("Require both roles and explicit bool parity / 需要两角色及明确布尔一致性")
    if (type(_dict(method_result).get("schema_version")) is not int
            or method_result["schema_version"] != 1):
        raise ValueError("Unsupported method schema / 不支持的方法 schema")
    selection = _list(method_result["selection"])
    for row in selection:
        _path(row["path"])
        if type(row["qualname"]) is not str or not row["qualname"]:
            raise ValueError("Invalid selected owner")
        if not set(_list(row["versions_present"])) <= set(ROLES):
            raise ValueError("Invalid selection roles")
    observed = {role: _observation(observations[role], role_parity_valid[role]) for role in ROLES}
    methods = {}
    for name, method in _dict(method_result["methods"]).items():
        runs = []
        for run in _list(method["runs"]):
            _integer(run["repeat"])
            if set(_dict(run["versions"])) != set(ROLES):
                raise ValueError("Method source roles missing")
            versions = {role: _score_role(_version(run["versions"][role]), observed[role],
                selection, role, name) for role in ROLES}
            sites = [site for role in ROLES for site in versions[role]["sites"]]
            events = Counter()
            for role in ROLES:
                events.update(versions[role]["summary"]["classification_event_counts"])
            task_valid = (not any(observed[role]["errors"] for role in ROLES)
                          and all(versions[role]["summary"]["observed_primitive_module_global_sites"]
                                  for role in ROLES))
            runs.append({"repeat": run["repeat"], "versions": versions,
                         "task": _summarize(sites, events, task_valid),
                         "task_validity_errors": {role: observed[role]["errors"] for role in ROLES}})
        if not runs:
            raise ValueError("A method needs at least one retained run")
        methods[name] = {"runs": runs, "repeat_count": len(runs),
            "independent_task_count": 1,
            "score_repeats_equal": len({_sha({"versions": row["versions"], "task": row["task"]})
                                        for row in runs}) == 1}
    if not methods:
        raise ValueError("At least one method is required / 至少需要一个方法")
    result = {"schema_version": 1, "input_method_sha256": _sha(method_result),
        "input_observer_sha256": {role: observed[role]["input_sha256"] for role in ROLES},
        "instrumentation_parity_valid": role_parity_valid, "methods": methods,
        "policy": {"event_semantics": "pre_op_binding_not_consumed_operand",
            "alignment": "exact path+sourceSHA+runtime_qualname+name; unique owner span containment",
            "occurrence_exact_static_edge_mapping": False,
            "runtime_sites": "code signature+offset+physical positions remain separate",
            "primary_denominator": "all retained observed primitive module_global sites; unselected and abstained sites retained",
            "site_accuracy": "all accepted primitive events at a site must match; any mismatch makes the site mismatching",
            "nonprimitive_states": "builtin/missing/unsupported retained separately, not claimed as accurate",
            "repeats": "static repetitions are not independent tasks or runtime replications",
            "invalid_observations": "raw retained diagnostics only; qualified metric values are null",
            "zero_accept": "conditional accuracy undefined, never an accuracy pass",
            "runtime_value_hypotheses_are_product_guarantees": False,
            "mismatch_interpretation": "derived_runtime_value_hypothesis_refuted_not_whole_graph_stale_bug",
            "whole_graph_completeness_is_separate": True,
            "mature_research_established": False}}
    return json.loads(_json(result))
