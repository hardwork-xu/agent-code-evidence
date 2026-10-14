"""Independent catalog reuse acceptance / 独立目录复用验收。

The 24 cases were specified before implementation. Fresh construction is the
resolver replay oracle, not evidence of Python runtime semantics or speedup.
反例先于实现固定；完整规范字节只证明解析器回放一致，不证明运行语义或性能。
"""

import ast
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import inspect
import textwrap

import pytest

from contextproof import dependencies, reuse, static_scope
from contextproof.catalog import CATALOG_TRACE_VERSION, ModuleCatalog
from contextproof.graph import build_graph, canonical_graph_bytes, compare_graphs, validate_graph
from contextproof.reuse import GraphSession


WHOLE = "incremental_read_set"
COARSE = "incremental_catalog_coarse_guard"
ROOT = "incremental_catalog_root_guard"
FINE = "incremental_catalog_read_set"
NEW_MODES = (COARSE, ROOT, FINE)
MODES = (WHOLE, *NEW_MODES)

APP = "import pkg\ndef entry():\n    return pkg.worker.compute()\n"
WORKER = "def compute():\n    return 7\n"
COMPLETE = {"app.py": APP, "pkg/__init__.py": "", "pkg/worker.py": WORKER}
NAMESPACE = {"app.py": APP, "pkg/worker.py": WORKER}
DEEP_APP = "import pkg\ndef entry():\n    return pkg.deep.worker.compute()\n"
DEEP = {"app.py": DEEP_APP, "pkg/deep/worker.py": WORKER}


def anchor(texts, path="app.py"):
    node = next(item for item in ast.parse(texts[path]).body
                if isinstance(item, ast.FunctionDef) and item.name == "entry")
    text = "".join(texts[path].splitlines(keepends=True)[node.lineno - 1:node.end_lineno])
    return {"id": path + ":entry", "path": path, "symbol": "entry", "kind": "function",
            "start_line": node.lineno, "end_line": node.end_lineno, "text": text,
            "text_sha256": hashlib.sha256(text.encode()).hexdigest()}


@dataclass(frozen=True)
class Case:
    case_id: str
    before: dict[str, str]
    after: dict[str, str]
    equal: bool
    reuse_modes: tuple[str, ...] = ()
    policy: dict[str, int] = field(default_factory=dict)
    anchor_sources: dict[str, str] | None = None
    anchor_path: str = "app.py"


def cases():
    literal = {"app.py": "def entry():\n    return 1\n"}
    module_value = {"app.py": "import pkg\ndef entry():\n    return pkg\n"}
    missing = {"app.py": APP}
    negative_deep = {"app.py": DEEP_APP}
    # The unread descendant controls subtree truth. A direct pkg candidate makes
    # the true-to-false transition change the resolver's frontier reason.
    last_descendant = {"app.py": DEEP_APP, "pkg/__init__.py": "",
                       "pkg/deep/other.py": "VALUE = 1\n"}
    relative = {"src/pkg/use.py": "from .worker import compute\n"
                "def entry():\n    return compute()\n", "src/pkg/worker.py": WORKER}
    sibling = COMPLETE | {"pkg/other.py": "VALUE = 1\n"}
    adjacent = {"app.py": "import pkg\ndef entry():\n    return pkg.a.f()\n"}
    getattr_init = "def __getattr__(name):\n    return 99\n"
    return (
        Case("C01", literal, literal | {"elsewhere.py": "X = 1\n"}, True, NEW_MODES),
        Case("C02", module_value, module_value | {"pkg.py": "X = 1\n"}, True, NEW_MODES),
        Case("C03", COMPLETE, COMPLETE | {"elsewhere.py": "X = 1\n"}, True, (ROOT, FINE)),
        Case("C04", COMPLETE, COMPLETE | {"pkg/other.py": "X = 1\n"}, True, (FINE,)),
        Case("C05", DEEP, DEEP | {"pkg/deep/other.py": "X = 1\n"}, True, (FINE,)),
        Case("C06", missing, missing | {"pkg/other.py": "X = 1\n"}, True, (FINE,)),
        Case("C07", COMPLETE, COMPLETE | {"notes.txt": "notes\n"}, True, (ROOT, FINE)),
        Case("C08", sibling, COMPLETE | {"pkg/renamed.py": "VALUE = 1\n"}, True, (FINE,)),
        Case("C09", COMPLETE, COMPLETE | {"pkg/worker.pyi": WORKER}, False),
        Case("C10", COMPLETE, COMPLETE | {"src/pkg/worker.py": WORKER}, False),
        Case("C11", COMPLETE, COMPLETE | {"pkg/worker/__init__.py": WORKER}, False),
        Case("C12", COMPLETE, COMPLETE | {"pkg/worker.PY": "broken(\n"}, False),
        Case("C13", COMPLETE, {k: v for k, v in COMPLETE.items() if k != "pkg/worker.py"},
             False),
        Case("C14", COMPLETE, {k: v for k, v in COMPLETE.items() if k != "pkg/worker.py"}
             | {"pkg/worker.pyi": WORKER}, False),
        Case("C15", negative_deep, DEEP, False),
        Case("C16", last_descendant, {k: v for k, v in last_descendant.items()
             if k != "pkg/deep/other.py"}, False),
        Case("C17", NAMESPACE, NAMESPACE | {"pkg/__init__.py": ""}, True),
        Case("C18", NAMESPACE | {"pkg/__init__.py": ""},
             NAMESPACE | {"pkg/__init__.py": getattr_init}, False),
        Case("C19", COMPLETE, COMPLETE | {"pkg/__init__.py": "worker = 99\n"}, False),
        Case("C20", relative, relative | {"pkg/worker.py": WORKER}, False,
             anchor_path="src/pkg/use.py"),
        Case("C21", COMPLETE, COMPLETE | {"pkg/worker.pyi": WORKER}, False,
             policy={"max_nodes": 1}),
        Case("C22", COMPLETE, COMPLETE | {"pkg/worker.pyi": WORKER}, True, NEW_MODES,
             policy={"max_depth": 0}),
        Case("C23", adjacent, adjacent | {"pkg/ab.py": "def f():\n    return 1\n"},
             True, (FINE,)),
        Case("C24", {}, literal, False, anchor_sources=literal),
    )


CASES = cases()


def parity(session, texts, snapshot, selected, **policy):
    result = session.update(texts, snapshot)
    expected = [build_graph(texts, snapshot, [item], **policy) for item in selected]
    assert [canonical_graph_bytes(graph) for graph in result.graphs] == [
        canonical_graph_bytes(graph) for graph in expected]
    for graph in result.graphs:
        validate_graph(graph)
    return result


def test_fixed_matrix_has_all_24_preimplementation_cases():
    assert [case.case_id for case in CASES] == [f"C{number:02}" for number in range(1, 25)]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_frozen_fresh_expectations(case):
    """The oracle fixture itself must have the previously specified behavior."""
    selected = [anchor(case.anchor_sources or case.before, case.anchor_path)]
    before = build_graph(case.before, "fixed-oracle", selected, **case.policy)
    after = build_graph(case.after, "fixed-oracle", selected, **case.policy)
    assert (canonical_graph_bytes(before) == canonical_graph_bytes(after)) is case.equal


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_24_case_catalog_guard_matrix_matches_canonical_fresh(mode, case):
    selected = [anchor(case.anchor_sources or case.before, case.anchor_path)]
    session = GraphSession(selected, mode=mode, **case.policy)
    initial = parity(session, case.before, "capture", selected, **case.policy)
    assert initial.rebuilt == 1 and initial.reused == 0
    result = parity(session, case.after, "changed", selected, **case.policy)
    assert result.reused == int(mode in case.reuse_modes)
    assert result.rebuilt == 1 - int(mode in case.reuse_modes)
    # Repeated capture with a new provider identity reseals an unchanged result.
    stable = parity(session, case.after, "stable-again", selected, **case.policy)
    assert stable.reused == 1 and stable.rebuilt == 0


@pytest.mark.parametrize("mode", NEW_MODES)
def test_empty_namespace_init_then_getattr_refreshes_consulted_source_dependency(mode):
    selected = [anchor(NAMESPACE)]
    session = GraphSession(selected, mode=mode)
    first = parity(session, NAMESPACE, "namespace", selected)
    with_init = NAMESPACE | {"pkg/__init__.py": ""}
    appeared = parity(session, with_init, "empty-init-appeared", selected)
    assert appeared.rebuilt == 1 and appeared.reused == 0
    assert "pkg/__init__.py" in session._reads[0]
    assert "pkg/__init__.py" not in {n["path"] for n in appeared.graphs[0]["nodes"].values()}
    changed = with_init | {"pkg/__init__.py": "def __getattr__(name):\n    return 99\n"}
    guarded = parity(session, changed, "getattr-appeared", selected)
    assert guarded.rebuilt == 1 and guarded.reused == 0
    assert not first.graphs[0]["frontier"] and guarded.graphs[0]["frontier"]
    assert any("__getattr__" in item["reason"] for item in guarded.graphs[0]["frontier"])


@pytest.mark.parametrize("mode", NEW_MODES)
@pytest.mark.parametrize("guard", [
    "from other import *\n",
    "def __getattr__(name):\n    return 99\n",
    "class Guard:\n    global worker\n    worker = 99\n",
    "worker = load()\n",
    "not valid (\n",
], ids=["wildcard", "getattr", "class-global", "dynamic", "parse-error"])
def test_unknown_guards_survive_reuse_and_can_return_to_complete(mode, guard):
    texts = COMPLETE | {"pkg/__init__.py": guard, "other.py": "VALUE = 1\n"}
    selected = [anchor(texts)]
    session = GraphSession(selected, mode=mode)
    first = parity(session, texts, "guarded", selected)
    assert first.graphs[0]["frontier"]
    assert not compare_graphs(first.graphs[0], first.graphs[0])["fresh"]
    unrelated = texts | {"other.py": "VALUE = 2\n"}
    replay = parity(session, unrelated, "unknown-replay", selected)
    assert replay.reused == 1 and replay.rebuilt == 0
    assert replay.graphs[0]["frontier"] == first.graphs[0]["frontier"]
    assert not compare_graphs(replay.graphs[0], replay.graphs[0])["fresh"]
    repaired = unrelated | {"pkg/__init__.py": ""}
    result = parity(session, repaired, "guard-removed", selected)
    assert result.rebuilt == 1 and not result.graphs[0]["frontier"]


@pytest.mark.parametrize("mode", NEW_MODES)
def test_parse_error_candidate_source_is_read_even_without_target_node(mode):
    texts = COMPLETE | {"pkg/worker.py": "def compute(\n"}
    selected = [anchor(texts)]
    session = GraphSession(selected, mode=mode)
    initial = parity(session, texts, "parse-error", selected)
    assert initial.graphs[0]["frontier"]
    assert "pkg/worker.py" in session._reads[0]
    assert "pkg/worker.py" not in {n["path"] for n in initial.graphs[0]["nodes"].values()}
    replay = parity(session, texts | {"pkg/other.py": "VALUE = 1\n"}, "sibling", selected)
    assert replay.reused == (mode == FINE)
    fixed = parity(session, COMPLETE, "fixed", selected)
    assert fixed.rebuilt == 1 and not fixed.graphs[0]["frontier"]


@pytest.mark.parametrize("mode", NEW_MODES)
@pytest.mark.parametrize("reverse", [False, True])
def test_query_footprints_do_not_leak_between_anchors_or_mixed_rebuild_and_reuse(mode, reverse):
    texts = COMPLETE | {"literal.py": "def entry():\n    return 1\n"}
    selected = [anchor(texts), anchor(texts, "literal.py")]
    if reverse:
        selected.reverse()
    session = GraphSession(selected, mode=mode)
    parity(session, texts, "capture", selected)
    by_path = {item["path"]: session._catalog_footprints[index]
               for index, item in enumerate(selected)}
    assert by_path["literal.py"] == {} and by_path["app.py"]
    assert by_path["literal.py"] is not by_path["app.py"]
    collision = texts | {"pkg/worker.pyi": WORKER}
    result = parity(session, collision, "collision", selected)
    assert result.reused == 1 and result.rebuilt == 1
    # The queried graph rebuilds; the literal graph retains a genuine zero-query
    # certificate even when it was built after a queried graph in the same corpus.
    changed = collision | {"pkg/extra.py": "VALUE = 1\n"}
    result = parity(session, changed, "mixed-next-update", selected)
    assert result.reused == (2 if mode == FINE else 1)
    assert result.rebuilt == (0 if mode == FINE else 1)
    for graph, selected_anchor in zip(result.graphs, selected):
        assert bool(graph["frontier"]) is (selected_anchor["path"] == "app.py")


@pytest.mark.parametrize("mode", NEW_MODES)
def test_inputs_original_anchors_policy_and_returned_graphs_are_isolated(mode):
    texts = deepcopy(COMPLETE)
    selected = [anchor(texts)]
    saved_anchors = deepcopy(selected)
    policy = {"max_depth": 4, "max_nodes": 256}
    session = GraphSession(selected, mode=mode, **policy)
    first = parity(session, texts, "capture", saved_anchors, **policy)
    texts["pkg/worker.py"] = "invalid (\n"
    selected[0].update(path="poisoned.py", text="poisoned", id="poisoned")
    policy.update(max_depth=0, max_nodes=1)
    first.graphs[0]["nodes"].clear()
    first.graphs[0]["frontier"].append({"poisoned": True})
    first.reasons["poisoned"] = 100
    stats = session.index_stats
    stats["retained_modules"] = 100
    result = parity(session, COMPLETE, "isolation-replay", saved_anchors,
                    max_depth=4, max_nodes=256)
    assert result.reused == 1 and result.rebuilt == 0
    assert not result.graphs[0]["frontier"]
    assert "poisoned" not in result.reasons
    assert session.index_stats["retained_modules"] == 3
    assert set(result.graphs[0]) == set(build_graph(COMPLETE, "isolation-replay", saved_anchors))


@pytest.mark.parametrize("mode", NEW_MODES)
def test_failed_second_anchor_update_is_atomic_then_retry_recovers(mode, monkeypatch):
    texts = COMPLETE | {"second.py": "import pkg\ndef entry():\n    return pkg.worker.compute()\n"}
    selected = [anchor(texts), anchor(texts, "second.py")]
    session = GraphSession(selected, mode=mode)
    initial = parity(session, texts, "committed", selected)
    original_cache = session._module_cache
    original_hashes = deepcopy(session._hashes)
    original_reads = deepcopy(session._reads)
    original_graphs = deepcopy(session._graphs)
    original_stats = deepcopy(session.index_stats)
    original_footprints = deepcopy(session._catalog_footprints)
    original_roots = deepcopy(session._catalog_root_guards)
    original_catalog_stats = deepcopy(session.catalog_stats)
    original_versions = deepcopy(session._catalog_versions)
    changed = texts | {"pkg/worker.pyi": WORKER, "new.py": "VALUE = 1\n"}
    original_build = reuse.build_graph
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("bounded injected second-anchor failure")
        return original_build(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(reuse, "build_graph", fail_second)
        with pytest.raises(RuntimeError, match="second-anchor failure"):
            session.update(changed, "failed-not-committed")
    assert calls == 2
    assert session._module_cache is original_cache
    assert session._hashes == original_hashes
    assert session._reads == original_reads
    assert session._graphs == original_graphs
    assert session.index_stats == original_stats
    assert session._catalog_footprints == original_footprints
    assert session._catalog_root_guards == original_roots
    assert session.catalog_stats == original_catalog_stats
    assert session._catalog_versions == original_versions
    retry_original = parity(session, texts, "retry-original", selected)
    assert retry_original.reused == 2 and retry_original.rebuilt == 0
    assert [graph["frontier"] for graph in retry_original.graphs] == [
        graph["frontier"] for graph in initial.graphs]
    success = parity(session, changed, "retry-success", selected)
    assert success.rebuilt == 2 and success.reused == 0
    assert session.index_stats["indexed_modules"] == 2


def test_catalog_consumers_use_query_primitives_without_bypassing_uncertainty_guard():
    """Static audit supplements the wildcard/getattr behavioral assertions."""
    for function in (dependencies._Corpus.resolve_module, static_scope.module_lookup_uncertainty):
        tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
        assert not any(isinstance(node, ast.Attribute) and node.attr == "modules"
                       for node in ast.walk(tree))
    source = inspect.getsource(dependencies._Corpus.resolve_module)
    assert "module_lookup_uncertainty" in source


@pytest.mark.parametrize("mode", NEW_MODES)
def test_positive_negative_exact_and_subtree_answers_are_retained(mode):
    selected = [anchor(DEEP)]
    session = GraphSession(selected, mode=mode)
    parity(session, DEEP, "namespace", selected)
    observed = session._catalog_footprints[0]
    assert observed[("exact", "pkg")] == ()
    assert observed[("exact", "pkg.deep")] == ()
    assert observed[("exact", "pkg.deep.worker")] == ("pkg/deep/worker.py",)
    assert observed[("subtree", "pkg.deep")] is True
    assert observed[("subtree", "pkg.deep.worker")] is True
    absent = {"app.py": DEEP_APP}
    changed = parity(session, absent, "missing-namespace", selected)
    assert changed.rebuilt == 1
    assert session._catalog_footprints[0][("exact", "pkg")] == ()
    assert session._catalog_footprints[0][("subtree", "pkg.deep")] is False
    stats = session.catalog_stats
    assert stats["tracked_graphs"] == 1 and stats["catalog_free_graphs"] == 0
    assert stats["available_traces"] == 1
    assert stats["exact_queries"] >= 1 and stats["subtree_queries"] >= 1
    stats["exact_queries"] = 1000
    assert session.catalog_stats["exact_queries"] < 1000


@pytest.mark.parametrize("mode", NEW_MODES)
def test_relative_src_query_records_normalized_module_and_alias_root(mode):
    texts = {"src/pkg/use.py": "from .worker import compute\n"
             "def entry():\n    return compute()\n", "src/pkg/worker.py": WORKER}
    selected = [anchor(texts, "src/pkg/use.py")]
    session = GraphSession(selected, mode=mode)
    parity(session, texts, "src-relative", selected)
    assert session._catalog_footprints[0][("exact", "pkg.worker")] == ("src/pkg/worker.py",)
    assert "pkg" in session._catalog_root_guards[0]
    assert not any(name.startswith(".") for _, name in session._catalog_footprints[0])
    # Physical src root is not a substitute for its normalized pkg alias root.
    collision = texts | {"pkg/worker.py": WORKER}
    result = parity(session, collision, "normalized-alias-collision", selected)
    assert result.rebuilt == 1 and result.reused == 0


def test_fault_seed_ignoring_empty_exact_answers_is_exposed_by_init_then_getattr(monkeypatch):
    """Test-only unsound observation filtering; never a supported production mode."""
    selected = [anchor(NAMESPACE)]
    session = GraphSession(selected, mode=FINE)
    original = dependencies._Corpus.module_candidates

    def discard_empty(corpus, name):
        result = original(corpus, name)
        if not result:
            corpus.catalog_queries.pop(("exact", name), None)
        return result

    with monkeypatch.context() as patch:
        patch.setattr(dependencies._Corpus, "module_candidates", discard_empty)
        parity(session, NAMESPACE, "faulty-capture", selected)
    assert ("exact", "pkg") not in session._catalog_footprints[0]
    with_init = NAMESPACE | {"pkg/__init__.py": ""}
    equal_now = parity(session, with_init, "init-appeared", selected)
    assert equal_now.reused == 1  # Wrong guard decision even though output agrees now.
    assert "pkg/__init__.py" not in session._reads[0]
    guarded = with_init | {"pkg/__init__.py": "def __getattr__(name):\n    return 99\n"}
    with pytest.raises(AssertionError):
        parity(session, guarded, "fault-exposed", selected)


@pytest.mark.parametrize("truth", [False, True], ids=["false-to-true", "true-to-false"])
def test_fault_seed_ignoring_subtree_answers_is_exposed_by_namespace_transition(monkeypatch, truth):
    case = next(case for case in CASES if case.case_id == ("C16" if truth else "C15"))
    selected = [anchor(case.before)]
    session = GraphSession(selected, mode=FINE)
    original = dependencies._Corpus.module_subtree_exists

    def discard_truth(corpus, name):
        result = original(corpus, name)
        if result is truth:
            corpus.catalog_queries.pop(("subtree", name), None)
        return result

    with monkeypatch.context() as patch:
        patch.setattr(dependencies._Corpus, "module_subtree_exists", discard_truth)
        parity(session, case.before, "faulty-capture", selected)
    assert not any(kind == "subtree" and value is truth
                   for (kind, _), value in session._catalog_footprints[0].items())
    # In C16 the removed file was not a source read: only the missing subtree
    # observation can reject the otherwise byte-stable consulted dependencies.
    if truth:
        assert "pkg/deep/other.py" not in session._reads[0]
    with pytest.raises(AssertionError):
        parity(session, case.after, "fault-exposed", selected)


def test_fault_seed_ignoring_consulted_source_hash_is_exposed_without_catalog_change():
    selected = [anchor(COMPLETE)]
    session = GraphSession(selected, mode=FINE)
    parity(session, COMPLETE, "capture", selected)
    assert "pkg/__init__.py" in session._reads[0]
    changed = COMPLETE | {"pkg/__init__.py": "worker = 99\n"}
    assert ModuleCatalog(changed).matches(session._catalog_footprints[0])
    # Internal test-owned fault removes precisely the negative attribute read.
    # This is not an external certificate API or a production ablation.
    session._reads[0].remove("pkg/__init__.py")
    with pytest.raises(AssertionError):
        parity(session, changed, "fault-exposed", selected)


@pytest.mark.parametrize("guard", [
    "from other import *\n", "def __getattr__(name):\n    return 99\n",
], ids=["wildcard", "getattr"])
def test_fault_seed_bypassing_uncertainty_guard_disagrees_with_saved_fresh_oracle(monkeypatch, guard):
    texts = COMPLETE | {"pkg/__init__.py": guard}
    selected = [anchor(texts)]
    expected = build_graph(texts, "same-snapshot", selected)
    assert expected["frontier"]
    with monkeypatch.context() as patch:
        patch.setattr(dependencies, "module_lookup_uncertainty", lambda *args: None)
        session = GraphSession(selected, mode=FINE)
        faulty = session.update(texts, "same-snapshot")
    assert canonical_graph_bytes(faulty.graphs[0]) != canonical_graph_bytes(expected)
    assert not faulty.graphs[0]["frontier"]


@pytest.mark.parametrize("mode", NEW_MODES)
def test_even_zero_query_reuse_hashes_every_source_and_constructs_current_catalog(mode, monkeypatch):
    """Deterministic work accounting, not a timing or speedup experiment."""
    texts = {"app.py": "def entry():\n    return 1\n", "other.py": "VALUE = 1\n",
             "notes.txt": "notes\n"}
    selected = [anchor(texts)]
    session = GraphSession(selected, mode=mode)
    parity(session, texts, "capture", selected)
    hashed, indexed = [], []
    original_hash = reuse.sha256
    original_catalog = reuse.ModuleCatalog

    def record_hash(source):
        hashed.append(source)
        return original_hash(source)

    def record_catalog(paths):
        indexed.append(tuple(paths))
        return original_catalog(paths)

    changed = texts | {"pkg/unread.py": "UNREAD = 1\n"}
    with monkeypatch.context() as patch:
        patch.setattr(reuse, "sha256", record_hash)
        patch.setattr(reuse, "ModuleCatalog", record_catalog)
        result = session.update(changed, "all-input-work")
    assert result.reused == 1 and result.rebuilt == 0
    assert hashed == list(changed.values())
    assert indexed == [tuple(changed)]
    expected = build_graph(changed, "all-input-work", selected)
    assert canonical_graph_bytes(result.graphs[0]) == canonical_graph_bytes(expected)


@pytest.mark.parametrize("mode", NEW_MODES)
@pytest.mark.parametrize("invalid", [
    {"../escape.py": "VALUE = 1\n"}, {"new.py": 99},
], ids=["unsafe-path", "nontext-source"])
def test_rejected_inputs_do_not_publish_hashes_graphs_or_query_state(mode, invalid):
    selected = [anchor(COMPLETE)]
    session = GraphSession(selected, mode=mode)
    parity(session, COMPLETE, "capture", selected)
    prior = deepcopy((session._hashes, session._graphs, session._reads,
                      session._catalog_footprints, session._catalog_root_guards))
    prior_cache = session._module_cache
    prior_stats = deepcopy(session.index_stats)
    with pytest.raises(ValueError):
        session.update(COMPLETE | invalid, "invalid-input")
    assert (session._hashes, session._graphs, session._reads,
            session._catalog_footprints, session._catalog_root_guards) == prior
    assert session._module_cache is prior_cache
    assert session.index_stats == prior_stats
    retry = parity(session, COMPLETE, "valid-retry", selected)
    assert retry.reused == 1 and retry.rebuilt == 0


@pytest.mark.parametrize("mode", NEW_MODES)
@pytest.mark.parametrize("queried", [False, True], ids=["zero-query", "queried"])
@pytest.mark.parametrize("fault", [
    "missing-version", "none-version", "unsupported-version", "missing-footprint",
    "none-footprint", "nondict-footprint", "missing-root-guard", "none-root-guard",
])
def test_missing_or_unsupported_catalog_certificate_rebuilds_then_refreshes(mode, queried, fault):
    texts = COMPLETE if queried else {"app.py": "def entry():\n    return 1\n"}
    selected = [anchor(texts)]
    session = GraphSession(selected, mode=mode)
    parity(session, texts, "valid-capture", selected)
    assert session._catalog_versions == [CATALOG_TRACE_VERSION]
    assert bool(session._catalog_footprints[0]) is queried
    if fault == "missing-version":
        session._catalog_versions = []
    elif fault == "none-version":
        session._catalog_versions = [None]
    elif fault == "unsupported-version":
        session._catalog_versions = [CATALOG_TRACE_VERSION + 1]
    elif fault == "missing-footprint":
        session._catalog_footprints = []
    elif fault == "none-footprint":
        session._catalog_footprints = [None]
    elif fault == "nondict-footprint":
        session._catalog_footprints = [()]
    elif fault == "missing-root-guard":
        session._catalog_root_guards = []
    elif fault == "none-root-guard":
        session._catalog_root_guards = [None]
    else:
        raise AssertionError("unrecognized test-owned certificate fault")
    assert session.catalog_stats["available_traces"] == 0
    assert session.catalog_stats["catalog_free_graphs"] == 0
    # Keep catalog/source identical: the shortcut must not bypass trace validity.
    refreshed = parity(session, texts, "same-bytes-invalid-trace", selected)
    assert refreshed.rebuilt == 1 and refreshed.reused == 0
    assert refreshed.reasons == {"catalog_trace_unavailable": 1}
    assert session._catalog_versions == [CATALOG_TRACE_VERSION]
    assert session.catalog_stats["available_traces"] == 1
    stable = parity(session, texts, "valid-refreshed-trace", selected)
    assert stable.reused == 1 and stable.rebuilt == 0
    collision = texts | {"pkg/worker.pyi": WORKER}
    changed = parity(session, collision, "follow-up-guard", selected)
    assert changed.rebuilt == int(queried)
    assert changed.reused == int(not queried)
