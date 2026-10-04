"""Independent, authored adversarial fixtures for selective evidence reuse.

These are development/regression cases, not natural changes or a holdout.
这里是人工构造的开发/回归样例，不是自然变更样本或保留测试集。

Labels come from explicit fixture construction and Python semantics, never the
ContextProof resolver. Runtime observations validate only these finite programs.
They do not establish general semantic equivalence or a natural error rate.

``expected_decision`` is the research safety policy. ``contract_expected_decision``
is separately nullable: arbitrary call/exec effects are outside the existing
bounded source/import-binding contract, not automatically resolver defects.
研究目标与现有契约分开：运行时副作用压力例不能直接计作已有契约的错误。
"""

from __future__ import annotations

import ast
from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
from typing import Any, Literal


Decision = Literal["fresh", "changed", "unknown"]
ContractClass = Literal[
    "supported_static", "unsupported_static", "runtime_effect_out_of_scope"
]
CORPUS_VERSION = "authored-adversarial-v1"
SPLIT = "development_adversarial_regression"
PARAMETERS = (1, 7, 19)
LIMITATION = (
    "72 authored instances from 24 syntax templates in 6 families; numeric variants "
    "are correlated and are not 72 independent semantic mechanisms. No natural "
    "error-rate, generalization, model-task or holdout claim is supported."
)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()).hexdigest()


@dataclass(frozen=True)
class RuntimeOutcome:
    """A finite synthetic execution result / 有限合成执行的返回值或异常类型。"""

    kind: Literal["return", "raise"]
    value: int | None = None
    exception: str | None = None


@dataclass(frozen=True)
class OracleCase:
    """An independently labelled source pair / 不使用待测解析器标注的源码对。"""

    case_id: str
    family: str
    template: str
    parameter: int
    before: dict[str, str]
    after: dict[str, str]
    expected_decision: Decision
    contract_class: ContractClass
    contract_expected_decision: Decision | None
    before_outcome: RuntimeOutcome
    after_outcome: RuntimeOutcome
    rationale_en: str
    rationale_zh: str
    anchor_path: str = "app.py"
    anchor_symbol: str = "entry"
    split: str = SPLIT

    def to_dict(self) -> dict[str, Any]:
        """JSON-compatible public record / 可直接序列化的公开记录。"""
        return asdict(self)


def _case(family: str, template: str, n: int, before: dict[str, str],
          after: dict[str, str], decision: Decision, before_value: int,
          after_value: int | None, en: str, zh: str, *, runtime_effect: bool = False,
          after_exception: str | None = None) -> OracleCase:
    contract_class: ContractClass = (
        "runtime_effect_out_of_scope" if runtime_effect else
        "unsupported_static" if decision == "unknown" else "supported_static"
    )
    return OracleCase(
        case_id=f"{family}/{template}/n{n}", family=family, template=template,
        parameter=n, before=before, after=after, expected_decision=decision,
        contract_class=contract_class,
        contract_expected_decision=None if runtime_effect else decision,
        before_outcome=RuntimeOutcome("return", before_value),
        after_outcome=(RuntimeOutcome("raise", exception=after_exception)
                       if after_exception else RuntimeOutcome("return", after_value)),
        rationale_en=en, rationale_zh=zh,
    )


def cases() -> tuple[OracleCase, ...]:
    """Return fresh deterministic fixture objects / 返回确定且互不共享修改的样例。

    The numeric parameter changes only literal payloads; template/family are the
    meaningful aggregation units. 数值参数不是独立语法机制，应按模板/家族汇总。
    """
    rows: list[OracleCase] = []
    entry = "def entry():\n    return helper()\n"
    original = "def helper():\n    return 0\n"
    for n in PARAMETERS:
        changed = n + 101

        def pair(build):
            return build(n), build(changed)

        def add(family, template, sources, decision, values, en, zh, **kwargs):
            rows.append(_case(family, template, n, *sources, decision, *values,
                              en, zh, **kwargs))

        family = "top_level_rebind"
        add(family, "assignment", pair(lambda v: {
            "app.py": original + f"helper = lambda: {v}\n" + entry,
        }), "unknown", (n, changed),
            "A function declaration is overwritten by an assignment; do not certify its old binding.",
            "函数声明被赋值覆盖，不能认证旧绑定。")
        add(family, "augmented_assignment", pair(lambda v: {
            "app.py": f"VALUE = {v}\nVALUE += 2\ndef entry():\n    return VALUE\n",
        }), "unknown", (n + 2, changed + 2),
            "Augmented assignment is an additional module binding write, not a sole literal.",
            "增量赋值是额外模块写入，不能当成唯一字面量绑定。")
        add(family, "conditional_definition", pair(lambda v: {
            "app.py": original + f"if True:\n    def helper():\n        return {v}\n" + entry,
        }), "unknown", (n, changed),
            "A conditional declaration replaces a top-level function; static path uncertainty stays visible.",
            "条件内声明替换模块函数，静态路径不确定性应保留。")
        add(family, "delete_then_restore", pair(lambda v: {
            "app.py": original + f"del helper\nhelper = lambda: {v}\n" + entry,
        }), "unknown", (n, changed),
            "Deletion and a later assignment invalidate the sole-declaration binding assumption.",
            "删除后重新赋值不满足唯一声明绑定假设。")

        family = "class_global"
        add(family, "assignment", pair(lambda v: {
            "app.py": original + "class Configure:\n    global helper\n"
                      + f"    helper = lambda: {v}\n" + entry,
        }), "unknown", (n, changed),
            "Explicit class-body global assignment writes the module binding while defining the class.",
            "类体显式 global 赋值在类定义时写入模块绑定。")
        add(family, "import_alias", pair(lambda v: {
            "app.py": original + "class Configure:\n    global helper\n"
                      + "    from provider import compute as helper\n" + entry,
            "provider.py": f"def compute():\n    return {v}\n",
        }), "unknown", (n, changed),
            "A class-body global import alias replaces the module function with provider.compute.",
            "类体 global 导入别名用 provider.compute 替换模块函数。")
        add(family, "function_definition", pair(lambda v: {
            "app.py": original + "class Configure:\n    global helper\n"
                      + f"    def helper():\n        return {v}\n" + entry,
        }), "unknown", (n, changed),
            "A class-body function definition under global binds in module scope, not class scope.",
            "global 声明下的类体函数定义绑定到模块而非类命名空间。")
        old = {"app.py": f"def helper():\n    return {n}\n"
                         + "class Configure:\n    pass\n" + entry}
        new = {"app.py": f"def helper():\n    return {n}\n"
                         + "class Configure:\n    global helper\n    del helper\n" + entry}
        add(family, "delete", (old, new), "unknown", (n, None),
            "A class-body global deletion removes the referenced module binding; entry raises NameError.",
            "类体 global 删除移除被引用模块绑定，entry 随后抛出 NameError。",
            after_exception="NameError")

        family = "imports_aliases_shadowing"
        add(family, "from_alias", pair(lambda v: {
            "app.py": "from provider import compute as helper\n" + entry,
            "provider.py": f"def compute():\n    return {v}\n",
        }), "changed", (n, changed),
            "The uniquely imported function's source changes through a preserved from-import alias.",
            "from 导入别名保持不变，但其唯一目标函数源码改变。")
        add(family, "module_alias", pair(lambda v: {
            "app.py": "import provider as policy\ndef entry():\n    return policy.compute()\n",
            "provider.py": f"def compute():\n    return {v}\n",
        }), "changed", (n, changed),
            "A uniquely resolvable module alias points to a changed direct function definition.",
            "唯一可解析的模块别名指向已修改的直接函数定义。")
        providers = {name: f"def compute():\n    return {n}\n" for name in ("one.py", "two.py")}
        add(family, "equal_behavior_retarget", (
            providers | {"app.py": "from one import compute as helper\n" + entry},
            providers | {"app.py": "from two import compute as helper\n" + entry},
        ), "changed", (n, n),
            "Identical return values do not preserve source/import identity when an alias is retargeted.",
            "别名切换来源后，即使返回值相同也不保持源码与导入绑定身份。")
        add(family, "function_local_shadow", pair(lambda v: {
            "app.py": original + "def entry():\n    from provider import compute as helper\n"
                      + "    return helper()\n",
            "provider.py": f"def compute():\n    return {v}\n",
        }), "unknown", (n, changed),
            "A function-local import shadows the same-named module function and needs lexical resolution.",
            "函数局部导入遮蔽同名模块函数，需保留词法解析不确定性。")

        family = "decorator_defaults"
        add(family, "decorator_side_effect", pair(lambda v: {
            "app.py": original + "def install(fn):\n    global helper\n"
                      + f"    helper = lambda: {v}\n    return fn\n"
                      + "@install\ndef unrelated():\n    return 0\n" + entry,
        }), "unknown", (n, changed),
            "Executing a decorator on another declaration mutates a global. This is a runtime-effect "
            "stress case, outside the current source/import-identity guarantee.",
            "其他声明的装饰器执行会改写全局；这是当前源码/导入身份保证之外的运行时副作用压力例。",
            runtime_effect=True)
        add(family, "default_call_side_effect", pair(lambda v: {
            "app.py": original + "def install():\n    global helper\n"
                      + f"    helper = lambda: {v}\n    return 0\n"
                      + "def unrelated(value=install()):\n    return value\n" + entry,
        }), "unknown", (n, changed),
            "A default-expression call executes while defining another function and mutates helper; "
            "arbitrary call effects are outside the existing static guarantee.",
            "另一函数默认值中的调用在定义时改写 helper；任意调用副作用超出现有静态保证。",
            runtime_effect=True)
        add(family, "literal_default_dependency", pair(lambda v: {
            "app.py": "from policy import VALUE\ndef entry(value=VALUE):\n    return value\n",
            "policy.py": f"VALUE = {v}\n",
        }), "changed", (n, changed),
            "A default argument reads an imported literal outside parameter-local scope.",
            "默认参数在参数局部作用域之外读取导入字面量。")
        old = {"app.py": "def identity(fn):\n    return fn\n@identity\n"
                         + f"def entry():\n    return {n}\n"}
        new = {"app.py": old["app.py"].replace("    return fn\n", "    # revised witness\n    return fn\n")}
        add(family, "decorator_source_identity", (old, new), "changed", (n, n),
            "The direct decorator source changes even though this finite program returns the same value.",
            "直接装饰器源码改变，即使本例有限执行返回值相同也应刷新源码证据。")

        family = "dynamic_wildcards"
        add(family, "wildcard_import", pair(lambda v: {
            "app.py": "from provider import *\n" + entry,
            "provider.py": f"def helper():\n    return {v}\n",
        }), "unknown", (n, changed),
            "Wildcard imports have unbounded/shadowable bindings in the declared static contract.",
            "通配符导入在所声明的静态契约中具有无界或可被遮蔽的绑定。")
        add(family, "globals_lookup", pair(lambda v: {
            "app.py": f"def helper():\n    return {v}\n"
                      + "def entry():\n    return globals()['helper']()\n",
        }), "unknown", (n, changed),
            "String-indexed globals lookup is explicit dynamic dispatch, not a direct name witness.",
            "按字符串查询 globals 属于显式动态分派，不是直接名称证据。")
        add(family, "getattr_dispatch", pair(lambda v: {
            "app.py": "import provider\ndef entry():\n    return getattr(provider, 'helper')()\n",
            "provider.py": f"def helper():\n    return {v}\n",
        }), "unknown", (n, changed),
            "getattr call dispatch is outside direct static attribute resolution.",
            "getattr 调用分派超出直接静态属性解析。")
        add(family, "exec_rebind", pair(lambda v: {
            "app.py": original + "exec({!r})\n".format(f"def helper():\n    return {v}\n") + entry,
        }), "unknown", (n, changed),
            "Module exec replaces helper. Inferring its runtime effects is outside the current "
            "source/import guarantee; this is a separate safety-policy stress case.",
            "模块 exec 替换 helper；运行时效果推断超出现有源码/导入保证，单独作为安全策略压力例。",
            runtime_effect=True)

        family = "unrelated_edits"
        add(family, "same_file_function", pair(lambda v: {
            "app.py": f"def unrelated():\n    return {v}\ndef entry():\n    return 41\n",
        }), "fresh", (41, 41),
            "Only an uncalled, unreferenced function body changes; the selected static closure is identical.",
            "仅修改未调用未引用函数体，所选静态闭包不变。")
        add(family, "other_file", pair(lambda v: {
            "app.py": "def entry():\n    return 41\n",
            "unused.py": f"def unrelated():\n    return {v}\n",
        }), "fresh", (41, 41),
            "An unimported file changes while the selected function and all its bindings remain identical.",
            "未导入文件改变，所选函数及其绑定均不变。")
        old = {"app.py": f"def entry():\n    return {n}\n"}
        add(family, "line_movement", (old, {"app.py": "# inserted comment\n\n" + old["app.py"]}),
            "fresh", (n, n),
            "Comment insertion moves source lines without changing the uniquely selected declaration.",
            "插入注释只移动行号，不改变唯一所选声明。")
        add(family, "unrelated_global_shadowed", pair(lambda v: {
            "app.py": f"helper = {v}\ndef entry():\n    helper = 41\n    return helper\n",
        }), "fresh", (41, 41),
            "A local literal shadows an unused global; changing the global does not change the static closure.",
            "局部字面量遮蔽未使用全局，修改全局不改变所选静态闭包。")
    return tuple(rows)


def anchor(case: OracleCase) -> dict[str, Any]:
    """Capture the full old declaration using only stdlib AST / 仅用标准库定位旧声明。

    No ContextProof corpus, resolver or graph is called to choose spans or labels.
    不调用 ContextProof 的 corpus、resolver 或 graph 选择源码范围或预期。
    """
    text = case.before[case.anchor_path]
    owners = [node for node in ast.parse(text).body
              if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
              and node.name == case.anchor_symbol]
    if len(owners) != 1:
        raise ValueError("fixture must have one top-level entry function")
    node = owners[0]
    start = min([node.lineno, *(item.lineno for item in node.decorator_list)])
    end = node.end_lineno
    if end is None:
        raise ValueError("AST has no end location")
    selected = "".join(text.splitlines(keepends=True)[start - 1:end])
    return {"id": case.case_id, "path": case.anchor_path, "symbol": case.anchor_symbol,
            "kind": "function", "start_line": start, "end_line": end, "text": selected,
            "text_sha256": hashlib.sha256(selected.encode()).hexdigest(),
            "file_sha256": hashlib.sha256(text.encode()).hexdigest()}


def corpus_manifest() -> dict[str, Any]:
    """Describe fixed corpus composition / 描述固定样例构成，不生成模型结论。"""
    rows = cases()
    return {"version": CORPUS_VERSION, "split": SPLIT, "limitation": LIMITATION,
            "count": len(rows), "template_count": len({(c.family, c.template) for c in rows}),
            "family_counts": dict(sorted(Counter(c.family for c in rows).items())),
            "decision_counts": dict(sorted(Counter(c.expected_decision for c in rows).items())),
            "contract_class_counts": dict(sorted(Counter(c.contract_class for c in rows).items())),
            "sha256": _digest([row.to_dict() for row in rows])}


def execute_fixture(case: OracleCase, version: Literal["before", "after"]) -> RuntimeOutcome:
    """Execute only an unmodified built-in fixture in an isolated interpreter.

    This is not a sandbox for third-party code. Membership checking restricts the
    API to these authored small programs. No repository-under-study code executes.
    仅执行本文件内未修改的合成样例；这不是第三方代码沙箱，不运行待研究仓库代码。
    """
    canonical = {row.case_id: row for row in cases()}
    if case.case_id not in canonical or case.to_dict() != canonical[case.case_id].to_dict():
        raise ValueError("execution is restricted to unmodified authored fixtures")
    if version not in {"before", "after"}:
        raise ValueError("version must be before or after")
    sources = case.before if version == "before" else case.after
    with tempfile.TemporaryDirectory(prefix="contextproof-authored-oracle-") as directory:
        root = Path(directory)
        for relative, text in sources.items():
            path = PurePosixPath(relative)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("fixture path must be relative and non-traversing")
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        script = (
            "import sys, json\n"
            f"sys.path.insert(0, {str(root)!r})\n"
            "try:\n"
            "    import app\n"
            "    value = app.entry()\n"
            "except Exception as exc:\n"
            "    output = {'kind': 'raise', 'value': None, 'exception': type(exc).__name__}\n"
            "else:\n"
            "    output = {'kind': 'return', 'value': value, 'exception': None}\n"
            "print(json.dumps(output, sort_keys=True))\n"
        )
        completed = subprocess.run([sys.executable, "-I", "-c", script], cwd=root,
                                   check=True, capture_output=True, text=True, timeout=10)
        return RuntimeOutcome(**json.loads(completed.stdout))
