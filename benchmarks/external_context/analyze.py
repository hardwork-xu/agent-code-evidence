"""Recompute pilot tables from every sealed task / 由所有封存任务重算试验表。"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import mean

from .io import sha256, write_new
from .runner import PROTOCOL


def summarize(data: dict, protocol: dict) -> dict:
    tasks = data['tasks']
    expected = {t['instance_id']: t['repo'] for t in protocol['selection']['tasks']}
    if len(tasks) != len(expected) or {t['instance_id']: t['repo'] for t in tasks} != expected:
        raise ValueError('summary must retain all frozen tasks exactly once')
    repos = sorted(set(expected.values()))
    methods, budgets = protocol['methods'], protocol['budgets']
    cells = []
    for method in methods:
        for budget in budgets:
            for repo in repos:
                records = [t for t in tasks if t['repo'] == repo]
                rows = []
                for task in records:
                    scores = [s for s in task['scores']
                              if (s['method'], s['budget']) == (method, budget)]
                    if len(scores) > 1:
                        raise ValueError('duplicate method/budget score')
                    if not scores and task.get('label_status') != 'unsupported_or_invalid_diff':
                        raise ValueError('missing score must have explicit label failure')
                    rows.extend((task['prediction_status'], s) for s in scores)
                cell = {'repo': repo, 'method': method, 'budget': budget,
                        'selected': len(records),
                        'prediction_failures': sum(t['prediction_status'] != 'predicted' for t in records),
                        'label_failures': sum(t.get('label_status') == 'unsupported_or_invalid_diff' for t in records)}
                for kind in ('line', 'file'):
                    evaluable = [s[kind] for _, s in rows if s[kind]['status'] == 'scored']
                    conditional = [s[kind] for state, s in rows
                                   if state == 'predicted' and s[kind]['status'] == 'scored']
                    cell[kind] = {'scorable': len(evaluable), 'no_target': len(rows) - len(evaluable),
                        'ite': {metric: mean(s[metric] for s in evaluable) if evaluable else None
                                for metric in ('precision', 'recall', 'f1')},
                        'successful_prediction_count': len(conditional),
                        'successful_prediction_only': {
                            metric: mean(s[metric] for s in conditional) if conditional else None
                            for metric in ('precision', 'recall', 'f1')}}
                cells.append(cell)
    macro = []
    for method in methods:
        for budget in budgets:
            group = [c for c in cells if c['method'] == method and c['budget'] == budget]
            row = {'method': method, 'budget': budget}
            for kind in ('line', 'file'):
                rows = [c[kind]['ite'] for c in group if c[kind]['ite']['f1'] is not None]
                row[kind] = {'scorable_repositories': len(rows),
                             **{m: mean(r[m] for r in rows) if rows else None
                                for m in ('precision', 'recall', 'f1')}}
            macro.append(row)
    primary = {r['method']: r for r in macro if r['budget'] == protocol['primary_budget']}
    comparisons = []
    for baseline in ('bm25_windows', 'bm25_declarations'):
        deltas = []
        for repo in repos:
            lookup = {c['method']: c for c in cells
                      if c['budget'] == protocol['primary_budget'] and c['repo'] == repo}
            g, b = lookup['graph_expand']['line']['ite'], lookup[baseline]['line']['ite']
            deltas.append({'repo': repo, 'f1_difference': None if g['f1'] is None or b['f1'] is None
                           else g['f1'] - b['f1']})
        g, b = primary['graph_expand']['line'], primary[baseline]['line']
        gain = None if g['f1'] is None or b['f1'] is None else g['f1'] - b['f1']
        recall = None if g['recall'] is None or b['recall'] is None else g['recall'] - b['recall']
        wins = sum(d['f1_difference'] is not None and d['f1_difference'] > 0 for d in deltas)
        comparisons.append({'baseline': baseline, 'per_repo': deltas, 'positive_repos': wins,
                            'macro_f1_difference': gain, 'macro_recall_difference': recall,
                            'numerical_planning_gate': gain is not None and recall is not None
                            and gain >= .03 and recall >= -.02 and wins >= 4})
    failures = Counter(t.get('failure_category', 'none') for t in tasks
                       if t['prediction_status'] != 'predicted' or t.get('label_status'))
    integrity_categories = {'source_integrity', 'memory_monitor_failure', 'worker_failure'}
    integrity_failures = sum(t.get('failure_category') in integrity_categories
                             or t.get('label_status') == 'unsupported_or_invalid_diff'
                             for t in tasks)
    return {'study_id': protocol['study_id'], 'evidence_level': 'external-edit-localization-pilot',
            'selected_tasks': len(tasks), 'repositories': len(repos),
            'prediction_statuses': dict(Counter(t['prediction_status'] for t in tasks)),
            'failure_categories': dict(failures), 'per_repo': cells, 'macro': macro,
            'primary_comparisons': comparisons,
            'integrity_failures': integrity_failures,
            'advance_to_confirmatory': not integrity_failures and all(c['numerical_planning_gate'] for c in comparisons),
            'mature_research_established': False,
            'limits': ['Proxy edit labels are not necessary context.',
                       'Only six repositories with imbalanced samples; no significance claim.',
                       'No model repair run, no external reproduction, no novelty established.',
                       'Failures are conservative zero predictions where labels exist; no-target cases explicitly excluded.']}


def main():
    parser = argparse.ArgumentParser(description='Recompute external pilot / 重算外部试验')
    parser.add_argument('--scores', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = args.scores.read_bytes()
    protocol = json.loads(PROTOCOL.read_text())
    data = json.loads(raw)
    if data['protocol_sha256'] != sha256(PROTOCOL.read_bytes()):
        raise ValueError('protocol checksum mismatch')
    result = summarize(data, protocol)
    result['scores_sha256'] = sha256(raw)
    result['protocol_sha256'] = sha256(PROTOCOL.read_bytes())
    write_new(args.output, result)
    print(json.dumps({k: result[k] for k in ('selected_tasks', 'prediction_statuses',
               'failure_categories', 'primary_comparisons', 'advance_to_confirmatory')}, indent=2))


if __name__ == '__main__':
    main()
