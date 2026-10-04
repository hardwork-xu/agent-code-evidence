#!/usr/bin/env python3
"""Trace reviewed upstream tests, then score task-conditioned source witnesses.

No model, downloads, installation, setup scripts, or performance measurements.
Execution requires macOS Seatbelt; source extraction and unit tests are portable.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from uuid import uuid4

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / 'src')]
from benchmarks.task_evidence.suite import (  # noqa: E402
    aggregate, anchors_for, digest, lexical_lines, physical_lines, record_lines, safe_extract,
    score, stale_current_lines, verified_texts, write_json,
)
from contextproof.graph import build_graph, compare_graphs  # noqa: E402

BENCH = REPO / 'benchmarks/task_evidence'


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def source_provenance(manifest_bytes: bytes) -> dict:
    files = [Path(__file__).resolve(), BENCH / 'worker.py', BENCH / 'suite.py',
             *sorted((REPO / 'src/contextproof').glob('*.py'))]
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
    tracked_dirty = bool(subprocess.check_output(
        ['git', 'status', '--porcelain', '--untracked-files=no'], cwd=REPO, text=True))
    scoped_paths = [str(p.relative_to(REPO)) for p in files]
    scoped_paths += ['benchmarks/task_evidence/manifest.json', 'benchmarks/task_evidence/PROTOCOL.md',
                     'benchmarks/task_evidence/EXECUTION_AMENDMENT.md']
    scoped_dirty = bool(subprocess.check_output(
        ['git', 'status', '--porcelain', '--untracked-files=all', '--', *scoped_paths],
        cwd=REPO, text=True))
    return {'manifest_sha256': digest(manifest_bytes),
            'protocol_amendment_sha256': digest((BENCH / 'EXECUTION_AMENDMENT.md').read_bytes()),
            'python': platform.python_version(),
            'platform': platform.system(), 'machine': platform.machine(), 'git_head': head,
            'tracked_worktree_dirty': tracked_dirty, 'measured_inputs_dirty': scoped_dirty,
            'implementation_sha256': {str(p.relative_to(REPO)): digest(p.read_bytes()) for p in files}}


def profile(allowed: list[Path]) -> str:
    paths = [*allowed, Path(sys.prefix), Path(sys.base_prefix), Path('/System'),
             Path('/usr'), Path('/dev')]
    permits = ' '.join(f'(subpath {json.dumps(str(p.resolve()))})' for p in paths)
    ancestors = sorted({str(parent) for root in paths for parent in root.resolve().parents})
    metadata = ' '.join(f'(literal {json.dumps(path)})' for path in ancestors)
    return ('(version 1) (allow default) (deny network*) (deny process-fork) '
            '(deny file-write*) '
            '(deny file-read*) '
            f'(allow file-read* {permits}) '
            # macOS loader needs root-directory data; realpath needs ancestor metadata.
            '(allow file-read-data (literal "/")) '
            f'(allow file-read-metadata {metadata})')


def sanitize_result(value, allowed: list[Path]):
    """Keep all task-owned absolute paths out of retained failure payloads."""
    if isinstance(value, str):
        for root in sorted({str(REPO), *[str(p.resolve()) for p in allowed]},
                           key=len, reverse=True):
            value = value.replace(root, '<task-path>')
        return value
    if isinstance(value, list):
        return [sanitize_result(item, allowed) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_result(item, allowed) for key, item in value.items()}
    return value


def isolated(script: Path, args: list[str], allowed: list[Path]) -> dict:
    if platform.system() != 'Darwin' or not Path('/usr/bin/sandbox-exec').exists():
        raise RuntimeError('macOS Seatbelt required; no unrestricted fallback')
    command = ['/usr/bin/sandbox-exec', '-p', profile(allowed),
               str(Path(sys.executable).resolve()), '-I', '-B', str(script), *args]
    try:
        completed = subprocess.run(command, text=True, capture_output=True,
                                   cwd=script.parent, timeout=30,
                                   env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
    except subprocess.TimeoutExpired:
        return {'harness_error': 'TimeoutExpired'}
    if completed.returncode:
        return {'harness_error': 'WorkerExit', 'returncode': completed.returncode,
                'stderr': sanitize_result(completed.stderr, allowed)}
    try:
        return sanitize_result(json.loads(completed.stdout), allowed)
    except ValueError:
        return {'harness_error': 'InvalidWorkerJSON'}


def preflight(work: Path) -> dict:
    with tempfile.TemporaryDirectory(dir=work) as directory:
        scratch = Path(directory)
        sentinel = work / 'task-evidence-outside-sentinel'
        if sentinel.exists():
            raise RuntimeError('preflight sentinel already exists')
        sentinel.write_text('outside sandbox allowlist')
        external = tempfile.NamedTemporaryFile(prefix='task-evidence-sentinel-',
                                               dir='/private/tmp', delete=False)
        external.write(b'controlled outside allowlist')
        external.close()
        outside_tmp = Path(external.name)
        probe = scratch / 'probe.py'
        probe.write_text('import json, os, pathlib, socket\n'
                         f'outside = pathlib.Path({str(sentinel)!r})\n'
                         f'outside_tmp = pathlib.Path({str(outside_tmp)!r})\n'
                         'operations = {"read": outside.read_text, '
                         '"tmp_read": outside_tmp.read_text, '
                         '"write": lambda: outside.write_text("bad"), '
                         '"inside_write": lambda: pathlib.Path("bad").write_text("bad"), '
                         '"network": lambda: socket.socket().connect(("127.0.0.1", 9)), '
                         '"fork": os.fork}\n'
                         'result = {}\n'
                         'for name, action in operations.items():\n'
                         '    try: action(); result[name] = "ALLOWED"\n'
                         '    except PermissionError: result[name] = "denied"\n'
                         'print(json.dumps(result))\n')
        try:
            result = isolated(probe, [], [scratch])
        finally:
            sentinel.unlink()
            outside_tmp.unlink()
        if len(result) != 6 or set(result.values()) != {'denied'}:
            raise RuntimeError('sandbox preflight did not deny all six operations')
        return result


def execute(manifest: dict, sources: Path, scratch: Path,
            progress_path: Path | None = None) -> list[dict]:
    rows = []
    completed_children = 0
    for case in manifest['cases']:
        tests = sources / case['repository'] / 'after'
        if digest((tests / case['test_path']).read_bytes()) != case['test_sha256']:
            raise ValueError('upstream test file checksum mismatch')
        row = {'id': case['id'], 'repository': case['repository'], 'runs': {}, 'untraced_runs': {}}
        rows.append(row)
        for key, trace_enabled in [('runs', True), ('untraced_runs', False)]:
            for state in ['before', 'after']:
                root = sources / case['repository'] / state
                payload = scratch / 'payload.json'
                write_json(payload, {'root': str(root), 'test_root': str(tests), 'case': case,
                                     'trace_enabled': trace_enabled})
                row[key][state] = []
                for _ in range(2):
                    row[key][state].append(isolated(BENCH / 'worker.py', [str(payload)],
                                                    [BENCH, root, tests, scratch]))
                    completed_children += 1
                    if progress_path is not None:
                        write_json(progress_path, {
                            'stage': 'execution', 'completed_children': completed_children,
                            'expected_children': 8 * len(manifest['cases']), 'runs': rows})
    return rows


def validate_runs(manifest: dict, runs: list[dict], corpora: dict, *,
                  require_controls: bool = True, expected_trace: bool = True) -> None:
    """Reject missing/reordered executions, forged identities, and invalid traces."""
    cases = manifest['cases']
    if not cases or len(runs) != len(cases):
        raise ValueError('execution case count mismatch')
    if len({row['id'] for row in runs}) != len(runs):
        raise ValueError('duplicate execution case IDs')
    if require_controls:
        controls = [{'id': row.get('id'), 'repository': row.get('repository'),
                     'runs': row.get('untraced_runs', {})} for row in runs]
        validate_runs(manifest, controls, corpora, require_controls=False, expected_trace=False)
    for case, row in zip(cases, runs):
        if row.get('id') != case['id'] or row.get('repository') != case['repository']:
            raise ValueError('execution case identity/order mismatch')
        if set(row.get('runs', {})) != {'before', 'after'}:
            raise ValueError('execution states must be before and after')
        for state, repeats in row['runs'].items():
            if len(repeats) != 2:
                raise ValueError('exactly two execution repeats required')
            texts = corpora[(case['repository'], state)]
            for run in repeats:
                if 'harness_error' in run:
                    continue  # Kept as an ineligible failure, never a task outcome.
                if run.get('trace_enabled') is not expected_trace:
                    raise ValueError('worker trace mode mismatch')
                if run.get('case_id') != case['id']:
                    raise ValueError('worker case identity mismatch')
                invocations = run.get('invocations', [])
                if len(invocations) != len(case['invocations']):
                    raise ValueError('invocation count mismatch')
                for expected, actual in zip(case['invocations'], invocations):
                    if actual.get('invocation') != expected:
                        raise ValueError('invocation identity/order mismatch')
                    if (type(actual.get('passed')) is not bool
                            or (actual.get('failure') is None) != actual['passed']):
                        raise ValueError('contradictory assertion outcome')
                    lines = actual.get('lines', [])
                    if not expected_trace and (lines or actual.get('generated_lines')):
                        raise ValueError('untraced control contains trace records')
                    seen = set()
                    for item in lines:
                        if (not isinstance(item, list) or len(item) != 2
                                or not isinstance(item[0], str) or type(item[1]) is not int
                                or item[0] not in texts
                                or not 1 <= item[1] <= (texts[item[0]] if type(texts[item[0]]) is int
                                                        else len(physical_lines(texts[item[0]])))):
                            raise ValueError('witness line outside verified source')
                        if tuple(item) in seen:
                            raise ValueError('duplicate witness line')
                        seen.add(tuple(item))
                    for item in actual.get('generated_lines', []):
                        if (not isinstance(item, list) or len(item) != 2
                                or not isinstance(item[0], str)
                                or not item[0].startswith('<attrs generated ')
                                or type(item[1]) is not int or item[1] < 1):
                            raise ValueError('invalid generated line record')
                if (type(run.get('passed')) is not bool
                        or run['passed'] != all(i['passed'] for i in invocations)):
                    raise ValueError('contradictory aggregate assertion outcome')


def outcome_signature(run: dict):
    if 'harness_error' in run:
        return None
    return [{'invocation': row['invocation'], 'passed': row['passed'], 'failure': row['failure']}
            for row in run['invocations']]


def outcomes_match(traced: dict, untraced: dict) -> bool:
    signature = outcome_signature(traced)
    return signature is not None and signature == outcome_signature(untraced)


def evaluate(manifest: dict, sources: Path, runs: list[dict], corpora: dict) -> list[dict]:
    validate_runs(manifest, runs, corpora)
    output = []
    for case, execution in zip(manifest['cases'], runs):
        repo = case['repository']
        before, after = (corpora[(repo, state)] for state in ['before', 'after'])
        state_runs = execution['runs']
        controls = execution['untraced_runs']
        deterministic = all(group[s][0] == group[s][1] for group in [state_runs, controls]
                            for s in ['before', 'after'])
        trace_consistent = all(outcomes_match(state_runs[s][0], controls[s][0])
                               for s in ['before', 'after'])
        current_run = state_runs['after'][0]
        witness = {tuple(line) for invocation in current_run.get('invocations', [])
                   for line in invocation['lines']}
        generated = {tuple(line) for invocation in current_run.get('invocations', [])
                     for line in invocation['generated_lines']}
        eligible = (deterministic and trace_consistent and current_run.get('passed') is True and bool(witness)
                    and all('harness_error' not in state_runs[s][0] for s in ['before', 'after']))
        current_anchors, missing_current = anchors_for(after, case['anchors'])
        old_anchors, missing_old = anchors_for(before, case['anchors'])
        graphs = {}
        for state, texts, anchors in [('before', before, old_anchors), ('after', after, current_anchors)]:
            graphs[state] = build_graph(texts, f'{repo}-{state}', anchors,
                                       **manifest['graph_policy']) if anchors else None
        current_graph, old_graph = graphs['after'], graphs['before']
        current_records = list(current_graph['nodes'].values()) if current_graph else []
        old_records = list(old_graph['nodes'].values()) if old_graph else []
        current_lines = record_lines(current_records)
        old_credit, old_states = stale_current_lines(old_records, after)
        test_lines = physical_lines((sources / repo / 'after' / case['test_path']).read_bytes().decode('utf-8'))
        query = ''.join(test_lines[case['test_start'] - 1:case['test_end']]) + json.dumps(case['anchors'])
        contexts = {'fresh_full_source': {(p, n + 1) for p, text in after.items()
                                          for n, _ in enumerate(physical_lines(text))},
                    'fresh_anchors': record_lines(current_anchors),
                    'fresh_graph': current_lines,
                    'lexical_matched_lines': lexical_lines(after, query, len(current_lines)),
                    'stale_graph_current_bytes': old_credit}
        validation = compare_graphs(
            old_graph, build_graph(after, f'{repo}-after', old_anchors,
                                   **manifest['graph_policy'])) if old_graph else None
        if validation:
            validation = {key: validation[key] for key in ['status', 'fresh']}
        row = {'id': case['id'], 'repository': repo, 'eligible': eligible,
               'deterministic': deterministic, 'trace_outcomes_consistent': trace_consistent, 'before_passed': state_runs['before'][0].get('passed'),
               'after_passed': current_run.get('passed'), 'generated_line_locations': len(generated),
               'witness': [list(x) for x in sorted(witness)],
               'metrics': {name: score(context, witness) for name, context in contexts.items()},
               'missing_anchors': {'before': missing_old, 'after': missing_current},
               'stale_span_states': old_states, 'stale_context_lines': len(record_lines(old_records)),
               'graph_anchor_states': [a['status'] for a in current_graph['anchors']] if current_graph else [],
               'graph_frontier': dict(Counter(x['kind'] for x in current_graph['frontier'])) if current_graph else {},
               'graph_reuse_validation': validation}
        # Old bytes remain supplied context even when none receive current-source credit.
        stale_metric = row['metrics']['stale_graph_current_bytes']
        stale_metric['credited_current_source_lines'] = stale_metric['context_lines']
        stale_metric['context_lines'] = row['stale_context_lines']
        stale_metric['execution_density'] = (stale_metric['covered_witness_lines'] / row['stale_context_lines']
                                             if row['stale_context_lines'] else None)
        output.append(row)
    return output


def verify_inputs_unchanged(provenance: dict, manifest: dict, sources: Path) -> None:
    """A successful run must retain the exact inputs that were recorded at start."""
    for relative, expected in provenance['implementation_sha256'].items():
        if digest((REPO / relative).read_bytes()) != expected:
            raise ValueError('implementation changed during task execution')
    if digest((BENCH / 'manifest.json').read_bytes()) != provenance['manifest_sha256']:
        raise ValueError('manifest changed during task execution')
    if digest((BENCH / 'EXECUTION_AMENDMENT.md').read_bytes()) != provenance['protocol_amendment_sha256']:
        raise ValueError('execution amendment changed during task execution')
    if digest((BENCH / 'PROTOCOL.md').read_bytes()) != manifest['protocol_sha256']:
        raise ValueError('protocol changed during task execution')
    for repo, data in manifest['repositories'].items():
        for state, pin in data['versions'].items():
            if digest((sources / f'{repo}-{state}.tar.gz').read_bytes()) != pin['archive_sha256']:
                raise ValueError('archive changed during task execution')
            verified_texts(sources / repo / state, pin)


def _offline_aggregate(rows: list[dict], stored: dict) -> dict:
    """Accept exact stable/legacy reduction results, never an approximate range.

    Python 3.12 changed float sum(). Preserve original result bytes and the
    measured writer; only this offline reader recognizes both reductions.
    仅离线校验接受两种明确求和结果；原始数据不改写，也不采用近似容差。
    """
    expected = aggregate(rows)
    valid = [row for row in rows if row['eligible']]
    for group, summary in expected.items():
        subset = [row for row in valid if group == 'all' or row['repository'] == group]
        for method, metric in summary['methods'].items():
            values = [row['metrics'][method]['recall'] for row in subset]
            sequential = 0.0
            for value in values:
                sequential += value
            alternatives = {math.fsum(values) / len(values), sequential / len(values)}
            recorded = stored[group]['methods'][method]['macro_recall']
            if type(recorded) is not float or recorded not in alternatives:
                raise ValueError('summary macro recall differs from exact stable/legacy reductions')
            metric['macro_recall'] = recorded
    return expected


def validate_result_bundle(directory: Path) -> dict:
    """Offline report integrity only; it does not rerun tests or authenticate source bytes."""
    directory = Path(directory)
    manifest_bytes = (BENCH / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    provenance = json.loads((directory / 'provenance.json').read_text())
    if provenance.get('manifest_sha256') != digest(manifest_bytes):
        raise ValueError('result manifest identity mismatch')
    if provenance.get('protocol_amendment_sha256') != digest((BENCH / 'EXECUTION_AMENDMENT.md').read_bytes()):
        raise ValueError('result execution amendment identity mismatch')
    if (not provenance.get('run_id') or not provenance.get('started_at_utc')
            or not provenance.get('finished_at_utc') or not provenance.get('command')
            or provenance.get('inputs_unchanged_at_finish') is not True
            or type(provenance.get('tracked_worktree_dirty')) is not bool
            or type(provenance.get('measured_inputs_dirty')) is not bool
            or len(provenance.get('git_head', '')) != 40):
        raise ValueError('result provenance is incomplete')
    for relative, expected in provenance.get('implementation_sha256', {}).items():
        if (Path(relative).is_absolute() or '..' in Path(relative).parts
                or not isinstance(expected, str) or len(expected) != 64):
            raise ValueError('invalid implementation provenance record')
    if not {'scripts/run_task_evidence.py', 'benchmarks/task_evidence/worker.py',
            'benchmarks/task_evidence/suite.py'} <= set(provenance.get('implementation_sha256', {})):
        raise ValueError('missing benchmark implementation hashes')
    status = json.loads((directory / 'status.json').read_text())
    if status != {'status': 'completed', 'stage': 'complete',
                  'completed_children': 8 * len(manifest['cases'])}:
        raise ValueError('result bundle is not a completed successful execution')
    counts = provenance.get('source_line_counts', {})
    corpus_counts = {}
    if set(counts) != set(manifest['repositories']):
        raise ValueError('recorded source repository catalog mismatch')
    for repo, data in manifest['repositories'].items():
        if set(counts[repo]) != {'before', 'after'}:
            raise ValueError('recorded source snapshot catalog mismatch')
        for state, pin in data['versions'].items():
            values = counts[repo][state]
            if (set(values) != set(pin['source_files'])
                    or any(type(n) is not int or n < 0 for n in values.values())):
                raise ValueError('recorded source line catalog mismatch')
            corpus_counts[(repo, state)] = values
    runs = json.loads((directory / 'runs.json').read_text())
    validate_runs(manifest, runs, corpus_counts)
    progress = json.loads((directory / 'progress.json').read_text())
    expected_children = 8 * len(manifest['cases'])
    if progress != {'stage': 'execution', 'completed_children': expected_children,
                    'expected_children': expected_children, 'runs': runs}:
        raise ValueError('final progress and raw execution record disagree')
    sandbox = json.loads((directory / 'sandbox.json').read_text())
    if sandbox != {key: 'denied' for key in ['read', 'tmp_read', 'write', 'inside_write', 'network', 'fork']}:
        raise ValueError('sandbox preflight does not match the six required checks')
    rows = json.loads((directory / 'cases.json').read_text())
    if len(rows) != len(manifest['cases']):
        raise ValueError('scored case count mismatch')
    methods = {'fresh_full_source', 'fresh_anchors', 'fresh_graph',
               'lexical_matched_lines', 'stale_graph_current_bytes'}
    for case, run, row in zip(manifest['cases'], runs, rows):
        traced, controls = run['runs'], run['untraced_runs']
        if row['id'] != case['id'] or row['repository'] != case['repository']:
            raise ValueError('scored case identity/order mismatch')
        deterministic = all(group[state][0] == group[state][1] for group in [traced, controls]
                            for state in ['before', 'after'])
        consistent = all(outcomes_match(traced[state][0], controls[state][0])
                         for state in ['before', 'after'])
        witness = {tuple(line) for inv in traced['after'][0].get('invocations', []) for line in inv['lines']}
        eligible = (deterministic and consistent and traced['after'][0].get('passed') is True
                    and bool(witness))
        if (row['deterministic'] != deterministic or row['trace_outcomes_consistent'] != consistent
                or row['eligible'] != eligible
                or row['before_passed'] != traced['before'][0].get('passed')
                or row['after_passed'] != traced['after'][0].get('passed')
                or row['witness'] != [list(x) for x in sorted(witness)]):
            raise ValueError('scored outcome/witness differs from raw execution')
        if set(row['metrics']) != methods:
            raise ValueError('result method catalog mismatch')
        for metric in row['metrics'].values():
            total, covered = metric['context_lines'], metric['covered_witness_lines']
            if (type(total) is not int or type(covered) is not int or total < 0
                    or not 0 <= covered <= min(total, len(witness))
                    or metric['witness_lines'] != len(witness)
                    or metric['recall'] != (covered / len(witness) if witness else None)
                    or metric['execution_density'] != (covered / total if total else None)):
                raise ValueError('result metric arithmetic mismatch')
        if row['metrics']['fresh_graph']['context_lines'] != row['metrics']['lexical_matched_lines']['context_lines']:
            raise ValueError('lexical and graph line budgets differ')
        if row['metrics']['stale_graph_current_bytes']['context_lines'] != row['stale_context_lines']:
            raise ValueError('stale supplied context accounting mismatch')
        full = row['metrics']['fresh_full_source']
        if (full['context_lines'] != sum(corpus_counts[(case['repository'], 'after')].values())
                or full['covered_witness_lines'] != len(witness)):
            raise ValueError('full-source upper bound mismatch')
    summary = json.loads((directory / 'summary.json').read_text())
    expected = {'cases': len(rows), 'eligible_cases': sum(r['eligible'] for r in rows),
                'excluded_cases': [r['id'] for r in rows if not r['eligible']],
                'before_fail_after_pass': sum(r['before_passed'] is False and r['after_passed'] is True for r in rows),
                'trace_outcomes_consistent_cases': sum(r['trace_outcomes_consistent'] for r in rows),
                'aggregate': _offline_aggregate(rows, summary['aggregate']),
                'no_model_or_repair_score': True}
    if summary != expected or expected['eligible_cases'] != len(rows):
        raise ValueError('summary disagrees with eligible per-case evidence')
    return {'cases': len(rows), 'children': expected_children,
            'validation': 'offline report consistency; source execution not rerun'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--extract', action='store_true', help='only verify and extract supplied archives')
    args = parser.parse_args()
    manifest_bytes = (BENCH / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    if digest((BENCH / 'PROTOCOL.md').read_bytes()) != manifest['protocol_sha256']:
        raise ValueError('frozen protocol bytes changed')
    sources = args.sources.resolve()
    corpora = {}
    for name, repository in manifest['repositories'].items():
        for state, pin in repository['versions'].items():
            archive = sources / f'{name}-{state}.tar.gz'
            if digest(archive.read_bytes()) != pin['archive_sha256']:
                raise ValueError('upstream archive checksum mismatch')
            root = sources / name / state
            if args.extract and not root.exists():
                safe_extract(archive, root, pin['archive_sha256'])
            corpora[(name, state)] = verified_texts(root, pin)
    if args.extract:
        print('verified six source snapshots')
        return 0
    if args.output is None or args.output.exists():
        raise ValueError('supply a new output directory; existing runs are never overwritten')
    args.output.mkdir(parents=True)
    stage = 'provenance'
    provenance = None
    started_at = utc_now()
    try:
        write_json(args.output / 'status.json', {'status': 'running', 'stage': stage})
        provenance = source_provenance(manifest_bytes)
        provenance.update(run_id=str(uuid4()), started_at_utc=started_at,
                          command=[sys.executable.rsplit('/', 1)[-1], 'scripts/run_task_evidence.py',
                                   '--sources', '<verified-source-cache>', '--output', '<new-run-output>'],
                          command_path_policy='actual arguments with local paths replaced by portable placeholders',
                          hash_seed_policy='not fixed: Python -I ignores PYTHONHASHSEED; repeat equality is checked',
                          inputs_unchanged_at_finish=False)
        provenance['source_line_counts'] = {
            repo: {state: {path: len(physical_lines(text)) for path, text in corpora[(repo, state)].items()}
                   for state in ['before', 'after']} for repo in manifest['repositories']}
        write_json(args.output / 'provenance.json', provenance)
        with tempfile.TemporaryDirectory(prefix='execution-', dir=sources) as directory:
            scratch = Path(directory)
            stage = 'sandbox_preflight'
            write_json(args.output / 'status.json', {'status': 'running', 'stage': stage})
            checks = preflight(sources)
            write_json(args.output / 'sandbox.json', checks)
            stage = 'execution'
            write_json(args.output / 'status.json', {'status': 'running', 'stage': stage})
            runs = execute(manifest, sources, scratch, args.output / 'progress.json')
            write_json(args.output / 'runs.json', runs)
        stage = 'evaluation'
        write_json(args.output / 'status.json', {'status': 'running', 'stage': stage})
        rows = evaluate(manifest, sources, runs, corpora)
        write_json(args.output / 'cases.json', rows)
        summary = {'cases': len(rows), 'eligible_cases': sum(r['eligible'] for r in rows),
                   'excluded_cases': [r['id'] for r in rows if not r['eligible']],
                   'before_fail_after_pass': sum(r['before_passed'] is False and r['after_passed'] is True for r in rows),
                   'trace_outcomes_consistent_cases': sum(r['trace_outcomes_consistent'] for r in rows),
                   'aggregate': aggregate(rows), 'no_model_or_repair_score': True}
        stage = 'final_input_integrity'
        write_json(args.output / 'status.json', {'status': 'running', 'stage': stage})
        verify_inputs_unchanged(provenance, manifest, sources)
        provenance.update(finished_at_utc=utc_now(), inputs_unchanged_at_finish=True)
        write_json(args.output / 'provenance.json', provenance)
        write_json(args.output / 'summary.json', summary)
        successful = all(r['eligible'] for r in rows)
        write_json(args.output / 'status.json', {
            'status': 'completed' if successful else 'completed_with_case_failures',
            'stage': 'complete', 'completed_children': 8 * len(rows)})
        print(json.dumps(summary, indent=2))
        return 0 if successful else 1
    except BaseException as exc:
        if provenance is not None:
            provenance['finished_at_utc'] = utc_now()
            write_json(args.output / 'provenance.json', provenance)
        write_json(args.output / 'status.json', {
            'status': 'failed', 'stage': stage,
            'error': sanitize_result({'type': type(exc).__name__, 'message': str(exc)},
                                     [sources, args.output.resolve()])})
        raise



if __name__ == '__main__':
    raise SystemExit(main())
