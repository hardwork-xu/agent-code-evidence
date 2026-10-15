"""Independent method controls; authored fixtures are not natural experiments.

独立方法契约与反例，只运行自编固定源码的静态分析，不运行上游程序。
"""
import hashlib
import json

import pytest

from benchmarks.semantic_observer.methods import evaluate_pair
from contextproof.dependencies import _Corpus


def one(source, **options):
    return evaluate_pair({"module.py": source}, {"module.py": source}, repeats=1, **options)


def version(result, method="currentfresh", side="after"):
    return result["methods"][method]["runs"][0]["versions"][side]


def test_actual_graph_refuses_a_binding_that_direct_module_lookup_accepts():
    source = "X = 1\ndef entry():\n    def inner():\n        X = 2\n        return X\n    return X\n"
    corpus = _Corpus.from_texts({"module.py": source})
    assert corpus.resolve_name("module.py", "X", [])["status"] == "resolved"
    result = one(source)
    assert version(result)["facts"] == []
    assert any("nested" in row["reason"] for row in version(result)["abstentions"])


def test_exact_primitive_facts_come_from_real_resolved_read_targets():
    source = "X = True\ndef entry():\n    return X\n"
    result = one(source)
    fact, = version(result)["facts"]
    assert fact["name"] == "X" and fact["expected"]["type"] == "bool"
    assert fact["expected"]["status"] == "supported"
    assert fact["qualname"] == fact["runtime_qualname"] == "entry"
    assert fact["target_start_line"] == 1
    assert fact["source_sha256"] == fact["target_source_sha256"] == hashlib.sha256(source.encode()).hexdigest()
    assert fact["complete_graph"]
    assert all(result["comparisons"][method]["semantic_comparison"] == "tie"
               for method in ("currentfresh", "whole_guard", "selective"))
    assert result["comparisons"]["always_abstain"]["semantic_comparison"] != "tie"


def test_resolved_container_stays_in_accepted_denominator_as_unsupported():
    result = one("X = [1, 2]\ndef entry():\n    return X\n")
    fact, = version(result)["facts"]
    assert fact["expected"]["status"] == "unsupported"
    assert version(result)["counts"]["accepted_read_edge_facts"] == 1
    assert version(result)["counts"]["primitive_supported_facts"] == 0
    assert version(result)["counts"]["primitive_unsupported_facts"] == 1


@pytest.mark.parametrize("declaration", ["X = 1; Y = 2", "X: int = 1; Y: int = 2",
                                         "X = 1; unused = object(); Y = 2"])
def test_semicolon_target_text_decodes_the_unique_already_resolved_symbol(declaration):
    result = one(declaration + "\ndef entry():\n    return X + Y\n")
    facts = version(result)["facts"]
    assert {fact["target_symbol"]: fact["expected"] for fact in facts} == {
        "X": {"status": "supported", "type": "int", "decimal": "1"},
        "Y": {"status": "supported", "type": "int", "decimal": "2"}}


def test_runtime_value_claims_are_explicit_experimental_hypotheses_not_product_promises():
    result = one("X=1\ndef entry():\n    return X\n")
    assert result["policy"]["runtime_value_hypotheses_are_product_guarantees"] is False
    assert result["policy"]["whole_graph_semantics_claimed"] is False
    assert "not_whole_graph_false_fresh" in result["policy"]["disagreement_interpretation"]
    assert version(result)["facts"][0]["claim_kind"] == "experimental_runtime_value_hypothesis"


def test_individual_binding_is_retained_while_whole_graph_is_incomplete():
    result = one("X = 2\ndef entry():\n    return X + UNKNOWN\n")
    fact, = version(result)["facts"]
    assert not fact["complete_graph"]
    assert version(result)["counts"]["complete_graphs"] == 0
    assert any(row["name"] == "UNKNOWN" for row in version(result)["abstentions"])


def test_import_alias_matches_local_read_name_and_real_remote_target():
    texts = {"app.py": "from values import X as ALIAS\ndef entry():\n    return ALIAS\n",
             "values.py": "X = 'sensitive raw literal'\n"}
    result = evaluate_pair(texts, texts, repeats=1)
    fact, = version(result)["facts"]
    assert fact["source_path"] == "app.py" and fact["name"] == "ALIAS"
    assert fact["target_path"] == "values.py" and fact["target_symbol"] == "X"
    assert fact["import_binding_nodes"]
    assert "sensitive raw literal" not in json.dumps(result)


def test_union_selection_is_sha_sorted_and_independent_of_execution_or_resolution():
    before = {"app.py": "def removed():\n    return missing_name\ndef both():\n    return 1\n"}
    after = {"app.py": "def added():\n    return another_missing_name\ndef both():\n    return 2\n"}
    result = evaluate_pair(before, after, repeats=1)
    assert [row["selection_sha256"] for row in result["selection"]] == sorted(
        row["selection_sha256"] for row in result["selection"])
    assert {row["group"] for row in result["selection"]} == {"added", "removed", "common"}
    assert len(version(result, side="before")["graphs"]) == 2
    assert len(version(result, side="after")["graphs"]) == 2
    assert {row["qualname"] for row in result["selection"]} == {"removed", "added", "both"}


def test_anchor_limit_chooses_union_by_stable_hash_not_input_order():
    texts = {"z.py": "def zed():\n    return external\n", "a.py": "def aye():\n    return 1\n"}
    first = evaluate_pair(texts, texts, anchor_limit=1, repeats=1)
    second = evaluate_pair(dict(reversed(list(texts.items()))), texts, anchor_limit=1, repeats=1)
    assert first["selection"] == second["selection"]
    digests = {symbol: hashlib.sha256(json.dumps(
        [path, symbol], ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        for path, symbol in [("z.py", "zed"), ("a.py", "aye")]}
    assert first["selection"][0]["qualname"] == min(digests, key=digests.get)


def test_true_cache_modes_reuse_unchanged_read_sets_and_still_tie_semantics():
    before = {"app.py": "X = 1\ndef entry():\n    return X\n",
              "other.py": "def unrelated():\n    return 0\n"}
    after = before | {"other.py": "def unrelated():\n    return 2\n"}
    result = evaluate_pair(before, after, repeats=2)
    runs = {method: row["runs"][0] for method, row in result["methods"].items()}
    assert runs["currentfresh"]["replay_counts"]["reused"] == 0
    assert runs["whole_guard"]["replay_counts"]["reused"] == 0
    assert runs["selective"]["replay_counts"]["reused"] == 1
    assert all(result["comparisons"][method]["graph_outputs_equal_currentfresh"]
               for method in ("currentfresh", "whole_guard", "selective"))
    assert all(row["repeats_semantically_equal"] for row in result["methods"].values())


def test_duplicate_function_and_bad_syntax_remain_visible():
    texts = {"app.py": "X=1\ndef duplicate():\n    return X\ndef duplicate():\n    return X\n",
             "broken.py": "def broken(:\n"}
    result = evaluate_pair(texts, texts, repeats=1)
    assert result["selection"][0]["declaration_counts"] == {"before": 2, "after": 2}
    assert result["parse_failures"]["before"] == [{"path": "broken.py", "category": "SyntaxError"}]
    assert version(result)["facts"] == []
    assert version(result)["graphs"][0]["frontier_count"] > 0


def test_nested_runtime_qualname_and_zero_coverage_are_not_promoted_to_accuracy():
    source = "X=1\ndef outer():\n    def inner():\n        return X\n    return inner\n"
    result = one(source)
    assert any(f["runtime_qualname"] == "outer.<locals>.inner"
               for f in version(result)["facts"] if f["qualname"] == "outer.inner")
    empty = evaluate_pair({}, {}, repeats=2)
    assert empty["selection"] == []
    assert all(row["semantic_comparison"] == "tie" for row in empty["comparisons"].values())
    assert empty["mature_research_established"] is False


def test_actual_timings_include_init_capture_replay_and_separate_common_preparation():
    result = one("X=1\ndef entry():\n    return X\n")
    assert result["preparation_seconds"] >= 0
    for method in result["methods"].values():
        timing = method["runs"][0]["timings_seconds"]
        assert timing["initialization"] >= 0
        assert timing["capture_including_projection"] >= 0
        assert timing["replay_including_projection"] >= 0
        assert timing["total_method"] == pytest.approx(
            timing["initialization"] + timing["capture_including_projection"] + timing["replay_including_projection"])


def test_counterbalanced_repeat_major_order_starts_fresh_without_warmup():
    result = evaluate_pair({"a.py": "X=1\ndef f():\n    return X\n"},
                           {"a.py": "X=2\ndef f():\n    return X\n"}, repeats=3)
    assert result["method_execution_order"] == [
        {"repeat": 0, "methods": ["currentfresh", "whole_guard", "selective"]},
        {"repeat": 1, "methods": ["whole_guard", "selective", "currentfresh"]},
        {"repeat": 2, "methods": ["selective", "currentfresh", "whole_guard"]}]
    assert result["policy"]["warmup"] == "none; fresh session caches in every method/repetition"
    for record in result["methods"].values():
        assert [run["repeat"] for run in record["runs"]] == [0, 1, 2]
    assert result["policy"]["always_abstain_timing"] == "separate zero-mechanism diagnostic"


@pytest.mark.parametrize("options", [{"anchor_limit": 0}, {"anchor_limit": 33},
                                    {"anchor_limit": True}, {"repeats": 0},
                                    {"repeats": True}, {"max_depth": -1}, {"max_nodes": 0}])
def test_invalid_fixed_limits_are_rejected(options):
    with pytest.raises(ValueError):
        evaluate_pair({}, {}, **options)


@pytest.mark.parametrize("texts", [{"../x.py": ""}, {"/x.py": ""}, {"x.pyi": ""}, {"x.py": 3}])
def test_source_contract_rejects_escaped_or_nonproduction_inputs(texts):
    with pytest.raises((ValueError, TypeError)):
        evaluate_pair(texts, {})
