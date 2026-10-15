"""Render the retained known-task observations / 由保留观测生成双语结果表。

This checks the public export before rendering. It does not run upstream code.
先检查公开记录再生成表格，不运行上游程序。
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import tempfile

from .public_check import frozen_utc, load_contract
from .transport import verify


ROOT = Path(__file__).resolve().parents[2]
STATES = {
    'finite_qualified': ('qualified finite labels', '固定标签通过'),
    'no_completed_target_pair': ('no complete pair', '无完整双侧记录'),
    'paired_no_observed_target_calls': ('no observed test calls', '未观测到测试调用'),
    'paired_unqualified_with_calls': ('unqualified with calls', '已调用但未通过验收'),
}


def render(evidence, index_sha, language):
    """Use the same counts and records in both languages / 两种语言共享数字与记录。"""
    zh = language == 'zh'
    counts = evidence['coverage_counts']
    conditions = {c['condition_key']: c for c in evidence['conditions']}
    statuses = Counter(t['status'] for t in evidence['tasks'])
    lines = [
        '# ' + ('已知39项任务的保留观测' if zh else 'Retained observations on39 known tasks'),
        '',
        ('这是已观测开发集的固定回归验收，不是新留出集、生成修复评测或成熟研究成果。'
         if zh else 'This is finite regression qualification on an already observed development set, '
         'not a new holdout, generated-repair evaluation or mature research result.'),
        '',
        f"Snapshot UTC: `{evidence['snapshot_recorded_utc']}`. INDEX SHA256: `{index_sha}`.",
        '',
        ('原分母始终为39项任务、87个F2P标签和5842个P2P标签。标签及重试不是独立任务。'
         if zh else 'The original denominator remains39 tasks,87 F2P labels and5842 P2P labels. '
         'Labels and retries are not independent tasks.'),
        '',
        ('| 指标 | 数量 |' if zh else '| Quantity | Count |'), '|---|---:|',
        f"| {'保留的完整双侧条件' if zh else 'Retained complete pair conditions'} | {counts['complete_pair_conditions']} |",
        f"| {'有双侧记录的不同任务' if zh else 'Distinct tasks with a complete pair record'} | {39-statuses['no_completed_target_pair']}/39 |",
        f"| {'最新条件固定标签通过' if zh else 'Latest conditions qualifying finite labels'} | {counts['latest_qualified_tasks']}/39 |",
        f"| {'保留的逐阶段观测' if zh else 'Retained phase observations'} | {counts['phase_reports']} |",
        f"| {'不完整条件' if zh else 'Incomplete conditions'} | {counts['partial_conditions_with_retained_records']} |",
        '',
        ('最新完整双侧条件按协议冻结时间排序，不能挑选最好结果。完整双侧记录可能包含崩溃、'
         '缺失调用或跳过，不等于断言验证完成。F2P列为真实行为失败→通过数；P2P列为两侧实际通过数。'
         if zh else 'Latest completed pair condition means protocol freeze time, never the best result. A complete pair record '
         'may contain crashes, absent calls or skips; it does not imply completed assertion validation. '
         'F2P counts actual behavioral fail-to-pass observations; P2P counts actual passes in both roles.'),
        '',
        ('| 任务 | F2P | P2P | 最新状态 | Run ID |' if zh else '| Task | F2P | P2P | Latest status | Run ID |'),
        '|---|---:|---:|---|---|',
    ]
    for task in sorted(evidence['tasks'], key=lambda t: t['instance_id']):
        runs = [conditions[k] for k in task['condition_keys']]
        last = max(runs, key=lambda c: (frozen_utc(c['protocol_created_utc']), c['run_id'])) if runs else None
        f2p = last['unit_reproduced'].get('F2P', 0) if last else 0
        p2p = last['unit_reproduced'].get('P2P', 0) if last else 0
        state = STATES[task['status']][int(zh)]
        run_id = task['latest_declared_condition_run_id'] or '—'
        lines.append(f"| `{task['instance_id']}` | {f2p}/{task['original_F2P']} | "
                     f"{p2p}/{task['original_P2P']} | {state} | `{run_id}` |")
    lines += ['',
        ('0个P2P表示未提供保留测试，不代表全面无回归。测试call通过也不保证执行到目标断言；'
         '原测试的提前返回、模拟与结构性弱断言仍保留。逐阶段、逐标签、环境指纹和所有较早条件见公开gzip记录。'
         if zh else 'Zero P2P means no preservation labels were supplied, not comprehensive '
         'non-regression. A test call does not guarantee reaching its intended assertion; original early '
         'returns, mocks and weak structural assertions remain. The public gzip records retain phases, '
         'labels, environment fingerprints and every earlier recorded condition.'), '',
        ('公开检查器重算记录与判据的一致性，不重新执行上游程序，也不独立认证私有原始日志或完整环境。'
         if zh else 'The public checker recomputes record/criterion consistency. It does not rerun '
         'upstream programs or independently authenticate private raw logs or full environments.'), '',
        '[Protocol / 协议](KNOWN_TASK_EXECUTION.md)', '',
    ]
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True, type=Path, help='gzip bundle / gzip记录目录')
    parser.add_argument('--expected-index-sha256', required=True, help='trusted commit digest / 可信提交摘要')
    parser.add_argument('--check', action='store_true', help='check saved tables / 核对已存表格')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='known-task-record-check-') as temporary:
        output = Path(temporary) / 'observations.json'
        verify(args.bundle, args.expected_index_sha256,
               load_contract(Path(__file__).with_name('contract.py')), output)
        raw = output.read_bytes()
        evidence = json.loads(raw)
        evidence_sha = hashlib.sha256(raw).hexdigest()
    for language in ['en', 'zh']:
        target = ROOT / 'docs' / language / 'KNOWN_TASK_EXECUTION_RESULTS.md'
        text = render(evidence, args.expected_index_sha256, language)
        if args.check:
            if not target.exists() or target.read_text() != text:
                raise ValueError('retained result table differs / 保留结果表不一致: ' + str(target))
        else:
            target.write_text(text)
    print(json.dumps({'status': 'passed', 'scope': 'public record consistency and table rendering only',
                      'index_sha256': args.expected_index_sha256,
                      'evidence_sha256': evidence_sha}))


if __name__ == '__main__':
    main()
