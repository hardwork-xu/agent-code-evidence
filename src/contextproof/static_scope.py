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


def _mangle(name: str, private_class: str | None) -> str:
    """Compiler-style private binding name / 编译器规则下的类私有绑定名。"""
    if (not private_class or not name.startswith("__") or name.endswith("__")
            or "." in name):
        return name
    class_name = private_class.lstrip("_")
    return "_" + class_name + name if class_name else name


def _binding_scopes(tree: ast.Module):
    """Yield blocks with their class mangling context / 返回词法块及类名改写上下文。"""
    pending = [(tree, None)]
    while pending:
        node, private_class = pending.pop()
        if isinstance(node, ast.ClassDef):
            yield node, node.name
            pending.extend((child, node.name) for child in node.body)
            pending.extend((child, private_class) for child in _definition_expressions(node))
        else:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield node, private_class
            pending.extend((child, private_class) for child in ast.iter_child_nodes(node))


def _scope_global_writes(owner: ast.AST, private_class: str | None) -> list[tuple[str, ast.AST]]:
    """Find explicit global binding writes in one lexical block.

    A function may execute later, so a possible write prevents a fixed module
    binding witness even if no call or branch reachability is established.
    Nested bodies have independent global declarations; defaults/decorators
    execute in the containing block. Comprehension iteration targets are local,
    while assignment expressions can bind a containing function's global.

    单独收集一个词法块的显式 global 重绑定。函数可能稍后执行；不假定调用
    或分支可达。嵌套体声明独立，定义时表达式属于外层；推导式循环变量不
    重绑定外层，但赋值表达式可能重绑定外层函数声明的全局名。
    """
    globals_: set[str] = set()
    writes: list[tuple[str, ast.AST]] = []
    pending = list(owner.body)
    while pending:
        node = pending.pop()
        names: set[str] = set()
        if isinstance(node, ast.Global):
            globals_.update(_mangle(name, private_class) for name in node.names)
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
        writes.extend((_mangle(name, private_class), node) for name in sorted(names))
        if isinstance(node, (*_DECLARATIONS, ast.Lambda)):
            pending.extend(_definition_expressions(node))
        elif isinstance(node, ast.comprehension):
            # Ignore iteration targets; scan assignment expressions in the rest.
            # 忽略推导式迭代目标，保留其它表达式中的外层赋值表达式。
            pending.extend([node.iter, *node.ifs])
        else:
            pending.extend(ast.iter_child_nodes(node))
    return [(name, node) for name, node in writes if name in globals_]


def guard_module_bindings(corpus: Any, paths=None) -> None:
    """Retain source-local rebinding / 保留单文件重绑定，不依赖模块目录。

    Optional paths limit work to newly indexed files; guards read no other file
    and must run exactly once before a file's binding summary is cached.
    可选 paths 仅处理新建索引；每个文件缓存前执行一次，且不读取其他文件。
    """
    for path in corpus.trees if paths is None else paths:
        tree = corpus.trees[path]
        # Every explicit function/class block can potentially rebind a module
        # global. Scan each block once; never execute repository code.
        # 每个函数/类块都可能显式重绑定模块全局名；逐块扫描，不执行源码。
        for owner, private_class in _binding_scopes(tree):
            for name, write in _scope_global_writes(owner, private_class):
                corpus.bindings[path].setdefault(name, []).append(
                    {"kind": "dynamic", "node": write, "origin": "explicit_global_write"})
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
