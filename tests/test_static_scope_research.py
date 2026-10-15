"""Independent class-global binding regressions, not a semantic accuracy benchmark."""

import ast
from copy import deepcopy
import hashlib
import json
from textwrap import dedent, indent

import pytest

from contextproof.dependencies import capture_witnesses, verify_witnesses
from contextproof.evidence import _seal, make_bundle
from contextproof.graph import (RESOLVER_VERSION, _seal as seal_graph, build_graph,
                                compare_graphs, validate_graph)
from contextproof.index import build_index


def build(source, selected=None):
    """Extract the fixed entry declaration independently of dependency resolution."""
    # Check fixture syntax through the compiler, not just ast.parse's weaker gate.
    # 用编译器验证测试输入语法；标签不由依赖解析器生成。
    compile(source, "app.py", "exec")
    if selected is None:
        owner = next(n for n in ast.parse(source).body
                     if isinstance(n, ast.FunctionDef) and n.name == "entry")
        text = "".join(source.splitlines(keepends=True)[owner.lineno - 1:owner.end_lineno])
        selected = {"id": "selected-entry", "path": "app.py", "symbol": "entry",
                    "kind": "function", "start_line": owner.lineno, "end_line": owner.end_lineno,
                    "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest()}
    graph = build_graph({"app.py": source}, hashlib.sha256(source.encode()).hexdigest(), [selected])
    return graph, selected


def test_class_global_definition_cannot_be_false_fresh():
    source = ("def helper():\n    return 1\n"
              "class Binder:\n    global helper\n    def helper():\n        return 2\n"
              "def entry():\n    return helper()\n")
    before, selected = build(source)
    after, _ = build(source.replace("return 2", "return 3"), selected)
    report = compare_graphs(before, after)
    assert not report["fresh"], json.dumps(report)
    assert report["status"] == "unresolved"


@pytest.mark.parametrize("body", [
    "global helper\nhelper = 2",
    "global helper\nhelper, other = 2, 3",
    "global helper\nhelper += 2",
    "global helper\ndel helper",
    "global helper\nimport math as helper",
    "global helper\nfrom math import sqrt as helper",
    "global helper\ndef helper():\n    return 2",
    "global helper\nasync def helper():\n    return 2",
    "global helper\nclass helper:\n    pass",
    "global helper\nvalue = (helper := 2)",
    "global helper\nfor helper in (2,):\n    pass",
    "global helper\nwith open('unused') as helper:\n    pass",
    "global helper\ntry:\n    pass\nexcept Exception as helper:\n    pass",
    "global helper\nmatch 2:\n    case helper:\n        pass",
    "global helper\nif False:\n    helper = 2",
    "global helper\ndef method(value=(helper := 2)):\n    pass",
    "global helper\nvalue = lambda arg=(helper := 2): arg",
    "global helper\nclass Nested((helper := object)):\n    pass",
    "class Nested:\n    global helper\n    helper = 2",
    "class Nested:\n    global helper\n    import math as helper",
    "class Nested:\n    global helper\n    del helper",
    "def method():\n    global helper\n    helper = 2",
    "def method():\n    class Nested:\n        global helper\n        helper = 2",
], ids=["assign", "unpack", "augassign", "delete", "import", "from-import",
        "def", "async-def", "class", "walrus", "for-target", "with-target",
        "except-target", "pattern", "unexecuted-branch", "method-default",
        "lambda-default", "nested-class-base", "nested-assign", "nested-import",
        "nested-delete", "deferred-method", "deferred-nested-class"])
def test_explicit_class_global_write_is_unknown(body):
    source = "helper = 1\nclass Binder:\n" + indent(body, "    ")
    source += "\ndef entry():\n    return helper\n"
    graph, _ = build(source)
    report = compare_graphs(graph, graph)
    assert not report["fresh"]
    assert report["status"] == "unresolved"
    assert graph["frontier"]
    assert any(edge["expression"] == "helper" and edge["status"] == "unresolved"
               and edge["target"] is None for edge in graph["edges"].values())
    assert not any(node["symbol"] == "helper" for node in graph["nodes"].values())


@pytest.mark.parametrize("body", [
    "helper = 2",
    "import math as helper",
    "from math import sqrt as helper",
    "def helper():\n    return 2",
    "global helper\npass",
    "global other\nother = 2\nhelper = 2",
    "global helper\nclass Nested:\n    helper = 2",
    "global helper\nclass Nested:\n    import math as helper",
    "global helper\nclass Nested:\n    helper = 2\n    del helper",
    "global helper\nvalues = [helper for helper in (2, 3)]",
    "global helper\nvalues = {helper: helper for helper in (2, 3)}",
    "global helper\ndef method(helper=2):\n    return helper",
    "global helper\nmethod = lambda helper=2: helper",
], ids=["local-assign", "local-import", "local-from-import", "local-def",
        "declaration-only", "unrelated-global", "nested-local-assign",
        "nested-local-import", "nested-local-delete", "list-target", "dict-target",
        "method-parameter", "lambda-parameter"])
def test_unrelated_or_separate_lexical_scope_does_not_poison_global(body):
    source = "helper = 1\nclass Binder:\n" + indent(body, "    ")
    source += "\ndef entry():\n    return helper\n"
    graph, selected = build(source)
    changed, _ = build(source.replace("2", "4"), selected)
    # This proves only the explicit source-binding contract, not runtime safety.
    # 此断言仅验证显式源码绑定契约，不表示一般运行时安全。
    report = compare_graphs(graph, changed)
    assert report["fresh"], report
    assert not graph["frontier"]


def test_nested_class_global_does_not_require_outer_global():
    source = dedent("""\
        def helper():
            return 1
        class Outer:
            helper = 10
            class Inner:
                global helper
                def helper():
                    return 2
        def entry():
            return helper()
    """)
    before, selected = build(source)
    after, _ = build(source.replace("return 2", "return 3"), selected)
    assert compare_graphs(before, after)["status"] == "unresolved"


@pytest.mark.parametrize("old_version", [1, 2, 3])
def test_pre_class_global_guard_graphs_require_recapture(old_version):
    current, _ = build("def entry():\n    return 1\n")
    assert current["policy"]["resolver_version"] == RESOLVER_VERSION == 4
    previous = deepcopy(current)
    previous["policy"]["resolver_version"] = old_version
    seal_graph(previous)
    with pytest.raises(ValueError, match="recapture"):
        validate_graph(previous)
    with pytest.raises(ValueError, match="different graph resolver versions"):
        compare_graphs(previous, current)
    with pytest.raises(ValueError, match="recapture"):
        compare_graphs(previous, previous)


def test_schema_one_direct_witness_rechecks_current_class_bindings(tmp_path):
    source = "def helper():\n    return 1\nclass Binder:\n    pass\n"
    source += "def entry():\n    return helper()\n"
    file = tmp_path / "app.py"
    file.write_text(source, encoding="utf-8")
    bundle = make_bundle(build_index(tmp_path), "entry", budget=1000000, method="bm25")
    bundle["entries"] = [item for item in bundle["entries"] if item["symbol"] == "entry"]
    _seal(bundle)
    witness = capture_witnesses(bundle, tmp_path)
    assert witness["schema_version"] == 1
    assert verify_witnesses(witness, tmp_path)["fresh"]
    file.write_text(source.replace("    pass\n", "    global helper\n    del helper\n"),
                    encoding="utf-8")
    report = verify_witnesses(witness, tmp_path)
    assert not report["fresh"]
    assert report["status"] == "unresolved"
