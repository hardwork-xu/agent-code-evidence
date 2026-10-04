"""Independent certificate review: exact fresh-build parity, not semantic soundness.

独立复核进程内复用证书；检查与完整重建逐字段相等，不把相等当运行时语义保证。
"""

import ast
from copy import deepcopy
import hashlib

import pytest

from contextproof.graph import build_graph, validate_graph
from contextproof.reuse import GraphSession


def anchor(texts, path="app.py", symbol="entry"):
    """Locate source independently of the dependency resolver / 独立定位源码。"""
    node = next(item for item in ast.parse(texts[path]).body
                if isinstance(item, ast.FunctionDef) and item.name == symbol)
    text = "".join(texts[path].splitlines(keepends=True)[node.lineno - 1:node.end_lineno])
    return {"id": path + ":" + symbol, "path": path, "symbol": symbol, "kind": "function",
            "start_line": node.lineno, "end_line": node.end_lineno, "text": text,
            "text_sha256": hashlib.sha256(text.encode()).hexdigest()}


def package_sources():
    return {"app.py": "import pkg\ndef entry():\n    return pkg.worker.compute()\n",
            "pkg/__init__.py": "# A package with no worker attribute.\n",
            "pkg/worker.py": "def compute():\n    return 7\n",
            "alternate.py": "def compute():\n    return 8\n",
            "unrelated.py": "OTHER = 1\n"}


def assert_fresh_parity(replay, texts, snapshot_id, selected, **policy):
    expected = [build_graph(texts, snapshot_id, [item], **policy) for item in selected]
    assert replay.graphs == expected
    for graph in replay.graphs:
        validate_graph(graph)
    assert replay.reused + replay.rebuilt == len(selected)


@pytest.mark.parametrize("replacement", [
    "def __getattr__(name):\n    return 1\n",
    "from alternate import *\n",
    "import alternate as worker\n",
    "worker = 1\n",
    "this is (invalid\n",
    "MARKER = 2\n",
], ids=["getattr", "wildcard", "explicit-alias", "explicit-constant", "parse-error",
        "conservative-whole-file"])
def test_negative_package_attribute_lookup_is_a_read_dependency(replacement):
    before = package_sources()
    selected = anchor(before)
    session = GraphSession([selected])
    initial = session.update(before, "before")
    assert not initial.graphs[0]["frontier"]
    assert "pkg/__init__.py" not in {node["path"] for node in initial.graphs[0]["nodes"].values()}
    after = before | {"pkg/__init__.py": replacement}
    result = session.update(after, "after")
    assert result.reused == 0
    assert result.reasons == {"read_dependency_changed": 1}
    assert_fresh_parity(result, after, "after", [selected])


def test_read_set_includes_node_free_negative_lookup_package():
    texts = package_sources()
    reads = {"caller-existing-marker"}
    graph = build_graph(texts, "before", [anchor(texts)], read_set=reads)
    assert reads == {"caller-existing-marker", "app.py", "pkg/__init__.py", "pkg/worker.py"}
    assert "pkg/__init__.py" not in {node["path"] for node in graph["nodes"].values()}


@pytest.mark.parametrize("added_path, added_source", [
    ("new.py", "NEW = 1\n"),
    ("pkg/worker.pyi", "def compute(): ...\n"),
    ("src/pkg/worker.py", "def compute():\n    return 99\n"),
    ("pkg/worker/__init__.py", "def compute():\n    return 99\n"),
    ("pkg.py", "worker = 9\n"),
], ids=["irrelevant-addition", "stub-ambiguity", "src-alias-ambiguity",
        "module-package-ambiguity", "parent-ambiguity"])
def test_catalog_additions_cannot_reuse_old_certificate(added_path, added_source):
    before = package_sources()
    selected = anchor(before)
    session = GraphSession([selected])
    session.update(before, "before")
    after = before | {added_path: added_source}
    result = session.update(after, "after")
    assert result.reused == 0
    assert result.reasons == {"catalog_changed": 1}
    assert_fresh_parity(result, after, "after", [selected])


@pytest.mark.parametrize("old,new", [
    ("unrelated.py", "renamed.py"),
    ("pkg/worker.py", "pkg/renamed.py"),
    ("pkg/__init__.py", "pkg/marker.py"),
    ("app.py", "entrypoint.py"),
], ids=["irrelevant-rename", "target-rename", "package-to-namespace", "anchor-rename"])
def test_rename_changes_catalog_even_when_file_bytes_do_not(old, new):
    before = package_sources()
    selected = anchor(before)
    session = GraphSession([selected])
    session.update(before, "before")
    after = dict(before)
    after[new] = after.pop(old)
    result = session.update(after, "after")
    assert result.reasons == {"catalog_changed": 1}
    assert_fresh_parity(result, after, "after", [selected])


@pytest.mark.parametrize("policy", [{"max_depth": 0}, {"max_depth": 1}, {"max_nodes": 1}])
@pytest.mark.parametrize("change", [False, True], ids=["same-corpus", "unrelated-edit"])
def test_incomplete_certificate_rebuilds_even_if_visible_files_are_unchanged(policy, change):
    before = package_sources()
    selected = anchor(before)
    session = GraphSession([selected], **policy)
    first = session.update(before, "before")
    assert first.graphs[0]["frontier"]
    after = before | ({"unrelated.py": "OTHER = 2\n"} if change else {})
    result = session.update(after, "after")
    assert result.reused == 0
    assert result.reasons == {"incomplete_graph": 1}
    assert_fresh_parity(result, after, "after", [selected], **policy)


def test_unavailable_import_becomes_resolvable_after_catalog_addition():
    before = {"app.py": "from absent import helper\ndef entry():\n    return helper()\n"}
    selected = anchor(before)
    session = GraphSession([selected])
    assert session.update(before, "before").graphs[0]["frontier"]
    after = before | {"absent.py": "def helper():\n    return 5\n"}
    result = session.update(after, "after")
    assert result.reused == 0
    assert not result.graphs[0]["frontier"]
    assert_fresh_parity(result, after, "after", [selected])


def test_unresolved_candidate_content_change_cannot_reuse_incomplete_graph():
    before = package_sources() | {"pkg/__init__.py": "worker = 1\n"}
    selected = anchor(before)
    session = GraphSession([selected])
    first = session.update(before, "before")
    assert first.graphs[0]["frontier"]
    after = before | {"pkg/__init__.py": "# restore submodule fallback\n"}
    result = session.update(after, "after")
    assert result.reasons == {"incomplete_graph": 1}
    assert not result.graphs[0]["frontier"]
    assert_fresh_parity(result, after, "after", [selected])


def test_unchanged_consulted_paths_allow_reuse_and_reseal_to_current_snapshot():
    before = package_sources()
    selected = anchor(before)
    session = GraphSession([selected])
    first = session.update(before, "before")
    after = before | {"unrelated.py": "OTHER = 999\n"}
    result = session.update(after, "after")
    assert result.reused == 1
    assert result.reasons == {"read_set_equal": 1}
    assert result.graphs[0]["id"] != first.graphs[0]["id"]
    assert_fresh_parity(result, after, "after", [selected])


def test_input_anchors_sources_and_output_graphs_do_not_mutate_cache():
    before = package_sources()
    selected = anchor(before)
    pristine = deepcopy(selected)
    anchors = [selected]
    session = GraphSession(anchors)
    selected["text"] = "caller changed the anchor"
    anchors.clear()
    first = session.update(before, "before")
    first.graphs[0]["nodes"].clear()
    first.graphs[0]["snapshot_id"] = "caller mutation"
    first.reasons["injected"] = 5
    before["unrelated.py"] = "OTHER = 3\n"
    result = session.update(before, "after")
    assert result.reused == 1
    assert "injected" not in result.reasons
    assert_fresh_parity(result, before, "after", [pristine])
    before["pkg/worker.py"] = "def compute():\n    return 100\n"
    changed = session.update(before, "after-target-change")
    assert changed.reused == 0
    assert_fresh_parity(changed, before, "after-target-change", [pristine])


def test_multiple_anchors_reuse_independently_and_match_separate_fresh_builds():
    before = package_sources() | {"second.py": "def entry():\n    return 2\n"}
    selected = [anchor(before), anchor(before, "second.py")]
    session = GraphSession(selected)
    session.update(before, "before")
    after = before | {"pkg/worker.py": "def compute():\n    return 100\n"}
    result = session.update(after, "after")
    assert (result.reused, result.rebuilt) == (1, 1)
    assert_fresh_parity(result, after, "after", selected)


@pytest.mark.parametrize("mode", sorted(GraphSession.MODES))
def test_baselines_and_certificate_match_fresh_build_across_revision_sequence(mode):
    before = package_sources()
    selected = anchor(before)
    session = GraphSession([selected], mode=mode)
    steps = [before, before | {"unrelated.py": "OTHER = 2\n"},
             before | {"pkg/__init__.py": "from alternate import *\n"},
             before, before | {"pkg/worker.pyi": "def compute(): ...\n"}, before]
    for i, texts in enumerate(steps):
        snapshot_id = "snapshot-" + str(i)
        result = session.update(texts, snapshot_id)
        assert_fresh_parity(result, texts, snapshot_id, [selected])
        if mode == "warm_ast_rebuild":
            assert result.reused == 0


@pytest.mark.parametrize("policy", [{"max_depth": -1}, {"max_nodes": 0},
                                     {"max_depth": True}, {"max_nodes": 1.5}])
def test_invalid_policy_cannot_yield_reusable_certificate(policy):
    before = package_sources()
    with pytest.raises(ValueError):
        session = GraphSession([anchor(before)], **policy)
        session.update(before, "before")


@pytest.mark.parametrize("mutation", [{"../escape.py": "PASS = 1\n"},
                                       {"pkg/worker.py": None}])
def test_failed_input_validation_preserves_last_valid_session(mutation):
    before = package_sources()
    selected = anchor(before)
    session = GraphSession([selected])
    session.update(before, "before")
    with pytest.raises(ValueError):
        session.update(before | mutation, "invalid")
    result = session.update(before, "after")
    assert result.reused == 1
    assert_fresh_parity(result, before, "after", [selected])


def test_update_failure_after_one_anchor_build_is_atomic(monkeypatch):
    import contextproof.reuse as implementation

    before = package_sources() | {"second.py": "def entry():\n    return 2\n"}
    selected = [anchor(before), anchor(before, "second.py")]
    session = GraphSession(selected)
    session.update(before, "before")
    after = before | {"pkg/worker.py": "def compute():\n    return 100\n",
                      "second.py": "def entry():\n    return 3\n"}
    original = implementation.build_graph
    calls = []

    def fail_second(*args, **kwargs):
        calls.append(args[2][0]["id"])
        if len(calls) == 2:
            raise RuntimeError("independent injected build failure")
        return original(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(implementation, "build_graph", fail_second)
        with pytest.raises(RuntimeError, match="injected build failure"):
            session.update(after, "failed-update")
    assert len(calls) == 2
    restored = session.update(before, "still-before")
    assert restored.reused == 2
    assert_fresh_parity(restored, before, "still-before", selected)
    retried = session.update(after, "successful-retry")
    assert retried.rebuilt == 2
    assert_fresh_parity(retried, after, "successful-retry", selected)


def test_same_snapshot_label_does_not_hide_changed_source_bytes():
    before = package_sources()
    selected = anchor(before)
    session = GraphSession([selected])
    session.update(before, "caller-label")
    after = before | {"pkg/worker.py": "def compute():\n    return 100\n"}
    result = session.update(after, "caller-label")
    assert result.reused == 0
    assert_fresh_parity(result, after, "caller-label", [selected])


def test_transitive_namespace_fallback_reads_each_existing_package():
    before = {"app.py": "import pkg\ndef entry():\n    return pkg.deep.worker.compute()\n",
              "pkg/__init__.py": "# empty outer package\n",
              "pkg/deep/__init__.py": "# empty inner package\n",
              "pkg/deep/worker.py": "def compute():\n    return 5\n"}
    selected = anchor(before)
    reads = set()
    initial = build_graph(before, "before", [selected], read_set=reads)
    assert not initial["frontier"]
    assert reads == set(before)
    for package in ("pkg/__init__.py", "pkg/deep/__init__.py"):
        session = GraphSession([selected])
        session.update(before, "before")
        after = before | {package: "def __getattr__(name):\n    return 0\n"}
        result = session.update(after, "after")
        assert result.reused == 0
        assert_fresh_parity(result, after, "after", [selected])


@pytest.mark.parametrize("policy", [{"max_depth": 2, "max_nodes": 10},
                                     {"max_depth": 3, "max_nodes": 100}])
def test_cached_graph_preserves_nondefault_policy(policy):
    before = package_sources()
    selected = anchor(before)
    session = GraphSession([selected], **policy)
    session.update(before, "before")
    after = before | {"unrelated.py": "OTHER = 999\n"}
    result = session.update(after, "after")
    assert result.reused == 1
    assert_fresh_parity(result, after, "after", [selected], **policy)
