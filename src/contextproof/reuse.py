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

    构造时固定锚点与策略；防御性复制输入与输出。路径目录或读取文件改变时
    重建。默认模式只复用完整图；探索性 read_set_any_status 保留未知/截断状态，
    缓存命中不代表 fresh。该消融在主实验观察到完整图覆盖率为零后引入，非预注册
    主方法。全语料基线仅在全部源字节相同时复用。
    """
    MODES = {"warm_ast_rebuild", "whole_corpus_guard", "read_set_certificate",
             "read_set_any_status"}

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
        self._hashes: dict[str, str] | None = None
        self._graphs: list[dict] = []
        self._reads: list[set[str]] = []

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
        same_catalog = self._hashes is not None and hashes.keys() == self._hashes.keys()
        graphs, reads, reasons = [], [], {}
        reused = 0
        corpus = None
        for index, anchor in enumerate(self._anchors):
            reason = "initial_capture"
            use = False
            if self._hashes is not None:
                graph = self._graphs[index]
                if self._mode == "warm_ast_rebuild":
                    reason = "baseline_rebuild"
                elif self._mode == "whole_corpus_guard":
                    use = hashes == self._hashes
                    reason = "whole_corpus_equal" if use else "corpus_changed"
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
                reused += 1
            else:
                read_set = set()
                if corpus is None:
                    corpus = _Corpus.from_texts(current, parsed_cache=self._cache)
                corpus.lookup_paths.clear()
                graph = build_graph(current, snapshot_id, [anchor], **self._policy,
                                    parsed_cache=self._cache, read_set=read_set, _corpus=corpus)
            graphs.append(graph)
            reads.append(read_set)
            reasons[reason] = reasons.get(reason, 0) + 1
        # Publish atomically only after every anchor succeeded. Old AST entries are
        # discarded between snapshots to bound memory by the current source set.
        # 全部锚点成功后才更新状态；清理旧 AST，避免版本历史无限累积。
        self._cache.memory = {key: tree for key, tree in self._cache.memory.items()
                              if hashes.get(key[0]) == key[1]}
        self._hashes, self._graphs, self._reads = hashes, graphs, reads
        return Replay(deepcopy(graphs), reused, len(graphs) - reused, reasons)
