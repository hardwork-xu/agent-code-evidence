"""Byte-equivalence checks against fresh graph construction on authored fixtures.

This tests incremental replay, not the resolver's semantic completeness.
验证增量回放等于重新构图，不将该等价关系当作解析器的语义完备性证明。
"""

from dataclasses import replace

import pytest

from benchmarks.selective_reuse.oracle_cases import anchor, cases
from contextproof.graph import build_graph, canonical_graph_bytes
from contextproof.reuse import GraphSession


CASES = cases()
MODES = sorted(GraphSession.MODES)


def assert_fresh_equivalent(session, texts, snapshot, anchors):
    replay = session.update(texts, snapshot)
    expected = [build_graph(texts, snapshot, [selected], max_depth=8)
                for selected in anchors]
    assert [canonical_graph_bytes(graph) for graph in replay.graphs] == [
        canonical_graph_bytes(graph) for graph in expected
    ]
    assert replay.reused + replay.rebuilt == len(anchors)
    assert sum(replay.reasons.values()) == len(anchors)
    return replay


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_frozen_oracle_pair_all_modes_match_fresh_bytes(case, mode):
    selected = [anchor(case)]
    session = GraphSession(selected, mode=mode, max_depth=8)
    initial = assert_fresh_equivalent(session, case.before, "before", selected)
    assert initial.reused == 0
    assert initial.rebuilt == 1
    stable = assert_fresh_equivalent(session, case.before, "before-new-id", selected)
    changed = assert_fresh_equivalent(session, case.after, "after", selected)
    restored = assert_fresh_equivalent(session, case.before, "restored", selected)
    if mode == "warm_ast_rebuild":
        assert stable.reused == changed.reused == restored.reused == 0
    if mode == "whole_corpus_guard":
        assert stable.reused == 1
        assert changed.reused == 0  # Every fixture changes at least one source file.
    # A runtime-effect stress case may be fresh in both graphs. Byte equality is
    # not a claim that the source resolver covers that out-of-contract behavior.


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("init_after", [
    "sub = 9\n",
    "def __getattr__(name):\n    return 9\n",
    "from provider import *\n",
])
def test_existing_package_negative_lookup_changes_invalidate_replay(mode, init_after):
    before = {
        "app.py": "from package import sub\ndef entry():\n    return sub.compute()\n",
        "package/__init__.py": "",
        "package/sub.py": "def compute():\n    return 17\n",
        "provider.py": "sub = 9\n",
    }
    # Reuse only the independent AST span helper, without adding these stress
    # variants to the frozen 72-case semantic corpus or its denominators.
    fixture = replace(CASES[0], before=before)
    selected = [anchor(fixture)]
    session = GraphSession(selected, mode=mode, max_depth=8)
    assert_fresh_equivalent(session, before, "before", selected)
    after = before | {"package/__init__.py": init_after}
    replay = assert_fresh_equivalent(session, after, "after", selected)
    assert replay.rebuilt == 1


@pytest.mark.parametrize("mode", MODES)
def test_added_ambiguous_module_path_cannot_reuse_prior_catalog(mode):
    before = {"app.py": "from provider import compute\ndef entry():\n    return compute()\n",
              "provider.py": "def compute():\n    return 17\n"}
    selected = [anchor(replace(CASES[0], before=before))]
    session = GraphSession(selected, mode=mode, max_depth=8)
    assert_fresh_equivalent(session, before, "before", selected)
    after = before | {"src/provider.py": "def compute():\n    return 97\n"}
    replay = assert_fresh_equivalent(session, after, "after", selected)
    assert replay.rebuilt == 1
    assert replay.graphs[0]["frontier"]


@pytest.mark.parametrize("mode", MODES)
def test_multiple_anchors_and_returned_mutation_keep_independent_certificates(mode):
    before = {"a.py": "def entry():\n    return 1\n",
              "b.py": "def entry():\n    return 2\n"}
    selected = [anchor(replace(CASES[0], case_id=path, before=before, anchor_path=path))
                for path in sorted(before)]
    session = GraphSession(selected, mode=mode, max_depth=8)
    initial = assert_fresh_equivalent(session, before, "before", selected)
    # Caller mutation must not poison either internal saved graph.
    initial.graphs[0]["nodes"].clear()
    initial.graphs[1]["snapshot_id"] = "caller-mutated"
    after = before | {"a.py": "def entry():\n    return 3\n"}
    replay = assert_fresh_equivalent(session, after, "after", selected)
    if mode == "read_set_certificate":
        assert replay.reused == replay.rebuilt == 1
