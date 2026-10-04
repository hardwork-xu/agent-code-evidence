"""Validate authored oracles independently of ContextProof's resolver.

These tests certify the fixture's labels/provenance and finite observations, not
the accuracy of the system under evaluation. 不使用被测图给样例生成预期。
"""

import ast
from collections import Counter
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.selective_reuse import oracle_cases as corpus


CASES = corpus.cases()


def test_corpus_is_frozen_development_with_explicit_correlated_denominators():
    manifest = corpus.corpus_manifest()
    assert manifest["count"] == 72
    assert manifest["template_count"] == 24
    assert len(manifest["family_counts"]) == 6
    assert set(manifest["family_counts"].values()) == {12}
    assert manifest["contract_class_counts"] == {
        "supported_static": 27, "unsupported_static": 36, "runtime_effect_out_of_scope": 9,
    }
    assert manifest["decision_counts"] == {"changed": 15, "fresh": 12, "unknown": 45}
    assert manifest["split"] == "development_adversarial_regression"
    assert "not 72 independent" in manifest["limitation"]
    assert len({case.case_id for case in CASES}) == len(CASES)
    assert corpus.corpus_manifest() == manifest
    assert all(case.before != case.after for case in CASES)
    templates = Counter((case.family, case.template) for case in CASES)
    assert set(templates.values()) == {3}


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_both_authored_versions_match_independent_python_execution(case):
    assert corpus.execute_fixture(case, "before") == case.before_outcome
    assert corpus.execute_fixture(case, "after") == case.after_outcome


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_labels_and_anchor_provenance_do_not_depend_on_graph(case):
    selected = corpus.anchor(case)
    lines = case.before[case.anchor_path].splitlines(keepends=True)
    assert selected["text"] == "".join(lines[selected["start_line"] - 1:selected["end_line"]])
    assert selected["text_sha256"] == hashlib.sha256(selected["text"].encode()).hexdigest()
    assert selected["file_sha256"] == hashlib.sha256(case.before[case.anchor_path].encode()).hexdigest()
    assert selected["id"] == case.case_id
    assert case.split == corpus.SPLIT
    assert case.rationale_en and case.rationale_zh
    for texts in (case.before, case.after):
        for path, text in texts.items():
            compile(text, path, "exec")
    if case.contract_class == "runtime_effect_out_of_scope":
        assert case.contract_expected_decision is None
        assert case.expected_decision == "unknown"
    else:
        assert case.contract_expected_decision == case.expected_decision
    if case.expected_decision == "fresh":
        assert case.before_outcome == case.after_outcome
    # Equality of finite execution is explicitly insufficient for source identity.
    if case.template in {"equal_behavior_retarget", "decorator_source_identity"}:
        assert case.before_outcome == case.after_outcome
        assert case.expected_decision == "changed"


def test_dataset_has_no_contextproof_import_or_resolver_oracle_dependency():
    module_tree = ast.parse(Path(corpus.__file__).read_text())
    imported = []
    for node in ast.walk(module_tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not any(name.startswith("contextproof") for name in imported)


def test_exec_is_not_a_generic_arbitrary_source_runner():
    fixture = CASES[0]
    altered = replace(fixture, before={"app.py": "def entry():\n    return 991\n"})
    with pytest.raises(ValueError, match="unmodified authored"):
        corpus.execute_fixture(altered, "before")
    with pytest.raises(ValueError, match="version"):
        corpus.execute_fixture(fixture, "unlisted")


def test_serialization_and_repeated_calls_do_not_share_mutable_sources():
    first, second = corpus.cases(), corpus.cases()
    expected = first[0].to_dict()
    assert json.loads(json.dumps(expected)) == expected
    first[0].before["app.py"] = "changed by a caller"
    assert second[0].to_dict() == expected
    assert corpus.cases()[0].to_dict() == expected
