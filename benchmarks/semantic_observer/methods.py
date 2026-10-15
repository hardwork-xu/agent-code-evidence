"""Real resolver methods for a binding-observation study.

Use actual resolved graph read edges, never a replacement name resolver.
使用真实解析图的已解析读取边；不另写名字解析器，也不将未知图视作语义证明。

Runtime-value hypotheses below are experimental interpretations derived from
literal read edges. The product promises source identity, not immutable runtime
values; a disagreement is not a whole-graph false-fresh bug.
运行时值属于派生实验假设；产品的源码身份见证不承诺运行时值不可变。
"""
from __future__ import annotations

import ast
from collections import Counter
import hashlib
import json
import time
from typing import Mapping

from contextproof.evidence import _safe_parts
from contextproof.graph import canonical_graph_bytes
from contextproof.index import source_lines
from contextproof.reuse import GraphSession

from . import encode_primitive


METHOD_MODES = {
    "currentfresh": "incremental_index_rebuild",
    "whole_guard": "incremental_whole_corpus_guard",
    "selective": "incremental_read_set",
}


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _sources(texts):
    if not isinstance(texts, Mapping):
        raise ValueError("source inputs must be mappings / 源码输入必须是映射")
    result = {}
    for path, text in texts.items():
        _safe_parts(path)
        if not path.endswith(".py") or not isinstance(text, str):
            raise ValueError("expected production .py text / 需要 production .py 文本")
        text.encode("utf-8")
        result[path] = text
    return dict(sorted(result.items()))


def _declarations(texts):
    """Enumerate identities only; resolution still belongs to build_graph.

    仅枚举静态函数身份；不依据运行时、图完整性或解析成功选择样本。
    """
    declarations, failures = {}, []
    for path, text in texts.items():
        try:
            tree = ast.parse(text, filename=path)
        except (SyntaxError, ValueError, RecursionError) as exc:
            failures.append({"path": path, "category": type(exc).__name__})
            continue

        class Visitor(ast.NodeVisitor):
            def __init__(self):
                self.stack = []

            def scope(self, node, function):
                static = ".".join([*(item[0] for item in self.stack), node.name])
                runtime_parts = []
                for name, is_function in self.stack:
                    runtime_parts.append(name)
                    if is_function:
                        runtime_parts.append("<locals>")
                runtime = ".".join([*runtime_parts, node.name])
                if function:
                    fragment = "".join(source_lines(text)[node.lineno - 1:node.end_lineno])
                    row = {"path": path, "symbol": static, "kind": "function",
                           "runtime_qualname": runtime,
                           "start_line": node.lineno, "end_line": node.end_lineno,
                           "text": fragment, "text_sha256": _sha(fragment.encode()),
                           "file_sha256": _sha(text.encode())}
                    declarations.setdefault((path, static), []).append(row)
                self.stack.append((node.name, function))
                self.generic_visit(node)
                self.stack.pop()

            def visit_FunctionDef(self, node):
                self.scope(node, True)

            def visit_AsyncFunctionDef(self, node):
                self.scope(node, True)

            def visit_ClassDef(self, node):
                self.scope(node, False)

        Visitor().visit(tree)
    return declarations, failures


def _anchor(key, declarations):
    # A duplicate declaration is kept in the selection. The real graph then
    # refuses the ambiguous identity; choosing its first span is not resolving it.
    # 重名声明不从分母删除；其歧义由真实产品拒绝，首个片段不构成解析。
    first = min(declarations[key], key=lambda row: (row["start_line"], row["end_line"]))
    return {key: value for key, value in first.items() if key != "runtime_qualname"} | {
        "id": "semantic-" + _sha(_canonical(list(key)))}


def _literal(target):
    """Decode an already accepted target, not discover a different binding.

    只解码真实图已接受的声明；失败或超出 primitive 范围须显式保留。
    """
    try:
        module = ast.parse(target["text"])
        statements = []
        # Product records preserve whole physical lines, including semicolon
        # neighbors. Select only the unique already-resolved target's statement.
        # 整物理行可含分号邻居；只解码真实产品已解析 symbol 的唯一声明，不解析新名字。
        for statement in module.body:
            if isinstance(statement, ast.Assign):
                names = [node.id for node in statement.targets if isinstance(node, ast.Name)]
                if len(names) == len(statement.targets) and target["symbol"] in names:
                    statements.append(statement)
            elif (isinstance(statement, ast.AnnAssign)
                  and isinstance(statement.target, ast.Name)
                  and statement.target.id == target["symbol"]):
                statements.append(statement)
        if len(statements) != 1:
            return {"status": "unsupported", "type": "other",
                    "reason": "accepted_target_statement_not_unique"}
        statement = statements[0]
        return encode_primitive(ast.literal_eval(statement.value))
    except (SyntaxError, ValueError, TypeError, MemoryError, RecursionError) as exc:
        return {"status": "unsupported", "type": "other",
                "reason": "literal_decode_" + type(exc).__name__}


def _project(graphs, declarations, file_hashes):
    facts, abstentions, graph_rows = {}, [], []
    for graph in graphs:
        complete = not graph["frontier"]
        graph_rows.append({"graph_id": graph["id"],
                           "graph_sha256": _sha(canonical_graph_bytes(graph)),
                           "complete_graph": complete,
                           "frontier_count": len(graph["frontier"]),
                           "anchor_rows": graph["anchors"]})
        for edge in graph["edges"].values():
            if edge["operation"] != "read":
                continue
            source = graph["nodes"][edge["source"]]
            base = {"source_path": source["path"],
                    "source_sha256": file_hashes[source["path"]], "qualname": source["symbol"],
                    "source_start_line": source["start_line"],
                    "source_end_line": source["end_line"], "name": edge["expression"],
                    "operation": edge["operation"], "edge_id": edge["id"]}
            declarations_for_source = declarations.get((source["path"], source["symbol"]), [])
            if len(declarations_for_source) == 1:
                base["runtime_qualname"] = declarations_for_source[0]["runtime_qualname"]
            reason = None
            if source["kind"] != "function":
                reason = "non_function_source_node"
            elif edge["status"] != "resolved":
                reason = edge["reason"]
            elif not edge["expression"].isidentifier():
                reason = "qualified_attribute_is_not_LOAD_GLOBAL_value"
            elif graph["nodes"][edge["target"]]["kind"] != "constant":
                reason = "resolved_target_is_not_literal_binding"
            if reason is not None:
                abstentions.append({**base, "graph_id": graph["id"],
                                    "resolver_status": edge["status"], "reason": reason})
                continue
            target = graph["nodes"][edge["target"]]
            fact = {**base, "claim_kind": "experimental_runtime_value_hypothesis",
                    "target_path": target["path"],
                    "target_source_sha256": file_hashes[target["path"]],
                    "target_symbol": target["symbol"],
                    "target_start_line": target["start_line"], "target_end_line": target["end_line"],
                    "target_text_sha256": target["text_sha256"],
                    "expected": _literal(target), "import_binding_nodes": edge["bindings"]}
            key = edge["id"]
            support = {"graph_id": graph["id"], "complete_graph": complete}
            if key in facts:
                old = {k: v for k, v in facts[key].items()
                       if k not in {"supporting_graphs", "complete_graph"}}
                if old != fact:
                    raise ValueError("same source read has conflicting accepted facts")
                facts[key]["supporting_graphs"].append(support)
                facts[key]["complete_graph"] = facts[key]["complete_graph"] and complete
            else:
                facts[key] = {**fact, "supporting_graphs": [support], "complete_graph": complete}
    rows = [facts[key] for key in sorted(facts)]
    return {"facts": rows, "abstentions": sorted(abstentions, key=lambda row: _canonical(row)),
            "graphs": sorted(graph_rows, key=lambda row: row["graph_id"]),
            "counts": {"accepted_read_edge_facts": len(rows),
                       "primitive_supported_facts": sum(f["expected"]["status"] == "supported" for f in rows),
                       "primitive_unsupported_facts": sum(f["expected"]["status"] != "supported" for f in rows),
                       "abstention_graph_edges": len(abstentions),
                       "graphs": len(graph_rows),
                       "complete_graphs": sum(row["complete_graph"] for row in graph_rows)}}


def _semantic_key(versions):
    # Graph handles/provenance are separate from the individual binding claims.
    # 图句柄/支撑图单列；不能因缓存方式或计时不同伪造语义差异。
    return _sha(_canonical({version: [
        {key: value for key, value in fact.items()
         if key not in {"supporting_graphs", "complete_graph"}}
        for fact in result["facts"]]
        for version, result in versions.items()}))


def evaluate_pair(before_texts, after_texts, *, anchor_limit=32, repeats=3,
                  max_depth=4, max_nodes=256):
    """Compare actual graph policies on a fixed static function selection.

    Each method owns identically configured persistent ModuleCache instances;
    mutable caches are never shared across competitors. ``currentfresh`` rebuilds
    each graph using current guarded module summaries, a stronger control than
    reparsing everything. Initialization/capture/replay/projection are included.
    公平使用独立同配置模块缓存；currentfresh 每次重建当前图，非故意冷解析弱基线。
    Raw timing repetitions are diagnostic records, never independent datasets.
    """
    if type(anchor_limit) is not int or not 1 <= anchor_limit <= 32:
        raise ValueError("anchor_limit must be in [1, 32]")
    if type(repeats) is not int or not 1 <= repeats <= 30:
        raise ValueError("repeats must be in [1, 30]")
    if type(max_depth) is not int or not 0 <= max_depth <= 128:
        raise ValueError("invalid max_depth")
    if type(max_nodes) is not int or not 1 <= max_nodes <= 100000:
        raise ValueError("invalid max_nodes")
    started = time.perf_counter()
    texts = {"before": _sources(before_texts), "after": _sources(after_texts)}
    hashes = {version: _sha(_canonical(source)) for version, source in texts.items()}
    file_hashes = {version: {path: _sha(source.encode()) for path, source in sources.items()}
                   for version, sources in texts.items()}
    declarations, parse_failures = {}, {}
    for version, source in texts.items():
        declarations[version], parse_failures[version] = _declarations(source)
    keys = sorted(set(declarations["before"]) | set(declarations["after"]),
                  key=lambda key: (_sha(_canonical(list(key))), key))[:anchor_limit]
    groups = {"common": [], "removed": [], "added": []}
    selection = []
    for key in keys:
        present = [version for version in texts if key in declarations[version]]
        group = "common" if len(present) == 2 else "removed" if present == ["before"] else "added"
        groups[group].append(key)
        selection.append({"path": key[0], "qualname": key[1],
                          "selection_sha256": _sha(_canonical(list(key))),
                          "versions_present": present, "group": group,
                          "declaration_counts": {version: len(declarations[version].get(key, []))
                                                 for version in texts}})
    preparation_seconds = time.perf_counter() - started
    methods = {method: {"mode": mode, "runs": []} for method, mode in METHOD_MODES.items()}
    execution_order = []
    for repeat in range(repeats):
        names = list(METHOD_MODES)
        rotation = repeat % len(names)
        order = names[rotation:] + names[:rotation]
        execution_order.append({"repeat": repeat, "methods": order})
        for position, method in enumerate(order):
            mode = METHOD_MODES[method]
            run_started = time.perf_counter()
            sessions = {}
            for group, selected in groups.items():
                version = "after" if group == "added" else "before"
                if selected:
                    sessions[group] = GraphSession(
                        [_anchor(key, declarations[version]) for key in selected],
                        mode=mode, max_depth=max_depth, max_nodes=max_nodes)
            initialized = time.perf_counter()
            before_graphs, capture_counts = [], Counter()
            for group in ("common", "removed"):
                if group in sessions:
                    result = sessions[group].update(texts["before"], hashes["before"])
                    before_graphs.extend(result.graphs)
                    capture_counts.update({"reused": result.reused, "rebuilt": result.rebuilt})
            before = _project(before_graphs, declarations["before"], file_hashes["before"])
            captured = time.perf_counter()
            after_graphs, replay_counts, reasons = [], Counter(), Counter()
            for group in ("common", "added"):
                if group in sessions:
                    result = sessions[group].update(texts["after"], hashes["after"])
                    after_graphs.extend(result.graphs)
                    replay_counts.update({"reused": result.reused, "rebuilt": result.rebuilt})
                    reasons.update(result.reasons)
            after = _project(after_graphs, declarations["after"], file_hashes["after"])
            versions = {"before": before, "after": after}
            semantic_digest = _semantic_key(versions)
            finished = time.perf_counter()
            methods[method]["runs"].append({"repeat": repeat, "execution_position": position,
                         "versions": versions,
                         "semantic_output_sha256": semantic_digest,
                         "capture_counts": dict(capture_counts),
                         "replay_counts": dict(replay_counts), "replay_reasons": dict(reasons),
                         "timings_seconds": {
                             "initialization": initialized - run_started,
                             "capture_including_projection": captured - initialized,
                             "replay_including_projection": finished - captured,
                             "total_method": finished - run_started,
                             "shared_preparation_separately_measured": preparation_seconds},
                         "module_cache_stats": {group: session.index_stats
                                                for group, session in sessions.items()}})
    for record in methods.values():
        record["repeats_semantically_equal"] = len({
            run["semantic_output_sha256"] for run in record["runs"]}) == 1
    abstain_runs = []
    for repeat in range(repeats):
        abstain_started = time.perf_counter()
        abstain_versions = {}
        abstain_initialized = time.perf_counter()
        for version in texts:
            abstain_versions[version] = {"facts": [], "abstentions": [
                {"source_path": key[0], "qualname": key[1], "reason": "always_abstain_policy"}
                for key in keys if key in declarations[version]], "graphs": [],
                "counts": {"accepted_read_edge_facts": 0, "primitive_supported_facts": 0,
                           "primitive_unsupported_facts": 0, "graphs": 0, "complete_graphs": 0}}
            if version == "before":
                abstain_captured = time.perf_counter()
        digest = _semantic_key(abstain_versions)
        abstain_finished = time.perf_counter()
        abstain_runs.append({
            "repeat": repeat, "versions": abstain_versions,
            "semantic_output_sha256": digest,
            "timings_seconds": {
                "initialization": abstain_initialized - abstain_started,
                "capture_including_projection": abstain_captured - abstain_initialized,
                "replay_including_projection": abstain_finished - abstain_captured,
                "total_method": abstain_finished - abstain_started,
                "shared_preparation_separately_measured": preparation_seconds}})
    methods["always_abstain"] = {"mode": "no_static_claims", "runs": abstain_runs,
        "repeats_semantically_equal": True}
    reference = methods["currentfresh"]["runs"][0]
    comparisons = {}
    for method, record in methods.items():
        run = record["runs"][0]
        equal = run["semantic_output_sha256"] == reference["semantic_output_sha256"]
        comparisons[method] = {"individual_binding_facts_equal_currentfresh": equal,
                               "semantic_comparison": "tie" if equal else "different_not_a_quality_score"}
        if method != "always_abstain":
            comparisons[method]["graph_outputs_equal_currentfresh"] = all(
                run["versions"][version]["graphs"] == reference["versions"][version]["graphs"]
                for version in texts)
    return {"schema_version": 1, "selection": selection, "parse_failures": parse_failures,
            "method_execution_order": execution_order,
            "snapshot_sha256": hashes, "preparation_seconds": preparation_seconds,
            "policy": {"anchor_limit": anchor_limit, "repeats": repeats,
                       "max_depth": max_depth, "max_nodes": max_nodes,
                       "selection": "SHA256(canonical JSON [path, qualified symbol]); union before selection",
                       "semantic_scope": "experimental runtime-value hypotheses derived from individual resolved literal read edges",
                       "product_contract": "source/declaration/import identity only, not immutable runtime values",
                       "runtime_value_hypotheses_are_product_guarantees": False,
                       "whole_graph_semantics_claimed": False,
                       "disagreement_interpretation": "finite pre-op disagreement with derived hypothesis; not_whole_graph_false_fresh",
                       "primitive_codec": "shared pure encode_primitive; unsupported values retained",
                       "added_removed": "only existing source side built; added functions are cold after captures",
                       "timing_scope": "actual method init/capture/replay including projection; common discovery/hash separately timed, not SUT performance",
                       "timing_order": "repeat-major, cyclic rotation of three actual methods; recorded explicitly",
                       "warmup": "none; fresh session caches in every method/repetition",
                       "always_abstain_timing": "separate zero-mechanism diagnostic",
                       "cache_fairness": "separate equal-policy persistent ModuleCache per method; currentfresh rebuilds graph using current module summaries"},
            "methods": methods, "comparisons": comparisons,
            "mature_research_established": False}
