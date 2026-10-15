"""Private guarded module summaries / 进程内已守卫模块摘要。

These are source-local syntax summaries, never resolved import results. Catalogs,
lookup reads, and graph outputs belong to each corpus. ASTs are private read-only
objects, as in ParseCache; GraphSession neither returns nor accepts these summaries.
摘要仅保存单文件语法事实，不缓存导入解析结果。目录、读取集合及图输出各自独立；
AST 与 ParseCache 一样由内部只读使用，GraphSession 不暴露或接收这些摘要。
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class _ModuleSummary:
    tree: ast.Module | None
    bindings: Mapping
    definitions: Mapping
    wildcard: bool

    @classmethod
    def capture(cls, tree, bindings=None, definitions=None, wildcard=False):
        """Freeze every summary container / 冻结摘要容器，解析失败也有独立摘要。"""
        return cls(tree, MappingProxyType({
            name: tuple(MappingProxyType(dict(binding)) for binding in values)
            for name, values in (bindings or {}).items()
        }), MappingProxyType({name: tuple(values)
                              for name, values in (definitions or {}).items()}), wildcard)


class ModuleCache:
    """Session-owned current-version cache / 会话专属、仅保留当前版本的缓存。

    Keys are (source path, source SHA256), including syntax-error summaries. The
    guard depends only on this file's AST, so catalog changes require new lookup
    resolution, not reindexing unchanged files. ``for_snapshot`` creates a fresh
    transaction; callers publish it only after every graph has succeeded.
    键为路径与源码哈希，包含语法错误摘要。守卫仅依赖本文件 AST；目录变化须重新
    解析查找，但无需重建未变文件的摘要。新事务仅在全部图成功后由会话发布。
    """

    def __init__(self):
        self._entries: dict[tuple[str, str], _ModuleSummary] = {}
        self._indexed = self._reused = self._invalid = 0

    def for_snapshot(self, hashes: Mapping[str, str]) -> ModuleCache:
        result = ModuleCache()
        result._entries = {key: value for key, value in self._entries.items()
                           if hashes.get(key[0]) == key[1]}
        return result

    def lookup(self, key: tuple[str, str]) -> _ModuleSummary | None:
        summary = self._entries.get(key)
        if summary is not None:
            self._reused += 1
            self._invalid += summary.tree is None
        return summary

    def store(self, key: tuple[str, str], summary: _ModuleSummary) -> None:
        self._entries[key] = summary
        self._indexed += 1
        self._invalid += summary.tree is None

    @property
    def stats(self) -> dict[str, int]:
        """Actual work in this update, outside graph artifacts / 仅报告本轮实际工作。

        Indexed counts newly created summaries (including failed parses); reused
        counts loaded summaries. Invalid counts encountered parse failures. When
        every graph is reused, all three are zero; retained still reports storage.
        indexed 包含新建的解析失败摘要；reused 是加载数，invalid 是本轮遇到的
        解析失败数。全图命中时这三项为零，retained 仍反映当前保留条目数。
        """
        return {"indexed_modules": self._indexed, "reused_modules": self._reused,
                "invalid_modules": self._invalid, "retained_modules": len(self._entries)}
