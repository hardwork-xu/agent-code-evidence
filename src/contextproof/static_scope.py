"""Conservative scope guards shared by direct and transitive witnesses.

Unsupported syntax remains visible instead of resolving an expression through a
same-named but different lexical/module binding. No repository code is executed.
"""

import ast
from typing import Any

_DECLARATIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _stored_names(node: ast.AST) -> set[str]:
    return {item.id for item in ast.walk(node)
            if isinstance(item, ast.Name) and isinstance(item.ctx, (ast.Store, ast.Del))}


def module_lookup_uncertainty(corpus, module: str, attrs: list[str]) -> str | None:
    candidates = corpus.module_candidates(module)
    if attrs and len(candidates) == 1:
        path = candidates[0]
        if path in corpus.wildcards:
            return "package wildcard may supply or shadow the requested attribute"
        bindings = corpus.bindings.get(path, {})
        if attrs[0] not in bindings and "__getattr__" in bindings:
            return "module __getattr__ may supply the requested attribute before submodule fallback"
    return None


def pattern_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, (ast.MatchAs, ast.MatchStar)) and child.name:
            names.add(child.name)
        elif isinstance(child, ast.MatchMapping) and child.rest:
            names.add(child.rest)
        for parameter in getattr(child, "type_params", []):
            if isinstance(getattr(parameter, "name", None), str):
                names.add(parameter.name)
    return names


def _definition_expressions(node: ast.AST) -> list[ast.AST]:
    """Expressions in the enclosing scope; 外层作用域中的定义时表达式。"""
    if isinstance(node, ast.ClassDef):
        return [*node.bases, *node.decorator_list, *(item.value for item in node.keywords)]
    expressions = [item for item in [*node.args.defaults, *node.args.kw_defaults]
                   if item is not None]
    for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs,
                *([node.args.vararg] if node.args.vararg else []),
                *([node.args.kwarg] if node.args.kwarg else [])]:
        if arg.annotation is not None:
            expressions.append(arg.annotation)
    if not isinstance(node, ast.Lambda):
        expressions.extend(node.decorator_list)
        if node.returns is not None:
            expressions.append(node.returns)
    return expressions


def _class_global_writes(owner: ast.ClassDef) -> list[tuple[str, ast.AST]]:
    """Find explicit class-suite writes to declared module globals.

    Class bodies execute when defined, but each nested class has its own global
    declarations. Function/lambda bodies and comprehension targets belong to
    other scopes. Only writes paired with a global declaration in the same
    class scope are returned; no branch or runtime call is evaluated.

    类体在定义时执行；嵌套类的 global 声明独立。函数体及推导式目标不属于
    外层类作用域。仅保留同一类作用域中显式声明为 global 的写入，不求值分支
    或调用，也不声称覆盖任意 Python 运行时副作用。
    """
    result: list[tuple[str, ast.AST]] = []
    classes = [owner]
    while classes:
        pending = list(classes.pop().body)
        globals_: set[str] = set()
        writes: list[tuple[str, ast.AST]] = []
        while pending:
            node = pending.pop()
            names: set[str] = set()
            if isinstance(node, ast.Global):
                globals_.update(node.names)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                names.add(node.id)
            elif isinstance(node, _DECLARATIONS):
                names.add(node.name)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                names.add(node.name)
            elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
                names.add(node.name)
            elif isinstance(node, ast.MatchMapping) and node.rest:
                names.add(node.rest)
            writes.extend((name, node) for name in sorted(names))
            if isinstance(node, ast.ClassDef):
                classes.append(node)
            if isinstance(node, (*_DECLARATIONS, ast.Lambda)):
                pending.extend(_definition_expressions(node))
            elif isinstance(node, ast.comprehension):
                # The iteration target is local to the comprehension.
                # 推导式循环目标不会重绑定外层类声明的 global。
                pending.extend([node.iter, *node.ifs])
            else:
                pending.extend(ast.iter_child_nodes(node))
        result.extend((name, node) for name, node in writes if name in globals_)
    return result


def guard_module_bindings(corpus: Any, paths=None) -> None:
    """Retain source-local rebinding / 保留单文件重绑定，不依赖模块目录。

    Optional paths limit work to newly indexed files; guards read no other file
    and must run exactly once before a file's binding summary is cached.
    可选 paths 仅处理新建索引；每个文件缓存前执行一次，且不读取其他文件。
    """
    for path in corpus.trees if paths is None else paths:
        tree = corpus.trees[path]
        pending = list(tree.body)
        while pending:
            node = pending.pop()
            names: set[str] = set()
            if isinstance(node, ast.NamedExpr):
                names.update(_stored_names(node.target))
            elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
                names.add(node.name)
            elif isinstance(node, ast.MatchMapping) and node.rest:
                names.add(node.rest)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                names.add(node.name)
            if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
                corpus.wildcards.add(path)
            for name in names:
                corpus.bindings[path].setdefault(name, []).append({"kind": "dynamic", "node": node})
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                # Definition-time expressions execute in the surrounding scope;
                # nested bodies do not. Parameters themselves do not bind here.
                pending.extend(_definition_expressions(node))
                continue
            if isinstance(node, ast.ClassDef):
                for name, write in _class_global_writes(node):
                    corpus.bindings[path].setdefault(name, []).append(
                        {"kind": "dynamic", "node": write})
                pending.extend(_definition_expressions(node))
                continue
            pending.extend(ast.iter_child_nodes(node))


def guard_references(references: list[dict], owner: ast.AST, scope_locals,
                     start: int, end: int) -> list[dict]:
    """Do not resolve collapsed references through a conflicting lexical scope.

    The inherited resolver keys references by expression/operation rather than
    lexical occurrence. If a name is bound in a nested scope, aggregating its
    occurrences cannot establish one module binding. Retain that uncertainty.
    """
    uncertain = pattern_names(owner)
    for node in ast.walk(owner):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) and node is not owner:
            local, ambiguous = scope_locals(node)
            # A partial direct witness can exclude the entire nested body. Its
            # local stores must not hide an outer global occurrence that is in
            # the selected span. Full declaration graphs include those nested
            # occurrences and retain the conflicting lexical scope.
            selected_loads = {child.id for child in ast.walk(node)
                              if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)
                              and start <= getattr(child, "lineno", 0) <= end}
            uncertain.update((local | ambiguous) & selected_loads)
        elif isinstance(node, ast.ClassDef):
            uncertain.update(_stored_names(node))
            uncertain.update(child.name for child in node.body if isinstance(child, _DECLARATIONS))
            for child in ast.walk(node):
                if isinstance(child, (ast.Import, ast.ImportFrom)):
                    uncertain.update(alias.asname or alias.name.split(".")[0] for alias in child.names)
                elif isinstance(child, ast.ExceptHandler) and child.name:
                    uncertain.add(child.name)
    for reference in references:
        if reference["expression"].split(".", 1)[0] in uncertain:
            reference.pop("target", None)
            reference.pop("bindings", None)
            reference.update(status="unresolved", reason="aggregated reference intersects nested, pattern, or class-local bindings")
    return references
