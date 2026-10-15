"""Process-local incremental static graphs / 进程内增量静态证据图。

Certificates preserve the resolver's output, never program semantics. The cache
is constructed from source inside this process and accepts no external proof.
证书仅保持静态解析器输出；不证明程序语义，也不接受外部提供的证书。
"""
from copy import deepcopy
from dataclasses import dataclass
from collections.abc import Mapping

from .dependencies import _Corpus
from .evidence import _safe_parts, sha256
from .graph import build_graph, _seal
from .parse_cache import ParseCache
from .module_cache import ModuleCache
from .catalog import ModuleCatalog, CATALOG_TRACE_VERSION


@dataclass(frozen=True)
class Replay:
    """Graphs and audit counts / 图与可审计的复用计数。"""
    graphs: list[dict]
    reused: int
    rebuilt: int
    reasons: dict[str, int]


class GraphSession:
    """Reuse source-read certificates across immutable snapshots.

    Anchors and policy are fixed at construction. Source maps are defensively
    copied; returned graphs cannot mutate the cached originals. A catalog change
    or changed consulted file triggers a rebuild. The default certificate mode
    requires complete graphs. The exploratory ``read_set_any_status`` ablation
    can reuse incomplete graphs while preserving every unknown/truncated state;
    a cache hit never upgrades freshness. This ablation was introduced after the
    primary study observed zero complete-graph coverage, not preregistered as a
    primary method. The whole-corpus baseline may reuse any byte-identical corpus.
    ``incremental_index_rebuild`` rebuilds every graph over guarded file summaries;
    ``incremental_read_set`` combines those same summaries with unknown-preserving
    read-set reuse. ``incremental_whole_corpus_guard`` combines the same summaries
    with whole-source equality checks. Historical modes retain their behavior.
    ``incremental_catalog_coarse_guard`` exempts valid zero-query graphs from
    whole-catalog invalidation; ``incremental_catalog_root_guard`` checks complete
    queried-root membership; ``incremental_catalog_read_set`` checks exact candidate
    tuples and namespace-existence answers. All three require valid versioned traces
    and unchanged consulted source bytes, and preserve incomplete output unchanged.

    构造时固定锚点与策略；防御性复制输入与输出。路径目录或读取文件改变时
    重建。默认模式只复用完整图；探索性 read_set_any_status 保留未知/截断状态，
    缓存命中不代表 fresh。该消融在主实验观察到完整图覆盖率为零后引入，非预注册
    主方法。全语料基线仅在全部源字节相同时复用。
    incremental_index_rebuild 复用已守卫文件摘要但重建所有图；incremental_read_set
    加入保留未知状态的读取集合复用；incremental_whole_corpus_guard 则仅在全部
    源码相同时复用图。已有模式行为保持不变。
    三种 incremental_catalog 模式分别使用查询感知的全目录、完整查询根成员和
    精确候选/命名空间存在性守卫；均要求有效版本化足迹及未变的读取字节，保留不完整输出。
    """
    MODES = {"warm_ast_rebuild", "whole_corpus_guard", "read_set_certificate",
             "read_set_any_status", "incremental_index_rebuild", "incremental_read_set",
             "incremental_whole_corpus_guard", "incremental_catalog_coarse_guard",
             "incremental_catalog_root_guard", "incremental_catalog_read_set"}

    def __init__(self, anchors: list[dict], *, mode: str = "read_set_certificate",
                 max_depth: int = 4, max_nodes: int = 256):
        if mode not in self.MODES:
            raise ValueError("unknown reuse mode / 未知复用模式")
        if not isinstance(anchors, list) or not anchors:
            raise ValueError("anchors must be nonempty / 锚点不能为空")
        self._anchors = deepcopy(anchors)
        self._mode = mode
        self._policy = {"max_depth": max_depth, "max_nodes": max_nodes}
        self._cache = ParseCache()
        self._module_cache = ModuleCache()
        self._hashes: dict[str, str] | None = None
        self._graphs: list[dict] = []
        self._reads: list[set[str]] = []
        self._catalog_footprints: list[dict] = []
        self._catalog_root_guards: list[dict] = []
        self._catalog_versions: list[int | None] = []

    @property
    def index_stats(self) -> dict[str, int]:
        """Last committed summary work; historical modes return zeros.

        Counters are separate from sealed graphs and cannot mutate cache state.
        上次成功更新的摘要工作量；历史模式为零。计数独立于图，返回值不暴露缓存。
        """
        return self._module_cache.stats

    def _catalog_trace_valid(self, index: int) -> bool:
        """Internal missing traces are not empty-query evidence / 缺失不等于有效空查询。"""
        return (index < len(self._catalog_versions)
                and self._catalog_versions[index] == CATALOG_TRACE_VERSION
                and index < len(self._catalog_footprints)
                and isinstance(self._catalog_footprints[index], dict)
                and index < len(self._catalog_root_guards)
                and isinstance(self._catalog_root_guards[index], dict))

    @property
    def catalog_stats(self) -> dict[str, int]:
        """Committed trace counts, not a semantic certificate / 已提交查询数，不是语义证书。"""
        traces = [q for i, q in enumerate(self._catalog_footprints) if self._catalog_trace_valid(i)]
        return {'available_traces': len(traces),
                'tracked_graphs': sum(bool(q) for q in traces),
                'catalog_free_graphs': sum(not q for q in traces),
                'exact_queries': sum(k[0] == 'exact' for q in traces for k in q),
                'subtree_queries': sum(k[0] == 'subtree' for q in traces for k in q)}

    def update(self, texts: Mapping[str, str], snapshot_id: str) -> Replay:
        """Hash all inputs then reuse or rebuild / 哈希全部输入后复用或重建。

        Callers provide a consistent immutable snapshot, not a live directory.
        No file access or untrusted source execution occurs here.
        调用方负责快照一致性；本函数不访问文件、不执行所分析的代码。
        """
        if not isinstance(snapshot_id, str) or not snapshot_id:
            raise ValueError("snapshot ID must be nonempty / 快照标识不能为空")
        current = dict(texts)
        for path, source in current.items():
            _safe_parts(path)
            if not isinstance(source, str):
                raise ValueError("source must be text / 源码必须为文本")
        hashes = {path: sha256(source) for path, source in current.items()}
        tracked = self._mode in {'incremental_catalog_coarse_guard',
                                 'incremental_catalog_root_guard', 'incremental_catalog_read_set'}
        incremental = tracked or self._mode in {'incremental_index_rebuild', 'incremental_read_set',
                                                'incremental_whole_corpus_guard'}
        catalog = ModuleCatalog(current) if tracked else None
        # A failed update discards its summaries; skipped graph builds still prune
        # changed/unread modules. No historical versions accumulate in the session.
        # 失败更新丢弃新摘要；全图复用也清理已改变的未读模块，不累积历史版本。
        module_cache = self._module_cache.for_snapshot(hashes) if incremental else None
        same_catalog = self._hashes is not None and hashes.keys() == self._hashes.keys()
        graphs, reads, footprints, root_guards, reasons = [], [], [], [], {}
        reused = 0
        corpus = None
        for index, anchor in enumerate(self._anchors):
            reason = "initial_capture"
            use = False
            if self._hashes is not None:
                graph = self._graphs[index]
                if self._mode in {"warm_ast_rebuild", "incremental_index_rebuild"}:
                    reason = "baseline_rebuild"
                elif self._mode in {"whole_corpus_guard", "incremental_whole_corpus_guard"}:
                    use = hashes == self._hashes
                    reason = "whole_corpus_equal" if use else "corpus_changed"
                elif tracked:
                    if not self._catalog_trace_valid(index):
                        reason = 'catalog_trace_unavailable'
                    elif any(hashes.get(path) != self._hashes.get(path)
                           for path in self._reads[index]):
                        reason = 'read_dependency_changed'
                    elif same_catalog:
                        use, reason = True, 'read_set_equal'
                    elif self._mode == 'incremental_catalog_coarse_guard':
                        use = not self._catalog_footprints[index]
                        reason = 'catalog_free_graph' if use else 'catalog_changed'
                    elif self._mode == 'incremental_catalog_root_guard':
                        use = catalog.roots_match(self._catalog_root_guards[index])
                        reason = 'catalog_root_equal' if use else 'catalog_root_changed'
                    else:
                        use = catalog.matches(self._catalog_footprints[index])
                        reason = 'catalog_queries_equal' if use else 'catalog_query_changed'
                elif not same_catalog:
                    reason = "catalog_changed"
                elif self._mode == "read_set_certificate" and graph["frontier"]:
                    reason = "incomplete_graph"
                elif any(hashes.get(path) != self._hashes.get(path)
                         for path in self._reads[index]):
                    reason = "read_dependency_changed"
                else:
                    use, reason = True, "read_set_equal"
            if use:
                graph = deepcopy(self._graphs[index])
                graph["snapshot_id"] = snapshot_id
                _seal(graph)
                read_set = self._reads[index].copy()
                footprint = self._catalog_footprints[index].copy()
                roots = self._catalog_root_guards[index].copy()
                reused += 1
            else:
                read_set = set()
                if corpus is None:
                    corpus = (_Corpus.from_texts(current, module_cache=module_cache,
                                                _source_hashes=hashes, _catalog=catalog,
                                                _track_catalog=tracked) if incremental else
                              _Corpus.from_texts(current, parsed_cache=self._cache))
                corpus.lookup_paths.clear()
                corpus.catalog_queries.clear()
                graph = build_graph(current, snapshot_id, [anchor], **self._policy,
                                    parsed_cache=self._cache, read_set=read_set, _corpus=corpus)
                footprint = corpus.catalog_queries.copy()
                roots = catalog.root_guards(footprint) if tracked else {}
            graphs.append(graph)
            reads.append(read_set)
            footprints.append(footprint)
            root_guards.append(roots)
            reasons[reason] = reasons.get(reason, 0) + 1
        # Publish atomically only after every anchor succeeded. Old AST entries are
        # discarded between snapshots to bound memory by the current source set.
        # 全部锚点成功后才更新状态；清理旧 AST，避免版本历史无限累积。
        self._cache.memory = {key: tree for key, tree in self._cache.memory.items()
                              if hashes.get(key[0]) == key[1]}
        self._hashes, self._graphs, self._reads = hashes, graphs, reads
        self._catalog_footprints, self._catalog_root_guards = footprints, root_guards
        self._catalog_versions = [CATALOG_TRACE_VERSION if tracked else None] * len(graphs)
        if module_cache is not None:
            self._module_cache = module_cache
        return Replay(deepcopy(graphs), reused, len(graphs) - reused, reasons)
