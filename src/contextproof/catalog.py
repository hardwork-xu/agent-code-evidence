"""Process-local module lookup footprints / 进程内模块目录查询足迹。

This index models this resolver's aliases, not Python's complete import system.
An unchanged recorded answer preserves a lookup branch, not program semantics.
该索引只描述当前解析器的别名；查询结果相同不证明Python运行时语义。
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from types import MappingProxyType
from collections.abc import Iterable, Mapping

from .evidence import _safe_parts

CATALOG_TRACE_VERSION = 1

Query = tuple[str, str]
Answer = tuple[str, ...] | bool


class ModuleCatalog:
    """Immutable path-derived aliases and namespace existence / 路径别名与命名空间存在性。

    Catalogs are constructed from current source keys inside the trusted process.
    No external serialized certificate is accepted. Source content guards remain
    separate; missing/ambiguous/unparseable candidates still belong to this index.
    在可信进程内从当前路径构造；不接受外部证书，文件内容仍由独立哈希守卫。
    """

    def __init__(self, paths: Iterable[str]):
        modules: dict[str, list[str]] = defaultdict(list)
        eligible = []
        for path in sorted(set(paths)):
            _safe_parts(path)
            if Path(path).suffix.lower() not in {'.py', '.pyi'}:
                continue
            eligible.append(path)
            parts = list(Path(path).with_suffix('').parts)
            if parts[-1] == '__init__':
                parts.pop()
            names = {'.'.join(parts)}
            if len(parts) > 1 and parts[0] == 'src':
                names.add('.'.join(parts[1:]))
            for name in sorted(names - {''}):
                modules[name].append(path)
        self.source_paths = tuple(eligible)
        self._modules = MappingProxyType({name: tuple(values) for name, values in sorted(modules.items())})
        # A qualified namespace branch asks existence, not the identity of every
        # sibling below it. Exact candidate queries cover downstream resolution.
        # 命名空间分支只询问存在性；后续精确查询另行登记。
        self._subtrees = set(self._modules)
        roots: dict[str, list[tuple[str, tuple[str, ...]]]] = defaultdict(list)
        for name, values in self._modules.items():
            parts = name.split('.')
            self._subtrees.update('.'.join(parts[:i]) for i in range(1, len(parts)))
            roots[parts[0]].append((name, values))
        self._subtrees = frozenset(self._subtrees)
        self._roots = MappingProxyType({root: tuple(values) for root, values in roots.items()})

    def candidates(self, module: str) -> tuple[str, ...]:
        """Return exact ordered candidates, including empty / 返回有序候选，包含空结果。"""
        return self._modules.get(module, ())

    def subtree_exists(self, module: str) -> bool:
        """Match exact-or-descendant existence / 精确模块或后代是否存在。"""
        return module in self._subtrees

    def mapping(self) -> dict[str, list[str]]:
        """Defensive historical corpus view / 防御性复制既有语料视图。"""
        return {name: list(paths) for name, paths in self._modules.items()}

    def answer(self, query: Query) -> Answer:
        kind, name = query
        if kind == 'exact':
            return self.candidates(name)
        if kind == 'subtree':
            return self.subtree_exists(name)
        raise ValueError('unknown catalog query kind / 未知目录查询类型')

    def matches(self, footprint: Mapping[Query, Answer]) -> bool:
        """Check every positive and negative answer / 核对所有正负查询。"""
        return all(self.answer(query) == expected for query, expected in footprint.items())

    def root_guards(self, footprint: Mapping[Query, Answer]) -> dict[str, tuple]:
        """Stronger coarse comparator: entire queried roots / 粗对照监控整个查询根目录。"""
        roots = {name.split('.')[0] for _, name in footprint}
        # An empty root is conservatively all modules. Most supported relative
        # imports cannot generate it; do not assume that to weaken this baseline.
        return {root: self._roots.get(root, ()) if root else tuple(self._modules.items())
                for root in sorted(roots)}

    def roots_match(self, guards: Mapping[str, tuple]) -> bool:
        """Compare saved root membership, not contents / 比较保存的根成员，不替代内容守卫。"""
        return all((self._roots.get(root, ()) if root else tuple(self._modules.items())) == expected
                   for root, expected in guards.items())
