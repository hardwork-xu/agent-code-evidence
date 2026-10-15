#!/usr/bin/env python3
"""Render bilingual reports from complete raw evidence / 由原始证据生成双语报告。"""
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_selective_reuse import summarize  # noqa: E402


def table(groups, changed=False):
    lines = ['| Repository | Rebuild ms | Whole-corpus ms | Read-set ms | Read-set reduction vs rebuild | vs whole corpus |',
             '|---|---:|---:|---:|---:|---:|']
    for name, methods in groups.items():
        if not name.startswith('natural:'):
            continue
        base = methods['warm_ast_rebuild']['median_ms']
        whole = methods['whole_corpus_guard']['median_ms']
        cert = methods['read_set_certificate']['median_ms']
        lines.append(f"| {name.removeprefix('natural:')} | {base:.2f} | {whole:.2f} | {cert:.2f} | {1-cert/base:+.1%} | {1-cert/whole:+.1%} |")
    return '\n'.join(lines)


def render(source):
    raw = json.loads(source.read_text())
    summary = summarize(raw)
    natural = [r for r in raw['rows'] if r['group'].startswith('natural:') and r['method'] == 'read_set_certificate' and r['repetition'] == 1 and r['phase'] == 'replay']
    changes = sum(r['source_changed'] for r in natural)
    eligible = sum(r['reused'] for r in natural)
    targets = sum(r['reused'] + r['rebuilt'] for r in natural)
    total_graphs = sum(len(r['graphs']) for r in raw['rows'])
    manifest = json.loads((ROOT / 'benchmarks/selective_reuse/natural-manifest.json').read_text())
    count_unique = sum(len({json.dumps(v['files'], sort_keys=True) for v in repo['versions']}) for repo in manifest['repositories'])
    target = summary['utility_target_met']
    environment = raw['environment']
    t_all, t_changed = table(summary['groups']), table(summary['source_changing_groups'])
    pergroup = []
    for name in sorted({r['group'] for r in raw['rows'] if r['group'].startswith('natural:')}):
        rows = [r for r in raw['rows'] if r['group'] == name and r['phase'] == 'capture' and r['method'] == 'read_set_certificate']
        pergroup.append(f"| {name.removeprefix('natural:')} | {statistics.median(r['elapsed_ns'] for r in rows)/1e6:.2f} |")
    captures = '\n'.join(['| Repository | Initial capture median ms |','|---|---:|',*pergroup])
    source_link = '../../' + source.relative_to(ROOT).as_posix()
    common = f"""
- run_id: `{raw['run_id']}`
- source commit: `{environment['source_commit']}`
- protocol SHA256: `{raw['protocol_sha256']}`
- manifest SHA256: `{raw['natural_manifest_sha256']}`
- Python {environment['python']}, {environment['cpu']}, {environment['architecture']}, RAM {environment['memory_bytes']//(1024**3)} GiB; one benchmark thread.
- [Raw data / 原始数据]({source_link}); [protocol / 协议](../../benchmarks/selective_reuse/protocol.json); [pins / 版本](../../benchmarks/selective_reuse/natural-manifest.json).
"""
    en = f"""# Source-read certificates for evolving code evidence: an experimental report

**Status: research draft, not submission-ready or peer reviewed.** This report
separates a resolver correction, a reproducible incremental-computation
experiment, and the evidence still missing for a mature research claim.

## Abstract

We investigate selective reuse of bounded Python source-evidence graphs. The
artifact corrects a class-global rebinding failure and records negative lookup
inputs that are absent from visible graph nodes. A fixed developmental corpus
contains 72 authored instances across 24 templates; 63 are inside the declared
static contract. Twelve previous false-fresh decisions, representing four
templates, become explicit unknowns. Nine runtime-effect cases remain outside
the contract. A paired replay covers four new repositories, six revisions each,
96 unique function identities, and three synthetic corpus sizes. Across
{total_graphs} emitted graphs, matched methods produce zero graph-byte
mismatches. The predeclared utility target is **{'met' if target else 'not met'}**.
These observations establish neither general Python semantic soundness nor
better coding-agent task performance.

## 1. Question and scope

Can complete static evidence be reused across revisions at lower total measured
cost while exactly preserving a full rebuild's bounded output? Source identity,
context relevance, semantic behavior and task success are distinct outcomes.
This is an engineering adaptation of established dependency traces, not a new
general incremental algorithm. Prior model runs found graph, fresh-source and
BM25 conditions tied at 24/25 tasks; those historical results are not rerun or
combined with the new timing table.

## 2. Mechanism and independent checks

A `GraphSession` retains anchors, policy, parsed source and read dependencies.
Only complete graphs qualify for selective reuse. All source paths and all
consulted file bytes must agree; otherwise the full resolver runs. Candidate
package files inspected before submodule fallback are tracked even when absent
from the resulting graph. [Design and correctness argument](SELECTIVE_REUSE.md).

The independent oracle labels were authored separately from the resolver and
checked by executing only the synthetic fixture programs. This is model-assisted
development validation, not independent human annotation or a holdout. There
are 21 scoped templates and three out-of-scope runtime-effect templates. Numeric
variants must not be interpreted as independent samples or a natural error rate.
[Version-2/version-3 matrix](../../benchmarks/selective_reuse/results/v2-v3-matrix.json).

## 3. Method

The protocol, methods and success threshold were fixed locally before primary
measurement; this was **not public preregistration**. Four convenience-sampled
Python projects absent from the previous natural corpus were pinned by latest
release (Pyflakes used the recorded tag fallback). Six first-parent commits per
project yielded {count_unique} distinct filtered source snapshots. SHA-ranked
sampling selected at most 24 top-level function identities from each oldest
version, without selecting on graph completeness. Overloads are deduplicated
as anchor identities but remain in source to preserve ambiguity.

The initial invocation was rejected before timing because overload identities
were duplicated; the original manifest, failure record and explicit protocol
amendment remain. No source commits were replaced and no performance target was
changed. [Preflight record](../../benchmarks/selective_reuse/results/preflight-20261004.json).

Each method shares an indexed corpus per revision and a warm AST cache across
revisions. We rotate whole method trajectories, perform one warmup and five
recorded repetitions, and run benchmarks sequentially. Total times include local
archive reads, UTF-8 decoding, checksum validation, hashing, checking, graph
copying/sealing and fallback. Downloads, correctness comparison and output JSON
serialization are separate. Initial capture is shown separately; it excludes
process startup and session construction. Background OS activity is uncontrolled.

There are 20 natural transitions: {changes} change filtered source and
{20-changes} retain identical source. They are all retained. Graphs, transitions
and repeated trials are dependent; four repositories do not support broad
population or significance claims. Min/max and individual observations are in
raw data. Metadata, complete pairing, interruption and non-overwrite checks
reject incomplete or inconsistent artifacts before summarization.

## 4. Results

Values are medians of the sum of five transitions in each repetition, in ms.
Positive reduction means faster; negative means slower. The utility target was
at least 20% lower time than the shared-index rebuild on at least three of four
repositories, with no graph mismatch. **{summary['natural_repositories_meeting_target']}/4 meet that threshold.**

{t_all}

Source-changing transitions only (same frozen inputs; no resampling):

{t_changed}

All 24 natural revision instances (20 distinct source snapshots) had zero complete sampled graphs. That is a coverage
limitation of this resolver and this sampling frame, not evidence that natural
programs are unsafe. Selective reuse retained {eligible}/{targets} natural anchor-transition graphs
per repetition. This is a replay count, not evidence of semantic safety. A
whole-corpus equality guard can retain incomplete graphs without changing their
unknown status; the selective policy deliberately rebuilds them. Therefore a
comparison only against full rebuild would conceal a strong simple alternative.

{captures}

All three synthetic sizes (10, 100, 1000 modules) include unrelated file edits,
referenced file edits and catalog additions. Raw data retain adverse fallback
cases, initialization and all five repetitions; synthetic timing is not a
natural-workload frequency estimate.

## 5. Provenance correction

Exact third-party license texts are retained and checked offline. A separate scripted source-identity audit of 71 original source files verified 1309 distributed excerpts:
748 byte matches, 544 matches after presentation whitespace, and 17 historical
noncontiguous excerpts whose declared contiguous line spans were inaccurate.
The 17 cases are explicitly indexed; historical raw outputs are unchanged.
This is a remaining historical citation limitation, not a source-span success.
[Verification](../../third_party/source-verification.json) ·
[17 corrections](../../third_party/noncontiguous-excerpts.json).

## 6. Interpretation and maturity gates

{'The narrow timing target is met on this sample; independent task evidence is still required.' if target else 'The primary timing hypothesis fails its predeclared target. The artifact remains useful for falsifying an optimization claim, but the results do not justify a general selective-reuse speedup claim.'}
At this primary experiment's cutoff, the remaining research requirements were
a defensible contribution beyond the established
incremental-computation mechanism, task-conditioned context labels independent
of this resolver, repository/time-disjoint natural validation, and end-to-end
coding-task evidence with fresh retrieval and simple invalidation baselines.
Independent human review and external replication have not occurred here.
An incremental per-module binding-summary baseline and retained-memory/RSS
measurements were absent from this experiment; its comparisons remain limited to
these three methods. Later work is separately reported in
[the follow-up study](MATURATION_REPORT.md), without replacing these results.
No acceptance, publication, SOTA, production deployment or model-quality gain
is claimed. This draft is a technical research record, not a completed paper.

## 7. Related work and reproduction

Dependency-hash traces are established in Mokhov, Mitchell and Peyton Jones,
[Build Systems à la Carte (2018)](https://www.microsoft.com/en-us/research/wp-content/uploads/2018/03/build-systems.pdf).
[Tup ghost nodes](https://gittup.org/tup/manual.html) and
[Bazel Skyframe](https://bazel.build/reference/skyframe) establish the importance
of negative and complete dependencies. [ContextBench v3](https://arxiv.org/abs/2602.05892v3)
concerns task-relevant contexts; [When Retrieval Hurts v1](https://arxiv.org/abs/2605.14478v1)
studies stale-context harm. Our adaptation does not establish novelty over these
principles or reproduce their model experiments. [Detailed positioning](RELATED_WORK.md).

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python scripts/check_attribution.py
python scripts/run_selective_reuse.py prepare
python scripts/run_selective_reuse.py run --suite all
python scripts/run_selective_reuse.py analyze --output PATH_TO_NEW_RUN_JSON
python scripts/render_selective_report.py benchmarks/selective_reuse/results/primary-20261004.json
```

The archived command is a portable reproduction command; local cache placement
is intentionally excluded. Runtime code and runner hashes are recorded. The
measured tree included uncommitted documentation/attribution work, while the
listed implementation files and runner were committed and content-hashed.
{common}
"""
    zh = f"""# 演进代码证据的读取集复用：实验研究报告

**状态：研究初稿，尚不具备投稿成熟度，也未经过同行评审。** 本报告分别
记录解析器修复、真实增量实验和成熟研究结论仍缺少的证据。

## 摘要与研究问题

问题是：在保持同一有界 Python 解析器输出的前提下，跨版本复用完整静态
证据，能否降低实际总开销？本实现修复类体 global 重绑定，并跟踪图节点
没有体现的负查找依赖。自写开发语料有 24 模板、72 实例；63 个在契约内，
旧版 12 个 false-fresh（四模板）变为显式 unknown；九个运行时副作用例
仍在保证范围外。新实验覆盖四个仓库、各六个固定提交、96 个去重函数锚点
及三种合成规模，{total_graphs} 个图输出中配对比较无逐字节不一致。
预先声明的效用目标**{'达到' if target else '未达到'}**。这不证明一般语义安全或模型任务收益。

## 实现、贡献与独立验证

`GraphSession` 固定锚点与策略，缓存解析结果和读取依赖。仅完整图可选择性
复用，完整路径目录和全部已咨询文件必须一致，否则完整重建。子模块回退
前检查的包文件即使没有成为图节点，也加入读取集。[设计与条件正确性论证](SELECTIVE_REUSE.md)。

这是已有依赖追踪思想的领域适配，不是通用新算法。源码身份、相关性、语义
行为和任务成功必须分别验证。历史模型实验中，图、新源码和 BM25 同为
24/25；本轮没有重跑或把它们混入新表格。

独立合成标签在解析器之外定义，并通过实际执行自写夹具检查；这是模型辅助
开发验证，不是人工专家标注或留出集。21 个契约内模板、三个契约外模板的
数值变体相互关联，不能当作自然总体错误率。
[旧新版矩阵](../../benchmarks/selective_reuse/results/v2-v3-matrix.json)。

## 实验协议

协议、方法和阈值在主要测量前本地固定，**不是公开预注册**。四个便利抽样
项目此前未进入自然语料，按最新 release 固定版本；Pyflakes 没有 release，
按明确记录的规则回退到 tag。每库六个相邻 first-parent 提交，共有
{count_unique} 种不同的过滤后源码快照。最旧版本中按路径/符号哈希选最多
24 个顶层函数身份，不按图是否完整挑样本。重载身份去重，原始重复定义仍
保留在语料内，解析歧义不会被删除。

首次启动在计时前被重复重载锚点预检拦下；保留初始清单、失败记录及明确
修订。未替换源码提交、未更换性能目标。
[失败记录](../../benchmarks/selective_reuse/results/preflight-20261004.json)。

三种方法均在每版本共享已索引语料、跨版本共享 AST 缓存。整条版本轨迹的
方法顺序轮换，一次预热、五次记录，性能实验串行运行。总时间含本地归档
读取、UTF-8 解码、校验、哈希、复用检查、图复制/封装与回退。网络下载、
结果一致性检查和 JSON 写出单独处理。初次捕获另列，未计进程启动和会话
构造；操作系统背景活动未控制。

20 次自然转换中，{changes} 次改变过滤后源码，{20-changes} 次源码完全相同；
全部保留并分层报告。图、版本转换和重复试验相关，四个仓库不足以推断总体
显著性。逐次记录与 min/max 均保留。结果校验会拒绝不完整配对、失败、中断
或跨重复输入/输出漂移；输出文件不覆盖旧记录。

## 真实结果

表格为每轮五次转换耗时之和的中位数，单位毫秒；正百分比表示加快，负值
表示变慢。预设目标是相对共享索引的重建基线，至少三个仓库降低 20%，且
图无不一致。实际 **{summary['natural_repositories_meeting_target']}/4 达到阈值**。

{t_all}

仅保留源码实际改变的转换重新汇总（同一冻结样本，没有重采样）：

{t_changed}

24 个自然版本出现（20 种唯一源码快照）中，被选图的完整数量全部为零。这反映当前解析器和采样范围
的覆盖局限，不是说自然程序不安全。每轮选择性策略复用 {eligible}/{targets} 个自然锚点转换图。这不是语义安全
数量。全语料相同的简单策略可保留不完整图及其 unknown 状态，选择性模式
则重建，因此只和重建比较会隐去更强的简单替代方案。

{captures}

10、100、1000 模块的合成实验均有无关文件改动、被引用文件改动和目录新增。
原始数据保留不利回退、初次捕获及全部五轮，不把合成负载解释为自然分布。

## 来源勘误

已补齐并离线核对第三方许可原文。单独脚本核对 71 个原文件中的 1309 处已分发
摘录：748 字节完全一致、544 仅有呈现空白差异，17 处历史非连续摘录误标
连续行范围。17 项均单列定位勘误，不修改历史原始输出，也不冒称连续出处
全部正确。[核验数据](../../third_party/source-verification.json) ·
[17 项勘误](../../third_party/noncontiguous-excerpts.json)。

## 结论与成熟度边界

{'该样本达到狭窄的计时目标，但仍不能推出任务收益。' if target else '主要计时假设未达到预设目标。这个可复核的否定结果有价值，但不能据此宣传普遍加速。'}
截至本主实验结束时，仍缺少：超出现有增量思想的明确贡献、独立于本解析器的任务上下文
标注、按仓库/时间隔离的自然验证，以及与新检索和简单失效基线的端到端
代码任务对照。尚未发生独立人工复核、外部复现、同行接收或论文发表。
本实验当时未实现逐模块绑定摘要的增量基线，未测缓存驻留内存/RSS，比较仅限三个已测方法。
后续工作见[独立后续报告](MATURATION_REPORT.md)，不会替换本次结果。
这份初稿是技术研究记录，不是已经完成的论文，不宣称 SOTA、生产部署或
模型质量提升。

## 文献与复现

[Build Systems à la Carte (2018)](https://www.microsoft.com/en-us/research/wp-content/uploads/2018/03/build-systems.pdf)
已有依赖哈希追踪；[Tup](https://gittup.org/tup/manual.html) 与
[Skyframe](https://bazel.build/reference/skyframe) 已强调负依赖及完整输入登记。
[ContextBench v3](https://arxiv.org/abs/2602.05892v3) 关注任务相关上下文；
[When Retrieval Hurts v1](https://arxiv.org/abs/2605.14478v1) 研究过时上下文的危害。
本轮没有复现它们的模型实验。[详细差异与一手来源](RELATED_WORK.md)。

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python scripts/check_attribution.py
python scripts/run_selective_reuse.py prepare
python scripts/run_selective_reuse.py run --suite all
python scripts/run_selective_reuse.py analyze --output PATH_TO_NEW_RUN_JSON
python scripts/render_selective_report.py benchmarks/selective_reuse/results/primary-20261004.json
```

原始数据的命令是去掉本机缓存位置的可移植复现命令；源码与 runner 的哈希
另行固定。测量时文档/归属补充尚未提交，但列出的运行时源码及 runner 已
提交并记录哈希。
{common}
"""
    for language, content in [('en', en), ('zh', zh)]:
        path = ROOT / 'docs' / language / 'RESEARCH_REPORT.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    print(raw['run_id'], 'reports rendered from verified raw data')


if __name__ == '__main__':
    render(Path(sys.argv[1]).resolve())
