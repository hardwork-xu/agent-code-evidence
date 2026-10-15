"""Incremental index invalidation and isolation / 增量摘要失效与隔离验证。

Fresh canonical graphs are the replay oracle, not a semantic soundness claim.
Counters independently verify that the stronger baseline actually skips indexing.
以新建图的规范字节验证回放，不声称语义完备；计数验证基线确实跳过重复索引。
"""

import ast
from copy import deepcopy
import gc
import hashlib
import weakref

import pytest

from contextproof import dependencies, reuse
from contextproof.dependencies import _Corpus
from contextproof.graph import build_graph, canonical_graph_bytes, compare_graphs, validate_graph
from contextproof.module_cache import ModuleCache
from contextproof.reuse import GraphSession


MODES = ("incremental_index_rebuild", "incremental_read_set", "incremental_whole_corpus_guard")


def anchor(texts, path="app.py"):
    node = next(item for item in ast.parse(texts[path]).body
                if isinstance(item, ast.FunctionDef) and item.name == "entry")
    text = "".join(texts[path].splitlines(keepends=True)[node.lineno - 1:node.end_lineno])
    return {"id": path + ":entry", "path": path, "symbol": "entry", "kind": "function",
            "start_line": node.lineno, "end_line": node.end_lineno, "text": text,
            "text_sha256": hashlib.sha256(text.encode()).hexdigest()}


def sources():
    return {"app.py": "import pkg\ndef entry():\n    return pkg.worker.compute()\n",
            "pkg/__init__.py": "# negative package attribute lookup\n",
            "pkg/worker.py": "def compute():\n    return 7\n",
            "other.py": "OTHER = 1\n", "notes.md": "not Python\n"}


def parity(session, texts, snapshot, selected, **policy):
    result = session.update(texts, snapshot)
    expected = [build_graph(texts, snapshot, [item], **policy) for item in selected]
    assert [canonical_graph_bytes(graph) for graph in result.graphs] == [
        canonical_graph_bytes(graph) for graph in expected]
    for graph in result.graphs:
        validate_graph(graph)
    return result


def test_strong_baseline_rebuilds_graphs_without_reindexing_or_reguarding_unchanged_modules(monkeypatch):
    texts = sources()
    selected = [anchor(texts)]
    indexed, guarded = [], []
    original_index = _Corpus._index
    original_guard = dependencies.guard_module_bindings

    def index(corpus, path, tree):
        indexed.append(path)
        return original_index(corpus, path, tree)

    def guard(corpus, paths=None):
        guarded.extend(corpus.trees if paths is None else paths)
        return original_guard(corpus, paths)

    with monkeypatch.context() as patch:
        patch.setattr(_Corpus, "_index", index)
        patch.setattr(dependencies, "guard_module_bindings", guard)
        session = GraphSession(selected, mode="incremental_index_rebuild")
        initial = session.update(texts, "first")
        assert len(indexed) == len(guarded) == 4
        indexed.clear()
        guarded.clear()
        stable = session.update(texts, "stable")
        assert not indexed and not guarded
        assert stable.rebuilt == 1 and stable.reused == 0
        assert session.index_stats == {"indexed_modules": 0, "reused_modules": 4,
                                       "invalid_modules": 0, "retained_modules": 4}
        changed = texts | {"other.py": "OTHER = 2\n"}
        result = session.update(changed, "changed")
        assert indexed == guarded == ["other.py"]
        assert session.index_stats["indexed_modules"] == 1
        assert session.index_stats["reused_modules"] == 3
    assert initial.graphs == [build_graph(texts, "first", selected)]
    assert result.graphs == [build_graph(changed, "changed", selected)]


def test_combined_whole_guard_reuses_equal_corpus_and_updates_only_changed_summary():
    texts = sources()
    selected = [anchor(texts)]
    session = GraphSession(selected, mode="incremental_whole_corpus_guard")
    parity(session, texts, "capture", selected)
    same = parity(session, texts, "same", selected)
    assert same.reused == 1 and same.rebuilt == 0
    assert session.index_stats == {"indexed_modules": 0, "reused_modules": 0,
                                   "invalid_modules": 0, "retained_modules": 4}
    changed = texts | {"other.py": "OTHER = 91\n"}
    different = parity(session, changed, "unrelated-change", selected)
    assert different.rebuilt == 1 and different.reused == 0
    assert session.index_stats["indexed_modules"] == 1
    assert session.index_stats["reused_modules"] == 3


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("replacement", [
    "def __getattr__(name):\n    return 1\n",
    "from other import *\n",
    "worker = 1\n",
    "not valid (\n",
    "class Guard:\n    global worker\n    worker = 1\n",
    "def f(value=(worker := 1)):\n    pass\n",
    "match 1:\n    case worker:\n        pass\n",
    "try:\n    pass\nexcept Exception as worker:\n    pass\n",
], ids=["getattr", "wildcard", "constant", "parse-error", "class-global",
        "definition-expression", "pattern", "exception-binding"])
def test_negative_lookup_and_source_local_guards_survive_reuse_then_invalidate(mode, replacement):
    before = sources()
    selected = [anchor(before)]
    session = GraphSession(selected, mode=mode)
    first = parity(session, before, "before", selected)
    assert "pkg/__init__.py" not in {node["path"] for node in first.graphs[0]["nodes"].values()}
    after = before | {"pkg/__init__.py": replacement}
    changed = parity(session, after, "changed", selected)
    assert changed.rebuilt == 1
    assert session.index_stats["indexed_modules"] == 1
    assert changed.graphs[0]["frontier"]
    unrelated = after | {"other.py": "OTHER = 2\n"}
    repeat = parity(session, unrelated, "repeat", selected)
    assert repeat.graphs[0]["frontier"] == changed.graphs[0]["frontier"]
    assert not compare_graphs(repeat.graphs[0], repeat.graphs[0])["fresh"]
    assert repeat.reused == (mode == "incremental_read_set")
    # A guard on a reused summary must not append duplicate dynamic bindings.
    again = parity(session, after, "again", selected)
    assert again.graphs[0]["frontier"] == changed.graphs[0]["frontier"]
    restored = parity(session, before, "restored", selected)
    assert not restored.graphs[0]["frontier"]


@pytest.mark.parametrize("replacement", ["worker = 1\n", "from other import *\n"])
def test_summary_hit_replays_negative_reads_into_rebuilt_graph_certificate(replacement):
    """Rebuild after anchor edit, then change a previously absent package binding.

    锚点改变触发重建后，缓存摘要的负向查找仍必须登记到新图的失效证书。
    """
    before = sources()
    selected = [anchor(before)]
    session = GraphSession(selected, mode="incremental_read_set")
    parity(session, before, "initial", selected)
    edited = before | {"app.py": before["app.py"].replace(
        "return pkg.worker.compute()", "return pkg.worker.compute() + 1")}
    rebuilt = parity(session, edited, "anchor-edit", selected)
    assert rebuilt.rebuilt == 1
    assert session.index_stats["indexed_modules"] == 1
    assert session.index_stats["reused_modules"] == 3
    assert "pkg/__init__.py" not in {n["path"] for n in rebuilt.graphs[0]["nodes"].values()}
    changed = edited | {"pkg/__init__.py": replacement}
    invalidated = parity(session, changed, "negative-binding-changed", selected)
    assert invalidated.rebuilt == 1 and invalidated.reused == 0
    assert invalidated.graphs[0]["frontier"]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("collision", ["src/pkg/worker.py", "pkg/worker.pyi", "pkg/worker/__init__.py"])
def test_catalog_collisions_add_remove_and_restore_without_invalidating_local_summaries(mode, collision):
    before = sources()
    selected = [anchor(before)]
    session = GraphSession(selected, mode=mode)
    parity(session, before, "before", selected)
    after = before | {collision: "def compute():\n    return 91\n"}
    result = parity(session, after, "collision", selected)
    assert result.rebuilt == 1 and result.graphs[0]["frontier"]
    assert session.index_stats["indexed_modules"] == 1
    assert session.index_stats["reused_modules"] == 4
    restored = parity(session, before, "restored", selected)
    assert not restored.graphs[0]["frontier"]
    assert session.index_stats["indexed_modules"] == 0
    assert session.index_stats["retained_modules"] == 4
    removed = {path: source for path, source in before.items() if path != "pkg/worker.py"}
    missing = parity(session, removed, "removed", selected)
    assert missing.graphs[0]["frontier"] and missing.rebuilt == 1
    assert session.index_stats["retained_modules"] == 3
    parity(session, before, "readded", selected)
    assert session.index_stats["indexed_modules"] == 1


@pytest.mark.parametrize("mode", MODES)
def test_invalid_to_valid_and_back_retains_parse_failure_summary_without_stale_resolution(mode):
    valid = sources()
    selected = [anchor(valid)]
    broken = valid | {"pkg/worker.py": "def compute(\n"}
    session = GraphSession(selected, mode=mode)
    first = parity(session, broken, "broken", selected)
    assert first.graphs[0]["frontier"]
    assert session.index_stats == {"indexed_modules": 4, "reused_modules": 0,
                                   "invalid_modules": 1, "retained_modules": 4}
    parity(session, broken, "stable-broken", selected)
    assert session.index_stats["indexed_modules"] == 0
    fixed = parity(session, valid, "fixed", selected)
    assert not fixed.graphs[0]["frontier"] and fixed.rebuilt == 1
    assert session.index_stats["indexed_modules"] == 1
    assert session.index_stats["invalid_modules"] == 0
    result = parity(session, broken, "broken-again", selected)
    assert result.graphs[0]["frontier"] and result.rebuilt == 1
    assert session.index_stats["indexed_modules"] == 1
    assert session.index_stats["invalid_modules"] == 1


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("policy", [{"max_nodes": 1}, {"max_depth": 0}, {"max_depth": 1}])
def test_truncation_is_preserved_and_looked_up_but_excluded_targets_still_invalidate(mode, policy):
    before = sources()
    selected = [anchor(before)]
    session = GraphSession(selected, mode=mode, **policy)
    first = parity(session, before, "before", selected, **policy)
    assert first.graphs[0]["frontier"]
    other = before | {"other.py": "OTHER = 2\n"}
    replay = parity(session, other, "unrelated", selected, **policy)
    assert replay.reused == (mode == "incremental_read_set")
    assert replay.graphs[0]["frontier"] == first.graphs[0]["frontier"]
    changed = other | {"pkg/worker.py": "def compute():\n    return 21\n"}
    result = parity(session, changed, "changed", selected, **policy)
    assert result.reused == (mode == "incremental_read_set" and policy.get("max_depth") == 0)
    assert not compare_graphs(result.graphs[0], result.graphs[0])["fresh"]


@pytest.mark.parametrize("mode", MODES)
def test_retention_bounded_by_current_python_sources_across_long_edits_and_removals(mode):
    before = sources()
    selected = [anchor(before)]
    session = GraphSession(selected, mode=mode)
    parity(session, before, "first", selected)
    old_tree = weakref.ref(next(value.tree for key, value in session._module_cache._entries.items()
                               if key[0] == "other.py"))
    for revision in range(20):
        changed = before | {"other.py": f"OTHER = {revision + 2}\n"}
        parity(session, changed, f"revision-{revision}", selected)
        entries = session._module_cache._entries
        assert len(entries) <= 4
        assert all(digest == hashlib.sha256(changed[path].encode()).hexdigest()
                   for path, digest in entries)
        # The candidate may defer indexing an unread changed file; it must evict
        # its former summary even while all graphs are reused.
        assert session.index_stats["retained_modules"] == (3 if mode == "incremental_read_set" else 4)
    gc.collect()
    assert old_tree() is None
    assert not session._cache.memory  # No second retained AST pool in these modes.
    only_anchor = {"app.py": before["app.py"]}
    parity(session, only_anchor, "removed", selected)
    assert session.index_stats["retained_modules"] == 1
    parity(session, {}, "empty", selected)
    assert session.index_stats["retained_modules"] == 0


def test_reused_module_summary_never_caches_resolution_or_mutable_corpus_catalog():
    texts = sources()
    cache = ModuleCache()
    first = _Corpus.from_texts(texts, module_cache=cache)
    assert first.resolve_name("app.py", "pkg", ["worker", "compute"])["status"] == "resolved"
    other = texts | {"pkg/worker.py": "def compute(\n"}
    hashes = {path: hashlib.sha256(source.encode()).hexdigest() for path, source in other.items()}
    next_cache = cache.for_snapshot(hashes)
    second = _Corpus.from_texts(other, module_cache=next_cache)
    assert second.resolve_name("app.py", "pkg", ["worker", "compute"])["status"] == "unresolved"
    assert first.resolve_name("app.py", "pkg", ["worker", "compute"])["status"] == "resolved"
    assert first.lookup_paths is not second.lookup_paths
    second.lookup_paths.clear()
    second.modules["pkg"].append("collision.py")
    second.wildcards.add("app.py")
    assert first.modules["pkg"] == ["pkg/__init__.py"]
    assert "app.py" not in first.wildcards
    with pytest.raises(TypeError):
        second.bindings["app.py"]["pkg"][0]["module"] = "poisoned"
    with pytest.raises(TypeError):
        second.definitions["app.py"]["entry"] = ()


def test_resolver_reads_shared_ast_without_mutating_its_nodes_or_lists():
    texts = {
        "app.py": "from helper import compute\nVALUE = -2\n"
                  "def entry(default=(VALUE := 2)):\n"
                  "    return (compute if True else compute)([i for i in range(VALUE)])\n",
        "helper.py": "def compute(value):\n    return value\n",
    }
    selected = [anchor(texts)]
    session = GraphSession(selected, mode="incremental_index_rebuild")
    parity(session, texts, "before", selected)
    original = {key: (entry.tree, ast.dump(entry.tree, include_attributes=True))
                for key, entry in session._module_cache._entries.items()}
    for snapshot in ("rebuild-1", "rebuild-2"):
        parity(session, texts, snapshot, selected)
        assert session.index_stats["indexed_modules"] == 0
        for key, summary in session._module_cache._entries.items():
            assert summary.tree is original[key][0]
            assert ast.dump(summary.tree, include_attributes=True) == original[key][1]


@pytest.mark.parametrize("mode", MODES)
def test_session_inputs_outputs_and_independent_corpora_cannot_poison_cached_summaries(mode):
    texts = sources()
    selected = [anchor(texts)]
    session = GraphSession(selected, mode=mode)
    independent = GraphSession(selected, mode=mode)
    first = parity(session, texts, "first", selected)
    other = texts | {"pkg/worker.py": "def compute():\n    return 37\n"}
    parity(independent, other, "independent", selected)
    first.graphs[0]["nodes"].clear()
    first.graphs[0]["frontier"].append({"poisoned": True})
    stats = session.index_stats
    stats["retained_modules"] = 1000
    changed_input = dict(texts)
    session.update(changed_input, "copied-input")
    changed_input["pkg/worker.py"] = "not valid (\n"
    parity(session, texts, "restored-original", selected)
    assert session.index_stats["retained_modules"] == 4
    assert session._module_cache is not independent._module_cache


@pytest.mark.parametrize("mode", MODES)
def test_failed_update_discards_new_summaries_and_preserves_previous_graphs_and_reads(mode, monkeypatch):
    before = {"a.py": "def entry():\n    return 1\n", "b.py": "def entry():\n    return 2\n"}
    selected = [anchor(before, path) for path in sorted(before)]
    session = GraphSession(selected, mode=mode)
    parity(session, before, "before", selected)
    original_cache = session._module_cache
    original_hashes = dict(session._hashes)
    original_graphs, original_reads = deepcopy(session._graphs), deepcopy(session._reads)
    after = {"a.py": "def entry():\n    return 3\n", "b.py": "def entry():\n    return 4\n"}
    original_build = reuse.build_graph
    calls = 0

    def failing_build(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls % 2 == 0:
            raise RuntimeError("injected second-anchor failure")
        return original_build(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(reuse, "build_graph", failing_build)
        for index in range(5):
            with pytest.raises(RuntimeError, match="second-anchor"):
                session.update(after | {f"new-{index}.py": "VALUE = 1\n"}, "failed")
            assert session._module_cache is original_cache
            assert session._hashes == original_hashes
            assert session._graphs == original_graphs and session._reads == original_reads
            assert session.index_stats["retained_modules"] == 2
    parity(session, before, "after-failure", selected)
    parity(session, after, "success", selected)
    assert session.index_stats["indexed_modules"] == 2
