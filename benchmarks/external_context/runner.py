"""Frozen, issue-only pilot runner / 冻结的仅问题描述检索试验。

Prediction and label scoring are separate commands. Source is read as data;
upstream imports, tests, installation scripts and model calls never run.
预测与标签评分分开执行；不运行上游代码、测试、安装脚本或模型。
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time
import threading

from .io import archive_texts, canonical, sha256, write_new
from .scoring import edit_targets, score_prediction

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = Path(__file__).with_name('protocol.json')


def now():
    return datetime.now(timezone.utc).isoformat()


def verified_rows(path: Path, protocol: dict) -> dict:
    """Verify raw data first; callers explicitly project allowed columns.

    CSV byte parsing does not imply using label columns for retrieval.
    先校验完整文件；预测调用方只投影允许列，不将标签送入检索子进程。
    """
    if sha256(path.read_bytes()) != protocol['dataset']['sha256']:
        raise ValueError('dataset checksum mismatch')
    csv.field_size_limit(32 * 1024**2)
    with path.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    result = {row['instance_id']: row for row in rows}
    if len(result) != len(rows):
        raise ValueError('duplicate task IDs')
    for task in protocol['selection']['tasks']:
        row = result[task['instance_id']]
        if any(row[k] != task[k] for k in ('repo', 'base_commit')):
            raise ValueError('task metadata differs from freeze')
    return result


def provenance(protocol: dict) -> dict:
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)
    if dirty:
        raise ValueError('experiment requires a clean source commit')
    return {'git_commit': head, 'protocol_sha256': sha256(PROTOCOL.read_bytes()),
            'amendments_sha256': sha256(PROTOCOL.with_name('amendments.json').read_bytes()),
            'dataset_sha256': protocol['dataset']['sha256'],
            'python': platform.python_version(), 'platform': platform.system(),
            'platform_release': platform.release(), 'machine': platform.machine(),
            'cpu_count': os.cpu_count(), 'workers': 1,
            'command': 'python -m benchmarks.external_context.runner predict --dataset DATA --sources SOURCES --output NEW_DIRECTORY'}


def worker(payload: dict) -> dict:
    from contextproof.index import source_lines
    from .retrieval import retrieve_all
    limits = payload['resources']
    memory_mode = 'sampled-rss-250ms' if platform.system() == 'Darwin' else 'address-space-hard-limit'
    if platform.system() != 'Darwin':
        resource.setrlimit(resource.RLIMIT_AS, (limits['max_address_space_bytes'],) * 2)
    started = time.perf_counter()
    texts, source = archive_texts(Path(payload['archive']), payload['archive_sha256'],
                                 max_bytes=limits['max_python_bytes'],
                                 max_files=limits['max_python_files'],
                                 max_file_bytes=limits['max_single_python_bytes'])
    source['source_lengths'] = {p: len(source_lines(s)) for p, s in texts.items()}
    contexts = retrieve_all(texts, payload['issue'], budgets=payload['budgets'])
    expected = {(m, b) for m in json.loads(PROTOCOL.read_text())['methods']
                for b in payload['budgets']}
    if (len(contexts) != len(expected)
            or {(c['method'], c['budget']) for c in contexts} != expected):
        raise ValueError('missing or duplicate method/budget context')
    outputs = []
    for context in contexts:
        # Credit exactly delivered coordinates; never publish issue/code text.
        rendered = context['rendered']
        if len(rendered.encode('utf-8')) != context['consumed']:
            raise ValueError('rendered byte accounting mismatch')
        if context['consumed'] > context['budget']:
            raise ValueError('context exceeds budget')
        blocks = context['blocks']
        if rendered:
            payload_view = json.loads(rendered)
            if payload_view['blocks'] != blocks or payload_view['issue'] != payload['issue']:
                raise ValueError('payload and reported source differ')
        elif blocks:
            raise ValueError('empty payload cannot deliver source')
        lines = {(r['path'], n) for r in blocks
                 for n in range(r['start_line'], r['end_line'] + 1)}
        if len(lines) != sum(r['end_line'] - r['start_line'] + 1 for r in blocks):
            raise ValueError('duplicate physical source line in emitted context')
        for block in blocks:
            source_span = ''.join(source_lines(texts[block['path']])[
                block['start_line'] - 1:block['end_line']])
            if source_span != block['text']:
                raise ValueError('emitted source mismatch')
        outputs.append({'method': context['method'], 'budget': context['budget'],
                        'status': context['status'], 'consumed': context['consumed'],
                        'payload_sha256': sha256(rendered.encode('utf-8')),
                        'blocks': [{k: r[k] for k in ('path', 'start_line', 'end_line')}
                                   for r in blocks],
                        'frontier_count': len(context.get('frontier', [])),
                        'delivered_lines': len(lines)})
    return {'status': 'predicted', 'outputs': outputs, 'source': source,
            'wall_seconds': time.perf_counter() - started, 'memory_limit_mode': memory_mode}


def run_worker(payload: dict, timeout: int) -> tuple[int, bytes, bytes, dict]:
    """Fail closed on monitoring errors / 监控失效时终止试验，显式记录失败。

    macOS RSS is sampled every250ms; transient overshoot is possible. Linux uses
    a hard address-space limit. They are distinct modes, not equivalent bounds.
    macOS采样与Linux地址空间硬限制并不等价，结果记录实际模式。
    """
    darwin = platform.system() == 'Darwin'
    monitor_state = {'mode': 'sampled-rss-250ms' if darwin else 'address-space-hard-limit',
                     'exceeded': False, 'failed': False, 'peak_sampled_rss_bytes': None,
                     'samples': 0}
    if darwin:
        # Verify ps availability before launching an unmonitored worker.
        checked = subprocess.run(['ps', '-o', 'rss=', '-p', str(os.getpid())],
                                 capture_output=True, text=True, timeout=2)
        if checked.returncode or not checked.stdout.strip().isdigit():
            raise ValueError('memory monitor preflight failed')
    process = subprocess.Popen([sys.executable, '-m', 'benchmarks.external_context.runner', 'worker'],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               cwd=ROOT)
    stop = threading.Event()

    def monitor():
        while not stop.wait(.25):
            if process.poll() is not None:
                return
            try:
                observed = subprocess.run(['ps', '-o', 'rss=', '-p', str(process.pid)],
                                          capture_output=True, text=True, timeout=2)
                if process.poll() is not None:
                    return
                if observed.returncode or not observed.stdout.strip().isdigit():
                    raise ValueError('unreadable RSS')
                rss = int(observed.stdout.strip()) * 1024
                monitor_state['samples'] += 1
                monitor_state['peak_sampled_rss_bytes'] = max(
                    rss, monitor_state['peak_sampled_rss_bytes'] or 0)
                if rss > payload['resources']['max_address_space_bytes']:
                    monitor_state['exceeded'] = True
                    process.kill()
                    return
            except (OSError, ValueError, subprocess.TimeoutExpired):
                if process.poll() is None:
                    monitor_state['failed'] = True
                    process.kill()
                return
    watcher = threading.Thread(target=monitor, daemon=True) if darwin else None
    if watcher:
        watcher.start()
    try:
        stdout, stderr = process.communicate(canonical(payload), timeout=timeout)
        return process.returncode, stdout, stderr, monitor_state
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise
    finally:
        stop.set()
        if watcher:
            watcher.join(timeout=3)


def predict(args):
    protocol = json.loads(PROTOCOL.read_text())
    info = provenance(protocol)
    rows = verified_rows(args.dataset, protocol)
    sources = json.loads(args.sources.read_text())
    # Normalized public manifest: keyed task IDs, archive filename and checksum.
    selected = {r['instance_id']: r for r in sources['tasks']}
    if len(selected) != len(sources['tasks']):
        raise ValueError('duplicate source manifest task IDs')
    expected = protocol['selection']['tasks']
    if set(selected) != {r['instance_id'] for r in expected}:
        raise ValueError('source manifest must retain every frozen task')
    args.output.mkdir(parents=True, exist_ok=False)
    write_new(args.output / 'manifest.json', {'run_id': args.output.name,
              'started_at': now(), 'provenance': info,
              'source_manifest_sha256': sha256(args.sources.read_bytes()),
              'tasks': expected})
    predictions = []
    for i, task in enumerate(expected):
        row = rows[task['instance_id']]
        src = selected[task['instance_id']]
        if any(src.get(k) != task[k] for k in ('repo', 'base_commit')):
            raise ValueError('source manifest differs from frozen metadata')
        result = {**task, 'query_sha256': sha256(row['problem_statement'].encode('utf-8')),
                  'archive_sha256': src.get('archive_sha256'), 'started_at': now()}
        if src.get('status') != 'ready':
            result.update(status='input_unavailable', failure_category=src.get('status', 'unknown'))
        else:
            payload = {'issue': row['problem_statement'],
                       'archive': str(args.sources.parent / src['archive']),
                       'archive_sha256': src['archive_sha256'], 'budgets': protocol['budgets'],
                       'resources': protocol['resources']}
            try:
                returncode, stdout, stderr, monitor_state = run_worker(
                    payload, protocol['resources']['per_task_timeout_seconds'])
                result['memory_monitor'] = monitor_state
                if returncode or monitor_state['failed']:
                    # Do not publish local traceback paths or arbitrary source text.
                    category = ('memory_monitor_failure' if monitor_state['failed'] else
                                'memory_limit' if monitor_state['exceeded'] else 'worker_failure')
                    for marker, name in [(b'MemoryError', 'memory_limit'),
                                         (b'source resource limit exceeded', 'source_resource_limit'),
                                         (b'source archive checksum mismatch', 'source_integrity')]:
                        if marker in stderr:
                            category = name
                    result.update(status='failed', failure_category=category,
                                  error_sha256=sha256(stderr), returncode=returncode)
                else:
                    result.update(json.loads(stdout))
            except subprocess.TimeoutExpired:
                result.update(status='failed', failure_category='timeout')
            except ValueError as error:
                if str(error) != 'memory monitor preflight failed':
                    raise
                result.update(status='failed', failure_category='memory_monitor_failure')
        result['finished_at'] = now()
        write_new(args.output / f'prediction-{i:03}.json', result)
        predictions.append(result)
        print(f'{i+1}/{len(expected)} {task["instance_id"]}: {result["status"]}', flush=True)
    seal = {'finished_at': now(), 'tasks': len(predictions),
            'files': {f'prediction-{i:03}.json': sha256((args.output / f'prediction-{i:03}.json').read_bytes())
                      for i in range(len(predictions))},
            'manifest_sha256': sha256((args.output / 'manifest.json').read_bytes())}
    write_new(args.output / 'prediction-seal.json', seal)


def score(args):
    protocol = json.loads(PROTOCOL.read_text())
    dataset = verified_rows(args.dataset, protocol)
    seal_raw = (args.run / 'prediction-seal.json').read_bytes()
    seal = json.loads(seal_raw)
    manifest = json.loads((args.run / 'manifest.json').read_bytes())
    if sha256((args.run / 'manifest.json').read_bytes()) != seal['manifest_sha256']:
        raise ValueError('prediction manifest changed')
    if manifest['provenance']['protocol_sha256'] != sha256(PROTOCOL.read_bytes()):
        raise ValueError('protocol changed after prediction')
    if len(seal['files']) != protocol['selection']['selected_tasks']:
        raise ValueError('incomplete prediction seal')
    records = []
    seen = set()
    for name, digest in sorted(seal['files'].items()):
        raw = (args.run / name).read_bytes()
        if sha256(raw) != digest:
            raise ValueError('prediction changed after sealing')
        prediction = json.loads(raw)
        identity = prediction['instance_id']
        if identity in seen:
            raise ValueError('duplicate predicted task')
        seen.add(identity)
        row = dataset[identity]
        task = next((t for t in protocol['selection']['tasks'] if t['instance_id'] == identity), None)
        if task is None or any(prediction.get(k) != task[k] for k in ('repo', 'base_commit')):
            raise ValueError('prediction metadata differs from frozen task')
        if prediction['status'] == 'predicted':
            outputs = prediction['outputs']
            expected = {(m, b) for m in protocol['methods'] for b in protocol['budgets']}
            if (len(outputs) != len(expected)
                    or {(o['method'], o['budget']) for o in outputs} != expected):
                raise ValueError('missing or duplicate method/budget predictions')
        base = {'instance_id': identity, 'repo': prediction['repo'],
                'prediction_status': prediction['status'],
                'prediction_failure_category': prediction.get('failure_category')}
        patch = row['patch']
        try:
            edit_targets(patch)
        except ValueError as error:
            records.append({**base, 'label_status': 'unsupported_or_invalid_diff',
                            'failure_category': str(error), 'scores': [],
                            'patch_sha256': sha256(patch.encode('utf-8')),
                            'denominator_retained': True})
            continue
        if prediction['status'] != 'predicted':
            scores = [{'method': method, 'budget': budget, 'context_status': 'failed_prediction',
                       'consumed': 0, 'intent_to_evaluate_zero': True,
                       **score_prediction(set(), patch, {})}
                      for method in protocol['methods'] for budget in protocol['budgets']]
            for value in scores:
                value['out_of_corpus_target_lines'] = None
                value['source_diagnostic_status'] = 'unknown_after_prediction_failure'
            records.append({**base, 'failure_category': prediction.get('failure_category'),
                            'patch_sha256': sha256(patch.encode('utf-8')),
                            'scores': scores, 'denominator_retained': True})
            continue
        scores = []
        for output in prediction['outputs']:
            lines = {(b['path'], n) for b in output['blocks']
                     for n in range(b['start_line'], b['end_line'] + 1)}
            scores.append({'method': output['method'], 'budget': output['budget'],
                'context_status': output['status'], 'consumed': output['consumed'],
                **score_prediction(lines, patch, prediction['source']['source_lengths'])})
        records.append({**base, 'patch_sha256': sha256(patch.encode('utf-8')), 'scores': scores})
    if seen != {r['instance_id'] for r in protocol['selection']['tasks']}:
        raise ValueError('prediction task selection changed')
    write_new(args.output, {'study_id': protocol['study_id'], 'scored_at': now(),
              'prediction_seal_sha256': sha256(seal_raw), 'dataset_sha256': protocol['dataset']['sha256'],
              'protocol_sha256': sha256(PROTOCOL.read_bytes()), 'tasks': records})


def main():
    parser = argparse.ArgumentParser(description='Issue-only external localization pilot / 仅问题描述外部定位试验')
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('predict', help='Predict before scoring / 先预测，后评分')
    p.add_argument('--dataset', type=Path, required=True)
    p.add_argument('--sources', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    s = commands.add_parser('score', help='Score sealed predictions / 对已封存预测评分')
    s.add_argument('--dataset', type=Path, required=True)
    s.add_argument('--run', type=Path, required=True)
    s.add_argument('--output', type=Path, required=True)
    commands.add_parser('worker', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.command == 'worker':
        print(json.dumps(worker(json.load(sys.stdin)), ensure_ascii=False, allow_nan=False))
    elif args.command == 'predict':
        predict(args)
    else:
        score(args)


if __name__ == '__main__':
    main()
