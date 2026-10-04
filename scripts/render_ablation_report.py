#!/usr/bin/env python3
"""Render explicit post-result ablation / 明确标记结果后消融的双语报告。"""
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_selective_ablation import analyze  # noqa: E402


def render(source):
    raw = json.loads(source.read_text())
    summary = analyze(raw)
    rows = [r for r in raw['rows'] if r['method'] == 'read_set_any_status'
            and r['repetition'] == 1 and r['phase'] == 'replay']
    reused, total = sum(r['reused'] for r in rows), sum(r['reused'] + r['rebuilt'] for r in rows)
    tables = {}
    for key in ['groups', 'source_changing_groups']:
        lines = ['| Repository | Rebuild ms | Whole-corpus ms | Any-status ms | vs rebuild | vs whole corpus |',
                 '|---|---:|---:|---:|---:|---:|']
        for name, methods in summary[key].items():
            b, w, a = [methods[m]['median_ms'] for m in ['warm_ast_rebuild', 'whole_corpus_guard', 'read_set_any_status']]
            lines.append(f"| {name.removeprefix('natural:')} | {b:.2f} | {w:.2f} | {a:.2f} | {1-a/b:+.1%} | {1-a/w:+.1%} |")
        tables[key] = '\n'.join(lines)
    seed_lines = ['| Repository | Rebuild capture + replay ms | Whole corpus ms | Any status ms |',
                  '|---|---:|---:|---:|']
    for group in raw['expected_groups']:
        values = []
        for method in ['warm_ast_rebuild', 'whole_corpus_guard', 'read_set_any_status']:
            totals = [sum(r['elapsed_ns'] for r in raw['rows'] if r['group'] == group
                          and r['method'] == method and r['repetition'] == rep) / 1e6
                      for rep in range(1, raw['repetitions'] + 1)]
            values.append(statistics.median(totals))
        seed_lines.append(f"| {group.removeprefix('natural:')} | " + ' | '.join(f'{x:.2f}' for x in values) + ' |')
    seed_table = '\n'.join(seed_lines)
    for lang in ['en', 'zh']:
        title = ('Exploratory ablation: preserving unknown cached graphs' if lang == 'en'
                 else '探索性消融：缓存并保留 unknown 图')
        intro = (f'''This experiment was designed **after** the complete-only primary method
reused zero natural graphs. It uses the same frozen data and is not a holdout or
confirmation of the failed primary hypothesis. Only the completeness gate is
removed. Source-read and catalog checks, output provenance and all unknown,
missing or truncated statuses remain. Three methods were rerun contemporaneously,
with one warmup and five complete trajectory repetitions per method.

The candidate reused **{reused}/{total}** natural anchor transitions per repetition.
All sampled graphs remain incomplete. These are saved computations, not newly
certified fresh evidence. Canonical graph outputs match the rebuilt baseline.
Values below are medians in ms; positive percentage is faster, negative is slower.
''' if lang == 'en' else f'''本实验在严格完整性主实验自然复用为零**之后**设计，使用同一固定数据，
不是留出验证，也不把失败主假设改写成成功。仅移除完整性门槛，保留文件
读取集、目录、出处校验及所有 unknown/missing/truncated 状态。三种方法
在同一轮重新测量，每种一次预热、五条完整轨迹重复。

每轮候选策略复用 **{reused}/{total}** 个自然锚点转换。所有所选图仍不完整，
这是少做重复计算，不是新增可认证为 fresh 的证据。规范序列化后的全部图输出与重建一致。
表格为毫秒中位数，正百分比表示更快、负值表示更慢。
''')
        limitation = ('''This is a same-data exploratory mechanism ablation. It does not establish
out-of-sample performance, complete dependency registration in general Python,
semantic safety, task relevance, coding-agent improvement or new memoization theory.
A per-module incremental binding-summary baseline and retained-memory/RSS costs
are unmeasured. Source hashing still touches all supplied text, and read/catalog
invalidation remains coarse. Initial capture is included in the last table, but
process startup and session construction are not. The unchanged primary report
retains its original zero-coverage result and failed utility target.
''' if lang == 'en' else '''这是同数据上的探索性机制消融，不能证明样本外性能、一般Python输入
登记完备性、语义安全、任务相关性、代码Agent收益或新的缓存理论。
逐模块绑定摘要增量基线、驻留内存/RSS尚未测量。仍哈希全部输入，读取集
与目录失效规则仍较粗。末表包含首次捕获，但不包含进程启动与会话构造。
主报告的零覆盖结果和未达效用目标保持原样。
''')
        content = f'''# {title}

{intro}
## {'All transitions' if lang == 'en' else '全部转换'}

{tables['groups']}

## {'Source-changing transitions only' if lang == 'en' else '仅源码改变的转换'}

{tables['source_changing_groups']}

## {'Initial capture plus complete replay' if lang == 'en' else '首次捕获加完整回放'}

{seed_table}

{limitation}

- run_id: `{raw['run_id']}`
- source commit: `{raw['environment']['source_commit']}`
- protocol SHA256: `{raw['protocol_sha256']}`
- [Raw / 原始数据](../../{source.relative_to(ROOT).as_posix()})
- [Protocol / 协议](../../benchmarks/selective_reuse/ablation-protocol.json)
- [Primary report / 主报告](RESEARCH_REPORT.md)

```bash
python scripts/run_selective_ablation.py --output work/NEW_ABLATION.json
python scripts/render_ablation_report.py work/NEW_ABLATION.json
```

Python {raw['environment']['python']}; {raw['environment']['cpu']}; one benchmark thread.
'''
        (ROOT / 'docs' / lang / 'ABLATION_REPORT.md').write_text(content)
    print(raw['run_id'], f'reused {reused}/{total}', 'bilingual exploratory reports rendered')


if __name__ == '__main__':
    render(Path(sys.argv[1]).resolve())
