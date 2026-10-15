"""Independent explicit-global regressions / 独立显式 global 写入回归。

Only developer-authored, fixed source fixtures are executed. CPython's compiler
symbol table and runtime are separate oracles; no upstream source runs and these
tests are not an unseen natural-source accuracy benchmark or a soundness proof.
仅运行自行编写的固定夹具；编译器与运行时作独立参照，不执行上游源码，
不将开发回归称为未见样本准确率实验或完整语义证明。
"""

import ast
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import symtable
from textwrap import indent

import pytest

from contextproof.dependencies import capture_witnesses, verify_witnesses
from contextproof.evidence import _seal as seal_bundle, make_bundle
from contextproof.graph import (RESOLVER_VERSION, _seal as seal_graph, build_graph,
                                canonical_graph_bytes, compare_graphs, validate_graph)
from contextproof.index import build_index, source_lines
from contextproof.reuse import GraphSession


@dataclass(frozen=True)
class Fixture:
    name: str
    body: str
    possible_global_write: bool
    runtime_changes: bool


# The first29 cases retain the independently specified development matrix.
# 前29例保持事前指定的开发矩阵；后三例扩大只读/推导式负控制。
FIXTURES = (
    Fixture("assign", "global x\nx = 2", True, True),
    Fixture("destructure", "global x\nx, y = 2, 3", True, True),
    Fixture("multi-assign", "global x\nx = y = 2", True, True),
    Fixture("augassign", "global x\nx += 2", True, True),
    Fixture("delete", "global x\ndel x", True, True),
    Fixture("import", "global x\nimport math as x", True, True),
    Fixture("from-import", "global x\nfrom math import pi as x", True, True),
    Fixture("function-definition", "global x\ndef x():\n    return 2", True, True),
    Fixture("async-definition", "global x\nasync def x():\n    return 2", True, True),
    Fixture("class-definition", "global x\nclass x:\n    pass", True, True),
    Fixture("namedexpr", "global x\ny = (x := 2)", True, True),
    Fixture("for-target", "global x\nfor x in (2,):\n    pass", True, True),
    Fixture("with-target", "global x\nfrom contextlib import nullcontext\n"
            "with nullcontext(2) as x:\n    pass", True, True),
    Fixture("except-target", "global x\ntry:\n    raise ValueError()\n"
            "except ValueError as x:\n    pass", True, True),
    Fixture("match-capture", "global x\nmatch 2:\n    case x:\n        pass", True, True),
    Fixture("unreachable-conditional", "global x\nif False:\n    x = 2", True, False),
    Fixture("nested-function-default", "global x\ndef inner(value=(x := 2)):\n    pass",
            True, True),
    Fixture("lambda-default", "global x\ny = lambda value=(x := 2): value", True, True),
    Fixture("nested-class-global", "class Inner:\n    global x\n    x = 2", True, True),
    Fixture("comprehension-namedexpr", "global x\ny = [(x := item) for item in (2,)]",
            True, True),
    Fixture("global-declaration-only", "global x\npass", False, False),
    Fixture("global-read-only", "global x\ny = x", False, False),
    Fixture("different-global", "global y\ny = 2\nx = 2", False, False),
    Fixture("local-assignment", "x = 2", False, False),
    Fixture("nested-class-local", "global x\nclass Inner:\n    x = 2", False, False),
    Fixture("comprehension-iteration-target", "global x\ny = [x for x in (2,)]", False, False),
    Fixture("nested-function-local", "global x\ndef inner():\n    x = 2\ninner()",
            False, False),
    Fixture("nested-function-parameter", "global x\ndef inner(x=2):\n    return x\ninner()",
            False, False),
    Fixture("lambda-parameter", "global x\ny = lambda x=2: x\ny()", False, False),
    Fixture("nested-function-readonly-global", "def inner():\n    global x\n    return x\ninner()",
            False, False),
    Fixture("nested-class-readonly-global", "class Inner:\n    global x\n    y = x",
            False, False),
    Fixture("dict-comprehension-iteration-target", "global x\ny = {x: x for x in (2,)}",
            False, False),
)
ALL_MODES = tuple(sorted(GraphSession.MODES))
BASE = "x = 0\ndef getter():\n    return x\ndef writer():\n    pass\n"


def fixture_source(case):
    return "x = 0\ndef getter():\n    return x\ndef writer():\n" + indent(case.body, "    ") + "\n"


def sha(source):
    return hashlib.sha256(source.encode()).hexdigest()


def selected(source):
    # Compile validates syntax that ast.parse alone may accept. The selected
    # identity/span is extracted independently of the dependency resolver.
    # 编译器验证语法；片段身份独立于被测依赖解析器提取。
    compile(source, "app.py", "exec")
    node = next(item for item in ast.parse(source).body
                if isinstance(item, ast.FunctionDef) and item.name == "getter")
    text = "".join(source_lines(source)[node.lineno - 1:node.end_lineno])
    return {"id": "fixed-getter", "path": "app.py", "symbol": "getter", "kind": "function",
            "start_line": node.lineno, "end_line": node.end_lineno, "text": text,
            "text_sha256": sha(text), "file_sha256": sha(source)}


def graph(source, anchor=None, snapshot="fixture"):
    return build_graph({"app.py": source}, snapshot, [anchor or selected(source)])


def expression_edge(built):
    return next(edge for edge in built["edges"].values()
                if edge["expression"] == "x" and edge["operation"] == "read")


def assert_binding_state(built, possible_write):
    validate_graph(built)
    edge = expression_edge(built)
    if possible_write:
        assert edge["status"] == "unresolved", edge
        assert edge["target"] is None and not edge["bindings"]
        assert built["frontier"]
        assert not any(node["symbol"] == "x" for node in built["nodes"].values())
        assert not compare_graphs(built, built)["fresh"]
    else:
        assert edge["status"] == "resolved", edge
        assert built["nodes"][edge["target"]]["kind"] == "constant"
        assert not built["frontier"]
        assert compare_graphs(built, built)["fresh"]


def compiler_write_sites(source):
    """CPython flags, not the candidate collector / 使用编译器而非被测收集器。"""
    root = symtable.symtable(source, "own_fixture.py", "exec")
    sites = []
    pending = list(root.get_children())
    while pending:
        table = pending.pop()
        if table.get_type() in {"class", "function"} and "x" in table.get_identifiers():
            symbol = table.lookup("x")
            if symbol.is_declared_global() and (symbol.is_assigned() or symbol.is_imported()):
                sites.append((table.get_name(), table.get_lineno()))
        pending.extend(table.get_children())
    return sites


def runtime_state(namespace):
    try:
        value = namespace["getter"]()
    except NameError:
        return "NameError", None
    return type(value).__name__, value if type(value) in {int, float, bool, str} else None


def runtime_result(source):
    namespace = {}
    # Only fixed developer-authored strings reach exec. Standard-library math
    # and nullcontext are trusted fixture helpers; upstream source never runs.
    # 仅执行固定自编字符串；math/nullcontext 为标准库夹具辅助，不执行上游源码。
    exec(compile(source, "own_fixture.py", "exec"), namespace)
    before = runtime_state(namespace)
    namespace["writer"]()
    return before, runtime_state(namespace)


def direct_bundle(tmp_path, source):
    (tmp_path / "app.py").write_text(source, encoding="utf-8")
    bundle = make_bundle(build_index(tmp_path), "getter", budget=1000000, method="bm25")
    bundle["entries"] = [entry for entry in bundle["entries"]
                         if entry["path"] == "app.py" and entry["symbol"] == "getter"]
    assert len(bundle["entries"]) == 1
    return seal_bundle(bundle)


def test_development_matrix_denominators_are_explicit():
    assert len(FIXTURES) == 32
    assert sum(case.possible_global_write for case in FIXTURES) == 20
    assert sum(case.runtime_changes for case in FIXTURES) == 19
    assert len(ALL_MODES) == 10


@pytest.mark.parametrize("case", FIXTURES, ids=lambda case: case.name)
def test_compiler_and_runtime_independently_confirm_fixed_case_labels(case):
    source = fixture_source(case)
    assert bool(compiler_write_sites(source)) is case.possible_global_write
    before, after = runtime_result(source)
    assert before == ("int", 0)
    assert (before != after) is case.runtime_changes


@pytest.mark.parametrize("case", FIXTURES, ids=lambda case: case.name)
def test_graph_does_not_confuse_possible_global_write_with_fixed_literal(case):
    assert_binding_state(graph(fixture_source(case)), case.possible_global_write)


@pytest.mark.parametrize("case", FIXTURES, ids=lambda case: case.name)
def test_direct_witness_capture_and_verification_preserve_binding_uncertainty(tmp_path, case):
    source = fixture_source(case)
    witness = capture_witnesses(direct_bundle(tmp_path, source), tmp_path)
    reference = next(ref for ref in witness["entries"][0]["references"]
                     if ref["expression"] == "x")
    assert reference["status"] == ("unresolved" if case.possible_global_write else "resolved")
    report = verify_witnesses(witness, tmp_path)
    assert report["fresh"] is not case.possible_global_write
    assert report["status"] == ("unresolved" if case.possible_global_write else "unchanged")


@pytest.mark.parametrize("case", FIXTURES, ids=lambda case: case.name)
def test_old_direct_witness_rechecks_writer_only_change(tmp_path, case):
    witness = capture_witnesses(direct_bundle(tmp_path, BASE), tmp_path)
    assert verify_witnesses(witness, tmp_path)["fresh"]
    changed = fixture_source(case)
    assert selected(changed)["text"] == selected(BASE)["text"]
    (tmp_path / "app.py").write_text(changed, encoding="utf-8")
    report = verify_witnesses(witness, tmp_path)
    assert report["fresh"] is not case.possible_global_write
    assert report["status"] == ("unresolved" if case.possible_global_write else "unchanged")


@pytest.mark.parametrize("mode", ALL_MODES)
@pytest.mark.parametrize("case", FIXTURES, ids=lambda case: case.name)
def test_every_session_mode_rebuilds_writer_only_change_and_retains_unknown(mode, case):
    anchor = selected(BASE)
    session = GraphSession([anchor], mode=mode)
    initial = session.update({"app.py": BASE}, "before-writer")
    assert initial.rebuilt == 1 and initial.reused == 0
    assert_binding_state(initial.graphs[0], False)
    source = fixture_source(case)
    result = session.update({"app.py": source}, "writer-added")
    assert result.rebuilt == 1 and result.reused == 0
    assert canonical_graph_bytes(result.graphs[0]) == canonical_graph_bytes(
        graph(source, anchor, "writer-added"))
    assert_binding_state(result.graphs[0], case.possible_global_write)
    stable = session.update({"app.py": source}, "same-source-new-identity")
    assert canonical_graph_bytes(stable.graphs[0]) == canonical_graph_bytes(
        graph(source, anchor, "same-source-new-identity"))
    assert_binding_state(stable.graphs[0], case.possible_global_write)
    must_rebuild = mode in {"warm_ast_rebuild", "incremental_index_rebuild"} or (
        mode == "read_set_certificate" and case.possible_global_write)
    assert stable.rebuilt == int(must_rebuild)
    assert stable.reused == int(not must_rebuild)
    restored = session.update({"app.py": BASE}, "writer-removed")
    assert restored.rebuilt == 1 and restored.reused == 0
    assert_binding_state(restored.graphs[0], False)


def test_setter_only_revision_changes_runtime_and_never_becomes_fresh():
    source = fixture_source(FIXTURES[0])
    revised = source.replace("    x = 2\n", "    x = 3\n")
    assert runtime_result(source)[1] == ("int", 2)
    assert runtime_result(revised)[1] == ("int", 3)
    anchor = selected(source)
    assert selected(revised)["text"] == anchor["text"]
    before, after = graph(source, anchor, "old"), graph(revised, anchor, "new")
    assert_binding_state(before, True)
    assert_binding_state(after, True)
    report = compare_graphs(before, after)
    assert not report["fresh"] and report["status"] == "unresolved"


@pytest.mark.parametrize("old_version", [1, 2, 3])
def test_pre_function_global_guard_artifacts_require_recapture(old_version):
    current = graph(BASE)
    assert RESOLVER_VERSION == 4
    previous = deepcopy(current)
    previous["policy"]["resolver_version"] = old_version
    seal_graph(previous)
    with pytest.raises(ValueError, match="recapture"):
        validate_graph(previous)
    with pytest.raises(ValueError, match="different graph resolver versions"):
        compare_graphs(previous, current)
    with pytest.raises(ValueError, match="recapture"):
        compare_graphs(previous, previous)


@pytest.mark.parametrize("body", ["global x\nx: int = 2", "global x\nx: int"])
def test_invalid_global_annotation_is_rejected_by_compiler_not_labeled_valid_writer(body):
    source = "x = 0\ndef writer():\n" + indent(body, "    ") + "\n"
    # ast.parse can construct this tree, but the compiler forbids the binding.
    # AST 可构造并不代表 Python 程序有效；编译器拒绝此名字注解。
    ast.parse(source)
    with pytest.raises(SyntaxError):
        compile(source, "own_invalid_fixture.py", "exec")
    with pytest.raises(SyntaxError):
        symtable.symtable(source, "own_invalid_fixture.py", "exec")


@pytest.mark.parametrize("class_name,read_name,should_guard", [
    ("C", "_C__x", True),
    ("C", "__x", False),
    ("__C", "_C__x", True),
    ("___", "__x", True),
])
def test_private_global_names_follow_compiler_mangling_not_raw_ast(class_name, read_name, should_guard):
    source = (f"{read_name} = 0\ndef getter():\n    return {read_name}\n"
              f"class {class_name}:\n    def writer(self):\n        global __x\n        __x = 2\n")
    namespace = {}
    exec(compile(source, "own_mangled_fixture.py", "exec"), namespace)
    assert namespace["getter"]() == 0
    namespace[class_name]().writer()
    assert namespace["getter"]() == (2 if should_guard else 0)
    tables = symtable.symtable(source, "own_mangled_fixture.py", "exec").get_children()
    class_table = next(table for table in tables if table.get_type() == "class")
    method = next(table for table in class_table.get_children() if table.get_name() == "writer")
    assert any(symbol.get_name() == read_name and symbol.is_declared_global()
               and symbol.is_assigned() for symbol in method.get_symbols()) is should_guard
    built = graph(source)
    edge = next(edge for edge in built["edges"].values() if edge["expression"] == read_name)
    assert edge["status"] == ("unresolved" if should_guard else "resolved"), edge
    assert bool(built["frontier"]) is should_guard


def test_nested_class_uses_nearest_private_name_context():
    source = ("_Inner__x = 0\ndef getter():\n    return _Inner__x\n"
              "class Outer:\n    class Inner:\n        def writer(self):\n"
              "            global __x\n            __x = 2\n")
    namespace = {}
    exec(compile(source, "own_nested_mangled_fixture.py", "exec"), namespace)
    namespace["Outer"].Inner().writer()
    assert namespace["getter"]() == 2
    built = graph(source)
    edge = next(edge for edge in built["edges"].values() if edge["expression"] == "_Inner__x")
    assert edge["status"] == "unresolved" and edge["target"] is None
    assert not compare_graphs(built, built)["fresh"]


def test_nested_function_in_method_keeps_class_private_name_context():
    source = ("_C__x = 0\ndef getter():\n    return _C__x\n"
              "class C:\n    def writer(self):\n        def inner():\n"
              "            global __x\n            __x = 2\n        inner()\n")
    namespace = {}
    exec(compile(source, "own_nested_method_fixture.py", "exec"), namespace)
    namespace["C"]().writer()
    assert namespace["getter"]() == 2
    edge = next(edge for edge in graph(source)["edges"].values() if edge["expression"] == "_C__x")
    assert edge["status"] == "unresolved" and edge["target"] is None


def test_trailing_dunder_global_is_not_private_name_mangled():
    source = ("__x__ = 0\ndef getter():\n    return __x__\n"
              "class C:\n    def writer(self):\n        global __x__\n        __x__ = 2\n")
    namespace = {}
    exec(compile(source, "own_dunder_fixture.py", "exec"), namespace)
    namespace["C"]().writer()
    assert namespace["getter"]() == 2
    edge = next(edge for edge in graph(source)["edges"].values() if edge["expression"] == "__x__")
    assert edge["status"] == "unresolved" and edge["target"] is None
