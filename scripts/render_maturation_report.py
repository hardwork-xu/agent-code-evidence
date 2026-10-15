#!/usr/bin/env python3
"""Render bilingual research reports only from validated completed evidence.

No source packages, task workers, graph construction or performance runs execute.
仅校验、汇总已完成的原始记录；不运行上游代码、任务、图构建或性能实验。
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_incremental_holdout as holdout  # noqa: E402
from scripts import run_selective_ablation as ablation  # noqa: E402
from scripts import run_selective_reuse as historical  # noqa: E402
from scripts import run_task_evidence as tasks  # noqa: E402

DEFAULT_HOLDOUT = ROOT / 'benchmarks/incremental_holdout/results/primary-20261004.json'
DEFAULT_TASKS = ROOT / 'benchmarks/task_evidence/results/primary-20261004'
METHODS = {
    'warm_ast_rebuild': 'AST', 'whole_corpus_guard': 'WCG',
    'read_set_any_status': 'RS', 'incremental_index_rebuild': 'IDX',
    'incremental_whole_corpus_guard': 'IWCG', 'incremental_read_set': 'IRS',
}
TASK_METHODS = {
    'fresh_full_source': 'Full source', 'fresh_anchors': 'Anchors',
    'fresh_graph': 'Graph', 'lexical_matched_lines': 'BM25',
    'stale_graph_current_bytes': 'Old graph',
}


def read(path):
    return json.loads(path.read_text())


def public_path(path):
    """Reports must link only repository-relative public artifacts."""
    return path.resolve().relative_to(ROOT).as_posix()


def table(headers, rows):
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ')
    return '\n'.join(['| ' + ' | '.join(map(cell, headers)) + ' |',
                      '|' + '|'.join('---' for _ in headers) + '|',
                      *['| ' + ' | '.join(map(cell, row)) + ' |' for row in rows]])


def pct(value, signed=False):
    return 'n/a' if value is None else format(value, '+.1%' if signed else '.1%')


def interval(values, scale=1):
    """The same numeric formatter is used in both language editions."""
    return (f"{values['median'] / scale:.2f} "
            f"[{values['min'] / scale:.2f}, {values['max'] / scale:.2f}]")


def summarize_values(values):
    return {'median': statistics.median(values), 'min': min(values), 'max': max(values)}


def counters(values):
    return ', '.join(f'{key}={value}' for key, value in sorted(values.items())) or 'none / 无'


def validated_data(holdout_path, task_directory):
    public_path(holdout_path)
    public_path(task_directory)
    protocol, manifest = holdout.load_inputs()
    raw = read(holdout_path)
    if raw.get('suite') != 'all' or set(raw.get('methods', [])) != set(METHODS):
        raise ValueError('report requires the full six-method timing and memory study')
    summary = holdout.summarize(raw, protocol, manifest)
    if raw.get('summary') != summary:
        raise ValueError('stored holdout summary differs from validated raw records')
    task_validation = tasks.validate_result_bundle(task_directory)
    task_manifest = read(tasks.BENCH / 'manifest.json')
    task_summary = read(task_directory / 'summary.json')
    task_rows = read(task_directory / 'cases.json')
    task_runs = read(task_directory / 'runs.json')
    task_provenance = read(task_directory / 'provenance.json')
    old_path = ROOT / 'benchmarks/selective_reuse/results/primary-20261004.json'
    old = read(old_path)
    old_summary = historical.summarize(old)
    exploratory_path = ROOT / 'benchmarks/selective_reuse/results/ablation-20261004.json'
    exploratory = read(exploratory_path)
    exploratory_summary = ablation.analyze(exploratory)
    if old.get('summary') != old_summary or exploratory.get('summary') != exploratory_summary:
        raise ValueError('historical raw records and summaries disagree')
    return dict(protocol=protocol, manifest=manifest, raw=raw, summary=summary,
                task_validation=task_validation, task_manifest=task_manifest,
                task_summary=task_summary, task_rows=task_rows, task_runs=task_runs,
                task_provenance=task_provenance, old=old, old_summary=old_summary,
                exploratory=exploratory, exploratory_summary=exploratory_summary,
                holdout_path=public_path(holdout_path), task_path=public_path(task_directory))


def report(data, lang):
    def tr(en, zh):
        return en if lang == 'en' else zh

    def verdict(value):
        return tr('met', '达到') if value else tr('not met', '未达到')

    protocol, manifest = data['protocol'], data['manifest']
    raw, summary = data['raw'], data['summary']
    task_rows, task_summary = data['task_rows'], data['task_summary']
    repos, methods = manifest['repositories'], protocol['methods']
    baseline = protocol['primary_comparison']['baseline']
    candidate = protocol['primary_comparison']['candidate']
    targets = protocol['targets']
    versions = protocol['natural']['versions']
    transitions = len(repos) * (versions - 1)
    changed = sum(repo['source_changed_transitions'] for repo in repos)
    nanchors = sum(len(repo['anchors']) for repo in repos)
    overall = summary['replay_target_met'] and summary['memory_gate_met']
    graph_better = [r['id'] for r in task_rows if
                    r['metrics']['fresh_graph']['recall'] > r['metrics']['lexical_matched_lines']['recall']]
    graph_worse = [r['id'] for r in task_rows if
                   r['metrics']['fresh_graph']['recall'] < r['metrics']['lexical_matched_lines']['recall']]
    graph_tied = [r['id'] for r in task_rows if
                  r['metrics']['fresh_graph']['recall'] == r['metrics']['lexical_matched_lines']['recall']]
    graph_below_anchors = [r['id'] for r in task_rows if
                           r['metrics']['fresh_graph']['recall'] < r['metrics']['fresh_anchors']['recall']]
    graph_lower_groups = [name for name, value in task_summary['aggregate'].items()
                          if name != 'all' and value['methods']['fresh_graph']['macro_recall']
                          < value['methods']['lexical_matched_lines']['macro_recall']]
    task_aggregate = task_summary['aggregate']['all']['methods']
    frontier_cases = sum(bool(row['graph_frontier']) for row in task_rows)
    cold_pairs = sum(len(row['graphs']) for row in raw['cold_reference'])
    incomplete_pairs = cold_pairs - sum(row['complete'] for row in raw['cold_reference'])
    timing_graphs = sum(len(row['graphs']) for row in raw['timing_rows'])
    memory_graphs = sum(len(row['graphs']) for trial in raw['memory_trials'] for row in trial['rows'])
    sections = []

    def add(title, content):
        sections.append('## ' + title + '\n\n' + content.strip())

    sections.append('# ' + tr('Incremental code-evidence reuse and task execution witnesses',
                              '增量代码证据复用与任务执行见证') + '\n\n' + tr(
        '**Status: reproducible engineering research report; no claim of submission maturity, '
        'SOTA, independent human review or coding-agent improvement.** Tables and verdicts are '
        'generated from validated completed records. The invalid task pilot supplies no result claim.',
        '**状态：可复核的工程研究报告；不声称投稿成熟度、SOTA、独立人工评审或代码 Agent 收益。** '
        '表格与达标判断由已完成且通过校验的记录生成，无效任务试运行不提供结论证据。'))

    add(tr('Abstract', '摘要'), tr(
        f'We evaluate a process-local application of dependency tracking to bounded Python '
        f'source-evidence graphs. A repository-held-out convenience sample contains {len(repos)} '
        f'repositories, {versions} pinned revisions each and {nanchors} fixed anchors. The candidate '
        f'is compared with persistent module indexing plus whole-corpus-equality reuse. '
        f'{summary["repositories_meeting_replay_target"]}/{len(repos)} repositories reach the '
        f'{pct(targets["replay_reduction"])} replay reduction threshold; the timing target is '
        f'**{verdict(summary["replay_target_met"])}** and the RSS gate is '
        f'**{verdict(summary["memory_gate_met"])}**. Completed records contain '
        f'{summary["canonical_mismatches"]} canonical mismatches against uncached reconstruction. '
        f'{incomplete_pairs}/{cold_pairs} reference graphs retain incomplete frontiers: the cache '
        f'preserves those unknowns and does not certify fresh semantics. '
        f'A separate, corrected {len(task_rows)}-case development study executes original upstream '
        f'assertion bodies with reviewed fixture adaptations. Graph and matched-line BM25 macro '
        f'execution-witness recall are {pct(task_aggregate["fresh_graph"]["macro_recall"])} and '
        f'{pct(task_aggregate["lexical_matched_lines"]["macro_recall"])}. These are separate '
        f'observations about replay cost and task-conditioned source coverage; neither establishes '
        f'context sufficiency, semantic soundness or model-task benefit.',
        f'本研究将既有依赖追踪思想用于进程内、有界 Python 源码证据图。仓库层面的留出便利样本包含 '
        f'{len(repos)} 个仓库、每库 {versions} 个固定版本及共 {nanchors} 个固定锚点。候选方法与 '
        f'“持久模块索引＋全语料相等复用”比较。{summary["repositories_meeting_replay_target"]}/{len(repos)} '
        f'个仓库达到 {pct(targets["replay_reduction"])} 的回放降时阈值；时间目标**'
        f'{verdict(summary["replay_target_met"])}**，RSS 门槛**{verdict(summary["memory_gate_met"])}**。'
        f'完整记录相对无跨版本缓存的重建共有 {summary["canonical_mismatches"]} 个规范图不一致。'
        f'{incomplete_pairs}/{cold_pairs} 个参照图仍有不完整边界：缓存保留 unknown，并不认证语义 fresh。'
        f'另一项经修正的 {len(task_rows)} 案例开发研究，按已审查的 fixture 适配方式执行上游原始断言函数体。'
        f'图与等行数 BM25 的任务执行见证宏平均召回率分别为 '
        f'{pct(task_aggregate["fresh_graph"]["macro_recall"])} 和 '
        f'{pct(task_aggregate["lexical_matched_lines"]["macro_recall"])}。回放成本与任务相关源码覆盖是不同结论；'
        f'二者均不能证明上下文充分性、语义可靠性或模型任务收益。'))

    add(tr('1. Research questions and contribution boundary', '1. 研究问题与贡献边界'), tr(
        'RQ1 asks whether selective read-set replay adds value beyond both persistent indexing '
        'and the cheap whole-corpus guard, at disclosed end-to-end ingestion and memory costs. '
        'RQ2 asks which lines actually executed by specific upstream assertions are present in '
        'each supplied context. The second label is obtained from Python execution, independently '
        'of static dependency extraction, but is not human gold context. Source identity, resolver '
        'equality, execution coverage and agent success remain distinct claims.\n\n'
        'Module summaries cache parsed source and guarded bindings by path and source hash; '
        'cross-file resolution uses the current catalog. Read sets include unsuccessful candidate '
        'lookups. Catalog changes conservatively invalidate reuse; incomplete frontiers remain '
        'incomplete. Graphs are copied/resealed, old summaries are pruned, and session state is '
        'published only after the update succeeds. Every source byte is still hashed; avoiding '
        'index work does not remove archive I/O, decoding or graph-output costs. '
        '[Exact mechanism and assumptions](INCREMENTAL_DESIGN.md).',
        'RQ1：在披露完整输入处理成本与内存成本的条件下，选择性读集复用能否超越持久索引和廉价全语料判断的组合？'
        'RQ2：特定上游断言真正执行过的源码行，有多少出现在各类提供的上下文中？第二类标签来自 Python 实际执行，'
        '独立于静态依赖提取，但并非人工标注的金标准上下文。源码身份、解析器等价、执行覆盖与 Agent 成功分别讨论。\n\n'
        '模块摘要按路径和源码哈希缓存 AST 与带约束的绑定；跨文件解析始终使用当前目录。读集保留失败候选查找；'
        '目录变化保守失效，不完整边界继续保持不完整。输出图复制并重新封装，旧摘要被清理，全部锚点成功后才发布新状态。'
        '仍需哈希全部源码；少做索引不能消除归档 I/O、解码及图输出成本。'
        '[具体机制与假设](INCREMENTAL_DESIGN.md)。'))

    method_rows = [
        ['AST', '`warm_ast_rebuild`', tr('warm AST; rebuild bindings and graphs', '缓存 AST；重建绑定及图')],
        ['WCG', '`whole_corpus_guard`', tr('warm AST; reuse only an equal source map', '缓存 AST；仅全源码相等时复用图')],
        ['RS', '`read_set_any_status`', tr('warm AST; selective reuse preserving every frontier', '缓存 AST；选择性复用并保留边界')],
        ['IDX', '`incremental_index_rebuild`', tr('persistent module summaries; rebuild every graph', '持久模块摘要；每次重建图')],
        ['IWCG', '`incremental_whole_corpus_guard`', tr('persistent summaries plus whole-corpus reuse; PRIMARY BASELINE', '持久摘要＋全语料复用；主基线')],
        ['IRS', '`incremental_read_set`', tr('persistent summaries plus read-set reuse; CANDIDATE', '持久摘要＋读集复用；候选方法')],
    ]
    add(tr('2. Frozen design and comparators', '2. 固定设计与比较方法'), tr(
        f'The four repositories are absent from the historical/development source corpora. '
        f'The latest stable release and seven contiguous first parents were pinned before graph '
        f'outcomes. Exactly {protocol["natural"]["anchors"]} top-level function identities per '
        f'repository were SHA-ranked in the oldest version and never reselected. Duplicate '
        f'declarations, missing/ambiguous anchors and every transition remain. This is a local '
        f'prespecification, not public preregistration.\n\n'
        f'Source-only inspection found {transitions-changed}/{transitions} source-identical '
        f'transitions. Before any held-out graph/timing observation, an explicit amendment added '
        f'IWCG and strengthened the primary comparator from IDX to IWCG. Original protocol and '
        f'manifest bytes remain archived; sources, anchors and targets were unchanged. All methods '
        f'share one indexed corpus within a snapshot. The public default strict completeness '
        f'policy is unchanged; this experiment evaluates the named experimental modes.\n\n',
        f'四个仓库均不在历史及开发源码语料中。图结果观察前，固定最新稳定 release 及其前七个相邻 first-parent '
        f'提交；在最旧版本按 SHA 排序选每库 {protocol["natural"]["anchors"]} 个顶层函数身份，后续不重选。'
        f'重复定义、缺失或含糊锚点以及全部转换都保留。这是本地预先声明，不是公开预注册。\n\n'
        f'仅检查输入字节时发现 {transitions-changed}/{transitions} 次转换源码相同。尚未观察任何留出图或计时结果时，'
        f'明确修订加入 IWCG，并将主比较从 IDX 加强为 IWCG。原协议与清单完整留存，源码、锚点、阈值不变。'
        f'各方法均在同一快照内共享索引语料。公开默认模式的严格完整性门槛未变；此处评估明确命名的实验模式。\n\n')
        + table([tr('ID', '缩写'), tr('Mode', '模式'), tr('Behavior', '行为')], method_rows)
        + '\n\n' + tr(
            '[Final protocol](../../benchmarks/incremental_holdout/protocol.json) · '
            '[Initial protocol](../../benchmarks/incremental_holdout/initial-protocol.json) · '
            '[Frozen source/anchor manifest](../../benchmarks/incremental_holdout/manifest.json).',
            '[最终协议](../../benchmarks/incremental_holdout/protocol.json) · '
            '[原协议](../../benchmarks/incremental_holdout/initial-protocol.json) · '
            '[固定源码与锚点清单](../../benchmarks/incremental_holdout/manifest.json)。'))

    corpus_rows = []
    for repo in repos:
        corpus_rows.append([repo['repository'], repo['tag'], len(repo['versions'][0]['files']),
                            max(v['source_bytes'] for v in repo['versions']), len(repo['anchors']),
                            repo['source_changed_transitions'], repo['source_unchanged_transitions']])
    add(tr('3. Workload and measurement boundaries', '3. 工作负载与测量边界'),
        table([tr('Repository', '仓库'), 'Release', tr('Files at first version', '首版文件数'),
               tr('Max source bytes', '最大源码字节数'), tr('Anchors', '锚点'),
               tr('Changed transitions', '源码改变转换'), tr('Identical transitions', '源码相同转换')], corpus_rows)
        + '\n\n' + tr(
            f'One complete-trajectory warmup and {protocol["repetitions"]} measured trajectories '
            f'per method are rotated in whole-method order. Each starts with a fresh GraphSession. '
            f'The primary observation is the sum of seven replay transitions per trajectory; '
            f'tables report its median and min/max, not a pooled transition or anchor statistic. '
            f'Local archive reads, hashes, decompression, decoding, source checks, indexing, guards, '
            f'copying/sealing and fallback are timed. Downloads, canonical comparison and result '
            f'serialization are outside timing. Capture is separately reported, and capture plus '
            f'replay remains a required secondary result; process startup/session construction '
            f'is not included in these timing sums. Changed-only strata are descriptive and never '
            f'replace the fixed primary endpoint. Background OS activity is not controlled.',
            f'各方法先完整预热一条轨迹，再记录 {protocol["repetitions"]} 条轨迹，按整条方法轨迹轮换顺序。'
            f'每次使用新 GraphSession。主要观察值是每条轨迹七次回放转换的耗时总和；表格给出其中位数及最小/最大值，'
            f'不把转换或锚点混合当作独立观测。本地归档读取、哈希、解压、解码、源码校验、索引、检查、复制/封装及回退'
            f'全部计时；下载、规范图比较与结果写出不计入。首次捕获单列，捕获加回放是必报次要指标；这些耗时总和'
            f'不包括进程启动及会话构造。仅源码改变的分层结果属于描述性分析，不替换固定主指标。未控制操作系统背景活动。'))

    decision_rows = []
    for repo in repos:
        name = repo['repository']
        group = summary['groups'][name]
        b, c = (group['methods'][m] for m in [baseline, candidate])
        decision_rows.append([name, interval(b['replay_ms']), interval(c['replay_ms']),
                              pct(group['candidate_replay_reduction'], True),
                              verdict(group['replay_target_met']), f"{group['candidate_rss_ratio']:.3f}×",
                              verdict(group['memory_gate_met'])])
    add(tr('4. Primary results and target decisions', '4. 主结果与达标判断'), tr(
        f'The prespecified speed criterion is at least {pct(targets["replay_reduction"])} lower '
        f'median replay time in at least {targets["min_repositories"]}/{len(repos)} repositories. '
        f'Every repository must also remain at no more than {targets["max_rss_ratio"]}× baseline '
        f'median uninstrumented peak RSS and {targets["max_rss_bytes"] / 2**20:.0f} MiB. '
        f'**Timing: {verdict(summary["replay_target_met"])}; memory: '
        f'{verdict(summary["memory_gate_met"])}; combined gates: {verdict(overall)}.** '
        f'Positive reduction is faster; a negative value is a regression.\n\n',
        f'预定时间标准是在至少 {targets["min_repositories"]}/{len(repos)} 个仓库中，中位回放时间降低不少于 '
        f'{pct(targets["replay_reduction"])}。同时每个仓库的未启用追踪器 RSS 峰值中位数不得超过基线 '
        f'{targets["max_rss_ratio"]} 倍或 {targets["max_rss_bytes"] / 2**20:.0f} MiB。'
        f'**时间：{verdict(summary["replay_target_met"])}；内存：{verdict(summary["memory_gate_met"])}；'
        f'联合门槛：{verdict(overall)}。** 降时为正表示更快，负值表示退步。\n\n')
        + table([tr('Repository', '仓库'), 'IWCG ms [min,max]', 'IRS ms [min,max]',
                 tr('Reduction', '降时'), tr('Speed gate', '时间门槛'), 'RSS IRS/IWCG',
                 tr('Memory gate', '内存门槛')], decision_rows)
        + '\n\n' + tr(
            f'Validation matched {cold_pairs} distinct snapshot/anchor references, '
            f'{timing_graphs} emitted timing graph digests and {memory_graphs} emitted memory-run '
            f'graph digests to freshly parsed per-snapshot references, with zero canonical '
            f'mismatches. These repeated outputs are not independent semantic test cases.',
            f'校验将 {cold_pairs} 个不同快照/锚点参照、计时中的 {timing_graphs} 个图摘要和内存运行中的 '
            f'{memory_graphs} 个图摘要与逐快照重新解析的参照比较，规范图不一致为零。这些重复输出不是独立语义测试案例。'))

    timing_rows = []
    for repo in repos:
        for method in methods:
            values = summary['groups'][repo['repository']]['methods'][method]
            timing_rows.append([repo['repository'], METHODS[method], *[
                interval(values[key]) for key in ['replay_ms', 'source_changing_replay_ms',
                                                  'capture_ms', 'capture_plus_replay_ms']]])
    add(tr('5. All methods, adverse strata and startup cost', '5. 全部方法、分层与首次捕获成本'),
        tr('All cells are ms median [minimum, maximum] across trajectory totals. Changed-only totals '
           'contain different numbers of transitions by repository; compare methods within the same '
           'repository, not these totals across repositories.\n\n',
           '所有数值为轨迹耗时总和的 ms 中位数 [最小值，最大值]。各仓库仅源码改变的转换数不同，'
           '应在同一仓库内比较方法，不应直接横比该分层总耗时。\n\n')
        + table([tr('Repository', '仓库'), tr('Method', '方法'), tr('Replay', '回放'),
                 tr('Changed-only replay', '仅源码改变回放'), tr('Capture', '捕获'),
                 tr('Capture + replay', '捕获＋回放')], timing_rows))

    rss_rows, traced_rows, trajectory_rows = [], [], []
    for repo in repos:
        name = repo['repository']
        for method in methods:
            values = summary['groups'][name]['methods'][method]
            rss_rows.append([name, METHODS[method], interval(values['rss']['rss_peak_bytes'], 2**20)])
            traced_rows.append([name, METHODS[method],
                                interval(values['python_traced']['python_peak_bytes'], 2**20),
                                interval(values['python_traced']['python_final_retained_bytes'], 2**20)])
        for version in range(versions):
            row = [name, version, repo['versions'][version]['commit'][:10]]
            for method in [baseline, candidate]:
                values = [next(row['python_retained_bytes'] for row in t['rows']
                               if row['version_index'] == version) for t in raw['memory_trials']
                          if t['group'] == name and t['method'] == method and t['modality'] == 'python_traced']
                row.append(interval(summarize_values(values), 2**20))
            trajectory_rows.append(row)
    rss_increases = ', '.join(
        f"{name} {pct(group['candidate_rss_ratio'] - 1, True)}"
        for name, group in summary['groups'].items() if group['candidate_rss_ratio'] > 1)
    add(tr('6. Uninstrumented resident memory', '6. 未启用追踪器的驻留内存'), tr(
        f'Each cell is MiB median [minimum, maximum] from {protocol["memory_repetitions"]} fresh '
        f'processes executing the complete {versions}-version trajectory, without warmup or '
        f'tracemalloc. The RSS gate uses only these processes. RSS includes interpreter/imports, '
        f'source maps, transient objects, indexes and graphs; it is not cache-only storage. '
        f'Native high-water units are normalized from bytes on '
        f'[macOS (Apple XNU manual)](https://raw.githubusercontent.com/apple-oss-distributions/xnu/main/bsd/man/man2/getrusage.2) '
        f'and KiB on [Linux (getrusage manual)](https://man7.org/linux/man-pages/man2/getrusage.2.html).\n\n',
        f'每格为 {protocol["memory_repetitions"]} 个新进程执行完整 {versions} 版本轨迹后的 MiB 中位数 '
        f'[最小值，最大值]，不预热、不启用 tracemalloc。RSS 门槛只使用这些进程。RSS 包含解释器/导入、'
        f'源码映射、临时对象、索引与图，不能解释为缓存自身大小。原生高水位单位由 '
        f'[macOS 的字节（Apple XNU 手册）](https://raw.githubusercontent.com/apple-oss-distributions/xnu/main/bsd/man/man2/getrusage.2) '
        f'及 [Linux 的 KiB（getrusage 手册）](https://man7.org/linux/man-pages/man2/getrusage.2.html) 归一化。\n\n')
        + table([tr('Repository', '仓库'), tr('Method', '方法'), 'RSS peak MiB [min,max]'], rss_rows)
        + '\n\n' + tr(
            f'Observed candidate median RSS increases relative to IWCG: {rss_increases or "none"}. '
            f'Passing the memory budget is not a claim of lower memory use.',
            f'相对 IWCG，候选方法 RSS 峰值中位数增加的仓库：{rss_increases or "无"}。'
            f'通过内存预算不等于内存使用下降。'))
    add(tr('7. Separately traced Python allocations', '7. 单独追踪的 Python 分配'), tr(
        'These fresh processes enable tracemalloc before the first source load and are separate '
        'from both timing and RSS-gate processes. Current traced retention is sampled after '
        'releasing returned graphs and collecting garbage, while the session and current source '
        'map remain alive. Peak/current traced bytes describe allocations observed since tracing '
        'started, not all process memory; tracing itself changes costs. '
        '[Python 3.12 tracemalloc documentation](https://docs.python.org/3.12/library/tracemalloc.html).\n\n',
        '此组新进程在首次读取源码前启用 tracemalloc，与计时及 RSS 门槛进程分开。释放返回图并执行 GC 后记录当前'
        '追踪保留量，此时会话与当前源码映射仍存活。追踪峰值/当前字节量只描述启动追踪以来观察到的分配，'
        '不是全部进程内存；追踪本身也改变成本。'
        '[Python 3.12 tracemalloc 文档](https://docs.python.org/3.12/library/tracemalloc.html)。\n\n')
        + table([tr('Repository', '仓库'), tr('Method', '方法'), 'Python peak MiB [min,max]',
                 tr('Final retained MiB [min,max]', '末版保留 MiB [最小,最大]')], traced_rows)
        + '\n\n' + tr('Primary pair, post-GC retention by version (MiB); eight revisions cannot prove '
                       'a long-running memory bound:\n\n',
                       '主比较方法逐版本 GC 后保留量（MiB）；八个版本不能证明长期运行的内存上界：\n\n')
        + table([tr('Repository', '仓库'), tr('Version', '版本'), 'Commit', 'IWCG [min,max]',
                 'IRS [min,max]'], trajectory_rows))

    reuse_rows = []
    for repo in repos:
        name = repo['repository']
        refs = sorted((r for r in raw['cold_reference'] if r['group'] == name),
                      key=lambda row: row['version_index'])
        for method in methods:
            values = summary['groups'][name]['methods'][method]['reused_per_repeat']
            reuse_rows.append([name, METHODS[method], ', '.join(map(str, values)),
                               len(repo['anchors']) * (versions - 1),
                               ', '.join(str(r['complete']) for r in refs)])
    add(tr('8. Reuse and incomplete-output coverage', '8. 复用与不完整输出覆盖'), tr(
        f'{incomplete_pairs}/{cold_pairs} reference graphs have incomplete frontiers. '
        'Reuse counts are saved computations, not newly certified fresh semantics. Complete-graph '
        'counts are shown for every pinned version, once, from uncached references. All methods '
        'must preserve those same counts and canonical frontiers. The timing file stores completeness '
        'and graph digests rather than per-kind frontier histograms; no unrecorded histogram is inferred.\n\n',
        f'{incomplete_pairs}/{cold_pairs} 个参照图含有不完整边界。复用次数表示少做的计算，不表示新认证的语义 fresh。'
        '每个固定版本的完整图数由无跨版本缓存参照给出；'
        '各方法必须保持相同计数及规范边界。计时文件保存完整性计数和图摘要，没有边界类别直方图，'
        '因此不推测未记录的直方图。\n\n')
        + table([tr('Repository', '仓库'), tr('Method', '方法'), tr('Reused in repetitions 1–5', '重复 1–5 的复用数'),
                 tr('Anchors × transitions', '锚点×转换'), tr('Complete graphs in versions 0–7', '版本 0–7 完整图数')], reuse_rows))

    task_source_rows = []
    for case in data['task_manifest']['cases']:
        source = data['task_manifest']['repositories'][case['repository']]['versions']
        task_source_rows.append([
            case['id'], f"{source['before']['tag']} → {source['after']['tag']}",
            f"[{case['test_symbol']}]({case['test_url']})", len(case['invocations'])])
    add(tr('9. Task-conditioned execution witness method', '9. 任务相关执行见证方法'), tr(
        f'The separate task set contains {len(task_rows)} assertion cases from packaging, attrs and '
        f'pluggy, using existing development release pairs. It is not held out. Exact after-version '
        f'upstream function bodies run against both versions, with reviewed imports/arguments and '
        f'fixture adaptations; the full pytest suite/conftest/setup hooks are not executed. '
        f'Original future flags are preserved with dont_inherit=True. Pytest fixtures can change '
        f'setup, scope and parameters, so an extracted body is not the full pytest environment. '
        f'[Official fixture semantics](https://docs.pytest.org/en/stable/how-to/fixtures.html).\n\n'
        f'Each version runs twice traced and twice untraced in separate restricted macOS processes '
        f'({data["task_validation"]["children"]} children). Repeats and per-invocation assertion '
        f'outcomes must agree; {task_summary["trace_outcomes_consistent_cases"]}/{len(task_rows)} '
        f'cases pass that parity check. Imports/fixture setup precede the tracing window. The '
        f'witness is the union of physical package lines executed by the after-version assertions '
        f'across that case’s invocations; before-version outcomes provide change/control context. '
        f'Generated attrs code is counted separately. '
        f'Python tracing is thread-specific; these reviewed single-process callables do not provide '
        f'a general multi-thread execution oracle. '
        f'[Python 3.12 tracing](https://docs.python.org/3.12/library/sys.html#sys.settrace).\n\n'
        f'All methods receive the same pinned source and entrypoint hints. BM25 uses the upstream '
        f'test text plus hints over 20-line windows at exactly the graph’s unique physical-line '
        f'budget. Full source is an unbudgeted upper bound. Old graph lines are all charged as '
        f'supplied context, but receive current-source credit only for exact, unique same-file '
        f'span matches. The score is executed-line recall, not gold-context precision, token cost '
        f'or repair success. {task_summary["before_fail_after_pass"]}/{len(task_rows)} cases fail '
        f'before and pass after; a release-pair difference does not identify one causal patch.',
        f'独立任务集含 packaging、attrs、pluggy 的 {len(task_rows)} 个断言案例，使用已有开发版本对，'
        f'不是留出集。将 after 版上游原始函数体应用到前后两个版本，使用经审查的导入、参数及 fixture 适配设置；'
        f'不执行完整 pytest/conftest/setup 钩子。通过 dont_inherit=True 保留原始 future 标志。'
        f'fixture 会影响准备、作用域和参数，所以提取函数体并不等于完整 pytest 环境。'
        f'[官方 fixture 语义](https://docs.pytest.org/en/stable/how-to/fixtures.html)。\n\n'
        f'每个版本在独立受限 macOS 进程中追踪两次、不追踪两次，共 {data["task_validation"]["children"]} 个子进程。'
        f'重复结果及逐调用断言结果必须一致；{task_summary["trace_outcomes_consistent_cases"]}/{len(task_rows)} '
        f'案例通过追踪/不追踪一致性检查。导入与 fixture 准备先于追踪窗口。见证是 after 版本断言各次调用实际执行的'
        f'包源码物理行并集；before 版结果提供变化或稳定对照信息。attrs 动态生成代码另计。'
        f'Python 追踪属于线程局部机制，这些经审查的进程内调用不提供一般多线程执行 oracle。'
        f'[Python 3.12 追踪文档](https://docs.python.org/3.12/library/sys.html#sys.settrace)。\n\n'
        f'各方法使用相同固定源码和入口提示。BM25 用上游测试文字加提示，对 20 行窗口检索，并严格匹配图的唯一物理行'
        f'预算。完整源码是不限预算的上界。旧图的全部提供行数均计费，只有当前同文件中唯一且完全相同的片段才获得'
        f'当前源码覆盖信用。该指标是执行行召回率，不是金标准上下文精确率、token 成本或修复成功率。'
        f'{task_summary["before_fail_after_pass"]}/{len(task_rows)} 案例前版失败、后版通过；版本对差异不能归因于单个补丁。')
        + '\n\n' + table([tr('Case', '案例'), tr('Before → after release', '前版 → 后版 release'),
                             tr('Original after-version test', '上游后版原始测试'),
                             tr('Invocations per child', '每子进程调用数')], task_source_rows)
        + '\n\n' + tr(
            '[Frozen test/source manifest](../../benchmarks/task_evidence/manifest.json) · '
            '[Task execution and fixture adaptation protocol](../../benchmarks/task_evidence/PROTOCOL.md) · '
            '[Source fetch, isolation preflight and reproduction commands](../../benchmarks/task_evidence/README.md).',
            '[固定测试与源码清单](../../benchmarks/task_evidence/manifest.json) · '
            '[任务执行与 fixture 适配协议](../../benchmarks/task_evidence/PROTOCOL.md) · '
            '[源码获取、隔离预检及复现命令](../../benchmarks/task_evidence/README.md)。'))

    task_case_rows, task_group_rows, audit_rows = [], [], []
    for row in task_rows:
        task_case_rows.append([row['id'], *[
            f"{pct(row['metrics'][method]['recall'])} / {row['metrics'][method]['context_lines']}"
            for method in TASK_METHODS]])
        audit_rows.append([row['id'], f"{row['before_passed']} → {row['after_passed']}",
                           len(row['witness']), row['generated_line_locations'],
                           counters(Counter(row['graph_anchor_states'])), counters(row['graph_frontier']),
                           json.dumps(row['missing_anchors'], sort_keys=True),
                           counters(row['stale_span_states']),
                           json.dumps(row['graph_reuse_validation'], sort_keys=True)])
    for group, values in task_summary['aggregate'].items():
        for method, metric in values['methods'].items():
            task_group_rows.append([group, TASK_METHODS[method], values['cases'],
                                    pct(metric['macro_recall']), f"{metric['mean_context_lines']:.2f}"])
    add(tr('10. Per-case and per-repository task results', '10. 逐案例与逐仓库任务结果'), tr(
        f'Each cell below is recall / supplied physical lines. Graph recall is greater than BM25 '
        f'in {len(graph_better)} cases, lower in {len(graph_worse)}, and equal in {len(graph_tied)}. '
        f'These dependent convenience cases do not support a significance or general superiority '
        f'claim. Lower graph-recall cases: {", ".join(graph_worse) or "none"}.\n\n',
        f'下表每格为召回率 / 提供的物理行数。图召回率在 {len(graph_better)} 个案例高于 BM25，'
        f'{len(graph_worse)} 个较低，{len(graph_tied)} 个相同。这些相关的便利案例不能支持显著性或普遍优越性判断。'
        f'图较低案例：{", ".join(graph_worse) or "无"}。\n\n')
        + tr(
            f'Graph recall is also below the direct-anchor context in '
            f'{", ".join(graph_below_anchors) or "no case"}. At repository level, graph macro recall '
            f'is lower than BM25 for {", ".join(graph_lower_groups) or "no repository"}. '
            f'These observed coverage comparisons do not identify the causal reason.\n\n',
            f'图召回率还在 {", ".join(graph_below_anchors) or "无案例"} 中低于直接锚点上下文。按仓库宏平均，'
            f'{", ".join(graph_lower_groups) or "无仓库"} 的图召回率低于 BM25。'
            f'这些覆盖比较本身不能确定因果原因。\n\n')
        + table([tr('Case', '案例'), *TASK_METHODS.values()], task_case_rows)
        + '\n\n' + table([tr('Group', '组'), tr('Method', '方法'), tr('Cases', '案例数'),
                              tr('Macro recall', '宏平均召回'), tr('Mean supplied lines', '平均提供行数')], task_group_rows))
    add(tr('11. Every recorded task frontier and negative state', '11. 全部已记录任务边界与负面状态'), tr(
        f'{frontier_cases}/{len(task_rows)} current task graphs contain frontiers. Nothing is '
        f'upgraded to fresh merely because it was cached or covers an executed line. Every case’s '
        f'anchor status, frontier-kind count, missing anchors, old-span state and old-graph validation is retained '
        f'below, including before failures and generated-code locations.\n\n',
        f'{frontier_cases}/{len(task_rows)} 个当前任务图含有边界。缓存命中或覆盖已执行行都不会将 unknown 升级为 fresh。'
        f'下表保留每个案例的锚点状态、全部边界类别计数、缺失锚点、旧片段状态和旧图校验结果，包括前版失败及动态生成代码位置。\n\n')
        + table([tr('Case', '案例'), 'Before → after', tr('Witness lines', '见证行'),
                 tr('Generated locations', '生成代码位置'), tr('Anchor states', '锚点状态'),
                 tr('All frontier counts', '全部边界计数'), tr('Missing anchors', '缺失锚点'),
                 tr('Old-span states', '旧片段状态'),
                 tr('Old-graph validation', '旧图校验')], audit_rows))

    old_rows = [r for r in data['old']['rows'] if r['group'].startswith('natural:')
                and r['method'] == 'read_set_certificate' and r['phase'] == 'replay' and r['repetition'] == 1]
    exploratory_rows = [r for r in data['exploratory']['rows'] if
                        r['method'] == 'read_set_any_status' and r['phase'] == 'replay' and r['repetition'] == 1]
    add(tr('12. Historical evidence is not rewritten', '12. 历史证据不改写'), tr(
        f'The earlier complete-only primary experiment met its speed target in '
        f'{data["old_summary"]["natural_repositories_meeting_target"]}/4 development repositories '
        f'and reused {sum(r["reused"] for r in old_rows)}/{sum(r["reused"]+r["rebuilt"] for r in old_rows)} '
        f'natural anchor transitions per repetition. Its failed target remains a negative result. '
        f'The later same-data any-status ablation reused {sum(r["reused"] for r in exploratory_rows)}/'
        f'{sum(r["reused"]+r["rebuilt"] for r in exploratory_rows)} transitions, but was designed after '
        f'that outcome and is exploratory, not a held-out confirmation. Neither table is pooled '
        f'with the new repository holdout. [Historical primary](RESEARCH_REPORT.md) · '
        f'[Exploratory ablation](ABLATION_REPORT.md).\n\n'
        f'The first task pilot was invalidated because forced postponed annotations changed '
        f'upstream test execution semantics and its read isolation was incomplete. Its raw records '
        f'remain preserved, but none of its coverage metrics is used here. The corrected run '
        f'preserves upstream compiler flags, restricts reads, rejects unverified bytecode/native '
        f'imports, validates every case/repeat/line identity, retains partial failures and checks '
        f'traced/untraced outcomes. This is a disclosed same-sample correction, not an independent '
        f'replication or new task holdout. [Invalid-pilot status](../../benchmarks/task_evidence/results/initial/STATUS.md) · '
        f'[Execution amendment](../../benchmarks/task_evidence/EXECUTION_AMENDMENT.md).',
        f'此前仅允许完整图复用的主实验，在 {data["old_summary"]["natural_repositories_meeting_target"]}/4 个开发仓库'
        f'达到时间阈值，每轮自然锚点转换复用 {sum(r["reused"] for r in old_rows)}/'
        f'{sum(r["reused"]+r["rebuilt"] for r in old_rows)}。该失败目标继续作为负结果保留。'
        f'此后同数据 any-status 消融复用 {sum(r["reused"] for r in exploratory_rows)}/'
        f'{sum(r["reused"]+r["rebuilt"] for r in exploratory_rows)} 次转换，但设计发生在主结果之后，'
        f'属于探索性结果，不能作为留出确认。两者都不与新仓库留出数据混合统计。'
        f'[历史主实验](RESEARCH_REPORT.md) · [探索性消融](ABLATION_REPORT.md)。\n\n'
        f'首次任务试运行因强制延迟注解改变上游执行语义，以及读取隔离不完整而失效。原始记录保留，但本报告不使用其'
        f'任何覆盖指标。修正版本保留原始编译标志、限制读取、拒绝未验证字节码/原生模块、校验全部案例/重复/行身份、'
        f'保存中断记录，并核对追踪/不追踪结果。这是公开说明的同样本修正，不是独立复现或新任务留出集。'
        f'[无效试运行状态](../../benchmarks/task_evidence/results/initial/STATUS.md) · '
        f'[执行修订](../../benchmarks/task_evidence/EXECUTION_AMENDMENT.md)。'))

    add(tr('13. Interpretation, limitations and next evidence', '13. 解释、局限与后续证据'), tr(
        ('The narrow combined performance target is met on this fixed sample. ' if overall else
         'The combined performance target is not met on this fixed sample; a broad speedup claim is unsupported. ')
        + f'Per-repository results, source-changing strata, capture cost and observed RSS increases '
        f'remain part of the result. {transitions-changed}/{transitions} source-identical '
        f'transitions favor simple reuse, and short release-centered histories are not representative '
        f'edit streams. Four convenience repositories, fixed top-level anchors and a bounded resolver '
        f'do not establish population effects. Five repeated trajectories describe timing variability, '
        f'not five independent datasets; no confidence/significance claim is made.\n\n'
        f'Task witnesses omit unexecuted alternatives and native/generated behavior outside their '
        f'stated scope. High recall can reflect broad class/module spans and cannot demonstrate '
        f'that a context is minimal or sufficient. The line-matched BM25 budget is not a token or '
        f'retrieval-latency match. Known development projects, release-pair selection and reviewed '
        f'fixture substitutes limit external validity. Memory tests include short-lived overlap '
        f'of old/new state and process overhead; eight revisions cannot prove unbounded-run stability.\n\n'
        f'Further research needs independent human task-context review, additional repository/time '
        f'holdouts, calibrated end-to-end coding tasks against current retrieval/invalidation '
        f'baselines, external reproduction and a separate novelty argument. This report establishes '
        f'an inspectable engineering experiment, not a mature paper, SOTA result or deployed system.',
        ('固定样本上的狭义联合性能目标达到。' if overall else
         '固定样本上的联合性能目标未达到，不能支持宽泛加速宣称。')
        + f'逐仓库结果、源码改变分层、捕获成本及已观察到的 RSS 增加均属于结果。{transitions-changed}/{transitions} 次源码相同转换'
        f'有利于简单复用，围绕 release 的短历史并不代表一般编辑流。四个便利仓库、固定顶层锚点和有界解析器不足以'
        f'推断总体效应。五条重复轨迹只描述时间波动，不是五个独立数据集；本报告不作置信或显著性宣称。\n\n'
        f'任务见证遗漏未执行分支及范围外的原生/生成行为。高召回可能来自宽泛类或模块片段，不能证明上下文最小或充分。'
        f'等行数 BM25 不等于 token 或检索延迟相同。已有开发仓库、版本对选择和经审查的 fixture 替代限制外部有效性。'
        f'内存记录包含新旧状态短时重叠及进程开销；八个版本不能证明无限运行稳定。\n\n'
        f'后续仍需独立人工任务上下文评审、更多仓库/时间留出、对照当前检索与失效方法的端到端编码任务、外部复现和独立'
        f'新颖性论证。本报告提供可检查的工程实验，不是成熟论文、SOTA 结果或已部署系统。'))

    add(tr('14. Related work and official method sources', '14. 相关工作与官方方法来源'), tr(
        'Dependency-hash traces and rebuild decisions are established in '
        '[Mokhov, Mitchell and Peyton Jones, Build Systems à la Carte (2018)]'
        '(https://www.microsoft.com/en-us/research/publication/build-systems-la-carte/). '
        '[Tup ghost nodes](https://gittup.org/tup/manual.html) provide prior treatment of failed '
        'lookups; [Bazel Skyframe](https://bazel.build/reference/skyframe) explains registered '
        'dependencies and incremental evaluation. Our claim is their scoped engineering '
        'application and evaluation, not new memoization or negative-dependency theory.\n\n'
        '[ContextBench v3](https://arxiv.org/abs/2602.05892v3) evaluates task-relevant coding '
        'contexts, whereas this report’s execution witnesses are not human relevance labels. '
        '[When Retrieval Hurts v1](https://arxiv.org/abs/2605.14478v1) studies stale repository '
        'context; stale-context harm is not a newly established phenomenon here. Neither paper’s '
        'model experiments is reproduced. These distinctions are our interpretation, not the '
        'authors’ assessment of this artifact. [Detailed positioning](RELATED_WORK.md). '
        'Official Python 3.12 tracing/tracemalloc and pytest fixture references are cited at the '
        'respective measurement boundaries above.',
        '[Mokhov、Mitchell 与 Peyton Jones 的 Build Systems à la Carte（2018）]'
        '(https://www.microsoft.com/en-us/research/publication/build-systems-la-carte/) 已建立依赖哈希轨迹与重建判断；'
        '[Tup ghost nodes](https://gittup.org/tup/manual.html) 已处理失败查找，'
        '[Bazel Skyframe](https://bazel.build/reference/skyframe) 说明输入登记和增量求值。'
        '本项目主张是有界领域的工程适配与评估，不是新的缓存或负依赖理论。\n\n'
        '[ContextBench v3](https://arxiv.org/abs/2602.05892v3) 评估编码任务相关上下文，而此处执行见证并非人工相关性标签。'
        '[When Retrieval Hurts v1](https://arxiv.org/abs/2605.14478v1) 研究过期仓库上下文，此处不将过期上下文有害包装为新发现。'
        '本报告未复现两篇论文的模型实验。这些区别是本项目的审慎解释，不是论文作者对本项目的评价。'
        '[详细定位](RELATED_WORK.md)。官方 Python 3.12 追踪/tracemalloc 与 pytest fixture 文档已在相应测量边界引用。'))

    environment, provenance = raw['environment'], data['task_provenance']
    ram = (f"{environment['memory_bytes'] / 2**30:.1f} GiB RAM"
           if environment.get('memory_bytes') is not None else tr('RAM not reported', '未记录 RAM'))
    source_rows = [
        ['Holdout run', raw['run_id'], raw['environment']['source_commit']],
        ['Task run', provenance['run_id'], provenance['git_head']],
        ['Holdout protocol SHA256', raw['protocol_sha256'], ''],
        ['Holdout manifest SHA256', raw['manifest_sha256'], ''],
        ['Task manifest SHA256', provenance['manifest_sha256'], ''],
        ['Task amendment SHA256', provenance['protocol_amendment_sha256'], ''],
    ]
    add(tr('15. Provenance and offline regeneration', '15. 出处与离线再生成'), tr(
        f'Holdout environment: Python {environment["python"]}; {environment["system"]}; '
        f'{environment["cpu"]}; {environment["architecture"]}; '
        f'{ram}; one benchmark thread. '
        f'Task environment: Python {provenance["python"]}; {provenance["platform"]}; '
        f'{provenance["machine"]}. Holdout source_dirty={environment["source_dirty"]}; '
        f'task measured_inputs_dirty={provenance["measured_inputs_dirty"]}. Runtime/supporting '
        f'file hashes and actual order remain in raw provenance. The whole-worktree dirty flag '
        f'and measured implementation digests describe different scopes. Pinned input identity '
        f'and saved result consistency are checked again before this report is generated. Offline validation checks record '
        f'consistency and arithmetic, not a new source execution or independent replication.\n\n',
        f'留出环境：Python {environment["python"]}；{environment["system"]}；{environment["cpu"]}；'
        f'{environment["architecture"]}；{ram}；单基准线程。'
        f'任务环境：Python {provenance["python"]}；{provenance["platform"]}；{provenance["machine"]}。'
        f'留出 source_dirty={environment["source_dirty"]}；任务 measured_inputs_dirty='
        f'{provenance["measured_inputs_dirty"]}。运行时/辅助文件哈希及实际顺序保留在原始出处中。全工作树 dirty 标志'
        f'与实测实现文件摘要描述不同范围。再生成报告前再次校验固定输入身份及保存结果的一致性。'
        f'离线校验检查记录一致性和算术，不是新的源码执行或独立复现。\n\n')
        + table([tr('Record', '记录'), tr('Identity', '身份'), 'Commit'], source_rows)
        + f'\n\n[Holdout raw / 留出原始数据](../../{data["holdout_path"]}) · '
        f'[Task raw / 任务原始数据](../../{data["task_path"]}/runs.json) · '
        f'[Task cases / 逐案例](../../{data["task_path"]}/cases.json) · '
        f'[Task provenance / 任务出处](../../{data["task_path"]}/provenance.json).\n\n'
        '```bash\npython scripts/render_maturation_report.py\n'
        'python scripts/render_maturation_report.py --check\n```\n\n'
        + tr('These commands perform offline validation and rendering only. Raw measurement commands '
             'remain in the input artifacts; new executions must use new result paths. Exact '
             'third-party license bytes and source pins are included in the tracked attribution records.',
             '这些命令只进行离线校验与文档生成。原始测量命令保存在输入记录中；新执行必须使用新的结果路径。'
             '精确第三方许可字节及源码固定版本保存在仓库归属记录中。'))
    add(tr('16. Reproduce in a new environment and result path', '16. 在新环境与新结果路径复现'), tr(
        'Run from the repository root in a fresh Python 3.12 environment. Development dependencies '
        'are optional for measurement and needed for the test suite. The public archive fetchers '
        'require curl with normal TLS verification; they use frozen URLs, SHA-256 digests and '
        'byte counts without authentication. Existing verified caches are reusable; changed '
        'archives are rejected. Neither fetching nor extraction executes upstream code.\n\n',
        '在仓库根目录使用新的 Python 3.12 环境。测量不要求开发依赖，运行测试套件时再安装。'
        '公开归档获取器需要使用正常 TLS 校验的 curl，按固定 URL、SHA-256 和字节数获取，不需要认证。'
        '已验证缓存可以复用；不一致归档会被拒绝。获取及解包都不执行上游代码。\n\n')
        + '```bash\npython3.12 -m venv .venv\nsource .venv/bin/activate\n'
        'python -m pip install -e .\n'
        '# Optional integrity-test dependencies / 可选的完整性测试依赖\n'
        'python -m pip install -e ".[dev]"\n```\n\n'
        + tr('The all-suite holdout includes timing plus both memory modalities. Memory measurement '
             'supports macOS/Linux; duration depends on hardware and system load. The prepare step '
             'populates the external cache from the existing frozen manifest. Use a new output '
             'filename, never the preserved primary artifact:\n\n',
             '留出 all-suite 包括计时和两类内存测量。内存测量支持 macOS/Linux；运行时间取决于硬件和系统负载。'
             'prepare 使用现有固定清单填充仓库外缓存。必须使用新输出文件，不能覆盖保留的主结果：\n\n')
        + '```bash\npython scripts/prepare_incremental_holdout.py --cache-dir ../holdout-inputs\n'
        'python scripts/run_incremental_holdout.py run --suite all \\\n'
        '  --cache-dir ../holdout-inputs --output work/NEW_HOLDOUT.json\n'
        'python scripts/run_incremental_holdout.py analyze --output work/NEW_HOLDOUT.json\n```\n\n'
        + tr('The adapted upstream assertion harness requires macOS sandbox-exec and fails closed '
             'when its isolation preflight cannot be enforced. Fetch the six pinned archives, '
             'verify/extract them, and execute into a new result directory:\n\n',
             '适配后的上游断言执行器要求 macOS sandbox-exec，不能落实隔离预检时会拒绝运行。'
             '获取六个固定归档、验证并解包，再执行到新结果目录：\n\n')
        + '```bash\npython scripts/fetch_task_inputs.py --cache ../task-inputs\n'
        'python scripts/run_task_evidence.py --sources ../task-inputs --extract\n'
        'python scripts/run_task_evidence.py --sources ../task-inputs --output work/NEW_TASK\n```\n\n'
        + tr('Both experiment runners retain failed or interrupted attempts; a failure cannot be '
             'published as a completed summary. These are reproduction instructions, not evidence '
             'that a second machine has reproduced the reported measurements.',
             '两个实验执行器均保留失败或中断记录，不能将失败发布成完整成功汇总。这些是复现操作说明，'
             '不表示第二台机器已复现本报告测量。'))
    return '\n\n'.join(sections) + '\n\n' + ('[中文](../zh/MATURATION_REPORT.md)' if lang == 'en'
                                               else '[English](../en/MATURATION_REPORT.md)') + '\n'


def render(holdout_path=DEFAULT_HOLDOUT, task_directory=DEFAULT_TASKS):
    data = validated_data(holdout_path, task_directory)
    return {lang: report(data, lang) for lang in ['en', 'zh']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--holdout', type=Path, default=DEFAULT_HOLDOUT)
    parser.add_argument('--tasks', type=Path, default=DEFAULT_TASKS)
    parser.add_argument('--check', action='store_true', help='verify committed reports without rewriting them')
    args = parser.parse_args()
    rendered = render(args.holdout, args.tasks)
    for lang, content in rendered.items():
        destination = ROOT / f'docs/{lang}/MATURATION_REPORT.md'
        if args.check:
            if not destination.exists() or destination.read_text() != content:
                raise ValueError('generated report differs: ' + destination.relative_to(ROOT).as_posix())
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content)
    print('Validated evidence and ' + ('checked' if args.check else 'rendered') + ' both research reports.')


if __name__ == '__main__':
    main()
