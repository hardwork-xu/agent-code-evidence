#!/usr/bin/env python3
"""Paired held-out replay and isolated memory / 留出回放及独立进程内存测量。

No analyzed upstream code is executed. Memory profiles are separate from timing.
不执行被分析的上游代码；内存剖析不进入普通计时结果。
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gc
import json
from pathlib import Path, PurePosixPath
import resource
import statistics
import subprocess
import sys
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))
from contextproof.dependencies import _Corpus  # noqa: E402
from contextproof.graph import canonical_graph_bytes, build_graph  # noqa: E402
from contextproof.reuse import GraphSession  # noqa: E402
from scripts import prepare_incremental_holdout as corpus  # noqa: E402
from scripts import run_selective_reuse as base  # noqa: E402

DATA = ROOT / 'benchmarks/incremental_holdout'
MODALITIES = ('rss', 'python_traced')


def stamp():
    return datetime.now(timezone.utc).isoformat()


def load_inputs():
    protocol = json.loads((DATA / 'protocol.json').read_text())
    manifest = json.loads((DATA / 'manifest.json').read_text())
    corpus.validate_manifest(manifest, protocol)
    return protocol, manifest


def source_provenance():
    """Bind workers to measured code and inputs / 绑定子进程源码及输入版本。"""
    return {'implementation_files': {
        p.relative_to(ROOT).as_posix(): base.digest(p.read_bytes())
        for p in sorted((ROOT / 'src/contextproof').glob('*.py'))},
        'runner_sha256': base.digest(Path(__file__).read_bytes()),
        'supporting_scripts': {name: base.digest((ROOT / name).read_bytes()) for name in
            ('scripts/run_selective_reuse.py', 'scripts/prepare_incremental_holdout.py')},
        'protocol_sha256': base.digest((DATA / 'protocol.json').read_bytes()),
        'manifest_sha256': base.digest((DATA / 'manifest.json').read_bytes())}


def _hex(value, length):
    return isinstance(value, str) and len(value) == length and all(c in '0123456789abcdef' for c in value)


def validate_provenance(result, protocol, manifest):
    provenance = result.get('provenance', {})
    for key in ('runner_sha256', 'protocol_sha256', 'manifest_sha256'):
        if not _hex(provenance.get(key), 64) or result.get(key) != provenance[key]:
            raise ValueError('missing or inconsistent source provenance')
    if (result.get('protocol_snapshot') != protocol
            or provenance['protocol_sha256'] != manifest['protocol_sha256']):
        raise ValueError('frozen protocol differs from run')
    # The input object and file are both supplied by the pinned study. Later
    # analysis may use different runtime code, but not a different input file.
    protocol_bytes = (DATA / 'protocol.json').read_bytes()
    manifest_bytes = (DATA / 'manifest.json').read_bytes()
    if (provenance['protocol_sha256'] != base.digest(protocol_bytes)
            or provenance['manifest_sha256'] != base.digest(manifest_bytes)
            or json.loads(protocol_bytes) != protocol
            or json.loads(manifest_bytes) != manifest):
        raise ValueError('saved run uses different source/protocol pins')
    files = provenance.get('implementation_files')
    required = {'src/contextproof/' + p for p in
                ('reuse.py', 'dependencies.py', 'graph.py', 'static_scope.py', 'module_cache.py')}
    if not isinstance(files, dict) or not required <= files.keys():
        raise ValueError('runtime source hashes missing')
    for name, value in files.items():
        path = PurePosixPath(name)
        if (path.parts[:2] != ('src', 'contextproof') or len(path.parts) != 3
                or path.suffix != '.py' or path.as_posix() != name or not _hex(value, 64)):
            raise ValueError('invalid runtime source hash/path')
    environment = result.get('environment', {})
    if (not _hex(environment.get('source_commit'), 40)
            or environment.get('implementation_files') != files):
        raise ValueError('runtime environment and measured source disagree')
    supporting = provenance.get('supporting_scripts', {})
    if (set(supporting) != {'scripts/run_selective_reuse.py', 'scripts/prepare_incremental_holdout.py'}
            or any(not _hex(value, 64) for value in supporting.values())):
        raise ValueError('executed loader/timing support hashes missing')


def anchors(repo, first):
    selected = base.anchors_for(first)
    if [{k: v for k, v in a.items() if k != 'text'} for a in selected] != repo['anchors']:
        raise ValueError('frozen anchor selection drift / 固定锚点漂移')
    return selected


def cold_reference(repo, cache, protocol):
    """No cross-version AST/module cache / 不使用跨版本 AST 或摘要缓存的参照。

    Share one newly parsed/indexed corpus among anchors of the same snapshot.
    每个快照重新解析与索引，仅在同一快照的锚点之间共享临时语料。
    """
    selected = None
    for index, version in enumerate(repo['versions']):
        texts = corpus.source_loader(cache, repo, version)()
        if selected is None:
            selected = anchors(repo, texts)
        fresh = _Corpus.from_texts(texts)
        graphs = [build_graph(texts, version['commit'], [a], _corpus=fresh,
                              **protocol['resolver_policy']) for a in selected]
        yield {'group': repo['repository'], 'version_index': index,
               'snapshot_id': version['commit'],
               'graphs': [base.digest(canonical_graph_bytes(g)) for g in graphs],
               'complete': sum(not g['frontier'] for g in graphs)}


def rss_bytes(value, system=None):
    """Normalize ru_maxrss units / 区分 macOS 字节与 Linux KiB。"""
    system = sys.platform if system is None else system
    if system not in ('darwin', 'linux'):
        raise ValueError('RSS profiling supports Linux/macOS only / 仅支持 Linux/macOS')
    return int(value * (1 if system == 'darwin' else 1024))


def memory_worker(repo, method, modality, cache, protocol):
    """One process, one full trajectory / 单进程只测一条完整轨迹，无预热。

    RSS runs never enable tracemalloc. Traced retention keeps the session and
    current input alive, releases the returned graph, and collects garbage.
    RSS 不启用追踪器；追踪保留量含会话及当前输入，释放输出图并执行 GC。
    """
    if modality not in MODALITIES or method not in protocol['methods']:
        raise ValueError('unknown memory configuration')
    if tracemalloc.is_tracing():
        raise ValueError('memory worker must start without active tracing')
    provenance = source_provenance()
    loaders = [corpus.source_loader(cache, repo, v) for v in repo['versions']]
    if modality == 'python_traced':
        tracemalloc.start()
    # Hydrate the fixed anchor spans from the first measured load. No AST anchor
    # reselection or extra unmeasured archive-load warmup is necessary.
    # 首次实测读入补齐固定锚点文本；不额外重选锚点或预热归档。
    initial = loaders[0]()
    selected = [{**a, 'text': ''.join(initial[a['path']].splitlines(keepends=True)[
        a['start_line'] - 1:a['end_line']])} for a in repo['anchors']]
    session = GraphSession(selected, mode=method, **protocol['resolver_policy'])
    rows = []
    for index, (load, version) in enumerate(zip(loaders, repo['versions'])):
        texts = initial if index == 0 else load()
        if index == 0:
            del initial
        result = session.update(texts, version['commit'])
        hashes = [base.digest(canonical_graph_bytes(g)) for g in result.graphs]
        counts = result.reused, result.rebuilt, sum(not g['frontier'] for g in result.graphs)
        del result
        gc.collect()
        current, peak = tracemalloc.get_traced_memory() if modality == 'python_traced' else (None, None)
        native_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rows.append({'version_index': index, 'snapshot_id': version['commit'],
                     'graphs': hashes, 'reused': counts[0], 'rebuilt': counts[1],
                     'complete': counts[2], 'rss_peak_bytes': rss_bytes(native_peak),
                     'rss_native_value': native_peak,
                     'rss_native_unit': 'bytes' if sys.platform == 'darwin' else 'KiB',
                     'python_retained_bytes': current, 'python_peak_bytes': peak})
    if modality == 'python_traced':
        tracemalloc.stop()
    if source_provenance() != provenance:
        raise ValueError('worker inputs or implementation changed during execution')
    return {'group': repo['repository'], 'method': method, 'modality': modality,
            'provenance': provenance,
            'status': 'passed', 'pid': __import__('os').getpid(), 'rows': rows,
            'rss_peak_bytes': max(r['rss_peak_bytes'] for r in rows),
            'python_peak_bytes': max(r['python_peak_bytes'] for r in rows)
                if modality == 'python_traced' else None}


def _integer(value, *, minimum=0):
    return type(value) is int and value >= minimum


def _validate_graphs(row, expected_count):
    values = row.get('graphs')
    if (not isinstance(values, list) or len(values) != expected_count
            or any(not isinstance(s, str) or len(s) != 64
                   or any(c not in '0123456789abcdef' for c in s) for s in values)):
        raise ValueError('invalid graph digests')
    if (any(not _integer(row.get(k)) for k in ('reused', 'rebuilt', 'complete'))
            or row['reused'] + row['rebuilt'] != expected_count
            or row['complete'] > expected_count):
        raise ValueError('inconsistent graph counts')


def validate(result, protocol, manifest):
    """Reject incomplete grids and mismatches / 拒绝残缺配对与结果漂移。"""
    if result.get('status') != 'passed':
        raise ValueError('only a completed passed run may be analyzed')
    if result.get('suite') not in ('timing', 'memory', 'all'):
        raise ValueError('invalid suite')
    validate_provenance(result, protocol, manifest)
    methods = protocol['methods']
    repos = {r['repository']: r for r in manifest['repositories']}
    if result.get('methods') != methods or result.get('expected_groups') != list(repos):
        raise ValueError('study group/method drift')
    versions = protocol['natural']['versions']
    invariants = {}
    expected_reference = {(r, v) for r in repos for v in range(versions)}
    for row in result.get('cold_reference', []):
        key = row['group'], row['version_index']
        if key not in expected_reference or key in invariants:
            raise ValueError('unknown or duplicate uncached reference')
        repo = repos[row['group']]
        if (row['snapshot_id'] != repo['versions'][row['version_index']]['commit']
                or not isinstance(row['graphs'], list) or len(row['graphs']) != len(repo['anchors'])
                or any(not _hex(g, 64) for g in row['graphs'])
                or not _integer(row['complete']) or row['complete'] > len(repo['anchors'])):
            raise ValueError('invalid uncached reference output')
        invariants[key] = row['graphs'], row['complete']
    if set(invariants) != expected_reference:
        raise ValueError('incomplete uncached reference grid')

    def check_output(row, name):
        version = row['version_index']
        repo = repos[name]
        _validate_graphs(row, len(repo['anchors']))
        if row['snapshot_id'] != repo['versions'][version]['commit']:
            raise ValueError('snapshot pin mismatch')
        key = name, version
        invariant = row['graphs'], row['complete']
        if key in invariants and invariants[key] != invariant:
            raise ValueError('canonical graph or completeness mismatch')
        invariants[key] = invariant

    if result['suite'] in ('timing', 'all'):
        expected = {(r, rep, m, v) for r in repos for rep in range(1, protocol['repetitions'] + 1)
                    for m in methods for v in range(versions)}
        found = set()
        for row in result['timing_rows']:
            name = row['group'].removeprefix('natural:')
            if row['group'] != 'natural:' + name:
                raise ValueError('timing group must use the exact natural prefix')
            key = name, row['repetition'], row['method'], row['version_index']
            if key not in expected or key in found:
                raise ValueError('unknown or duplicate timing row')
            found.add(key)
            if row['status'] != 'passed' or row['equivalence'] is not True:
                raise ValueError('failed timing measurement')
            if (any(not _integer(row[k]) for k in ('elapsed_ns', 'load_ns', 'graph_ns'))
                    or row['elapsed_ns'] != row['load_ns'] + row['graph_ns']):
                raise ValueError('invalid timing boundary')
            version = row['version_index']
            if row['phase'] != ('capture' if version == 0 else 'replay'):
                raise ValueError('invalid capture/replay phase')
            now = repos[name]['versions'][version]['files']
            before = repos[name]['versions'][version - 1]['files'] if version else now
            changed = sorted(p for p in before.keys() | now.keys() if before.get(p) != now.get(p))
            if (row['changed_paths'] != changed or row['source_changed'] != bool(changed)
                    or row['catalog_changed'] != (before.keys() != now.keys())):
                raise ValueError('source-change metadata differs from pinned hashes')
            if (not isinstance(row['reasons'], dict)
                    or any(not _integer(n) for n in row['reasons'].values())
                    or sum(row['reasons'].values()) != len(repos[name]['anchors'])):
                raise ValueError('invalid decision audit counts')
            check_output(row, name)
        if found != expected:
            raise ValueError('incomplete timing grid')
    elif result['timing_rows']:
        raise ValueError('unexpected timing rows')

    if result['suite'] in ('memory', 'all'):
        expected = {(r, rep, m, kind) for r in repos
                    for rep in range(1, protocol['memory_repetitions'] + 1)
                    for m in methods for kind in MODALITIES}
        found = set()
        for trial in result['memory_trials']:
            if trial.get('provenance') != result['provenance']:
                raise ValueError('worker input/source provenance mismatch')
            key = trial['group'], trial['repetition'], trial['method'], trial['modality']
            if key not in expected or key in found or trial['status'] != 'passed':
                raise ValueError('unknown, duplicate or failed memory trial')
            found.add(key)
            if [r['version_index'] for r in trial['rows']] != list(range(versions)):
                raise ValueError('incomplete memory trajectory')
            for row in trial['rows']:
                check_output(row, trial['group'])
                if not _integer(row['rss_peak_bytes'], minimum=1):
                    raise ValueError('invalid RSS bytes')
                if trial['modality'] == 'rss':
                    if row['python_retained_bytes'] is not None or row['python_peak_bytes'] is not None:
                        raise ValueError('RSS must be uninstrumented')
                elif (not _integer(row['python_retained_bytes'])
                      or not _integer(row['python_peak_bytes'])
                      or row['python_peak_bytes'] < row['python_retained_bytes']):
                    raise ValueError('invalid traced Python bytes')
            if trial['rss_peak_bytes'] != max(r['rss_peak_bytes'] for r in trial['rows']):
                raise ValueError('RSS summary mismatch')
            peaks = [r['rss_peak_bytes'] for r in trial['rows']]
            if peaks != sorted(peaks):
                raise ValueError('process high-water RSS decreased')
            expected_peak = (max(r['python_peak_bytes'] for r in trial['rows'])
                             if trial['modality'] == 'python_traced' else None)
            if trial['python_peak_bytes'] != expected_peak:
                raise ValueError('traced peak summary mismatch')
            if trial['modality'] == 'python_traced':
                peaks = [r['python_peak_bytes'] for r in trial['rows']]
                if peaks != sorted(peaks):
                    raise ValueError('traced high-water peak decreased')
        if found != expected:
            raise ValueError('incomplete memory grid')
    elif result['memory_trials']:
        raise ValueError('unexpected memory trials')


def _summary(values):
    return {'median': statistics.median(values), 'min': min(values), 'max': max(values), 'raw': values}


def summarize(result, protocol, manifest):
    validate(result, protocol, manifest)
    groups = {}
    for repo in manifest['repositories']:
        name = repo['repository']
        group = {'methods': {}}
        for method in protocol['methods']:
            item = {}
            rows = [r for r in result['timing_rows']
                    if r['group'] == 'natural:' + name and r['method'] == method]
            if rows:
                for label, select in [('replay_ms', lambda r: r['phase'] == 'replay'),
                                      ('capture_ms', lambda r: r['phase'] == 'capture'),
                                      ('capture_plus_replay_ms', lambda r: True),
                                      ('source_changing_replay_ms', lambda r: r['phase'] == 'replay'
                                       and r['source_changed'])]:
                    totals = [sum(r['elapsed_ns'] for r in rows if r['repetition'] == rep and select(r)) / 1e6
                              for rep in range(1, protocol['repetitions'] + 1)]
                    item[label] = _summary(totals)
                item['reused_per_repeat'] = [sum(r['reused'] for r in rows
                    if r['repetition'] == rep and r['phase'] == 'replay')
                    for rep in range(1, protocol['repetitions'] + 1)]
            for modality in MODALITIES:
                trials = [t for t in result['memory_trials'] if t['group'] == name
                          and t['method'] == method and t['modality'] == modality]
                if trials:
                    metrics = {'rss_peak_bytes': [t['rss_peak_bytes'] for t in trials]}
                    if modality == 'python_traced':
                        metrics.update(python_peak_bytes=[t['python_peak_bytes'] for t in trials],
                                       python_final_retained_bytes=[t['rows'][-1]['python_retained_bytes']
                                                                    for t in trials])
                    item[modality] = {k: _summary(v) for k, v in metrics.items()}
            group['methods'][method] = item
        b, c = [group['methods'][protocol['primary_comparison'][role]] for role in ('baseline', 'candidate')]
        if 'replay_ms' in b:
            group['candidate_replay_reduction'] = 1 - c['replay_ms']['median'] / b['replay_ms']['median']
            group['replay_target_met'] = group['candidate_replay_reduction'] >= protocol['targets']['replay_reduction']
        if 'rss' in b:
            b_rss, c_rss = [m['rss']['rss_peak_bytes']['median'] for m in (b, c)]
            group['candidate_rss_ratio'] = c_rss / b_rss
            group['memory_gate_met'] = (c_rss <= protocol['targets']['max_rss_bytes']
                                       and c_rss / b_rss <= protocol['targets']['max_rss_ratio'])
        groups[name] = group
    targets = Counter(g.get('replay_target_met') for g in groups.values())
    return {'groups': groups, 'canonical_mismatches': 0,
            'repositories_meeting_replay_target': targets[True] if result['timing_rows'] else None,
            'replay_target_met': targets[True] >= protocol['targets']['min_repositories']
                if result['timing_rows'] else None,
            'memory_gate_met': all(g['memory_gate_met'] for g in groups.values())
                if result['memory_trials'] else None,
            'interpretation': 'Repository-held-out convenience sample; descriptive, not population inference; '
                              'resolver output preservation, not semantic freshness or task success.'}


def run(args):
    protocol, manifest = load_inputs()
    provenance = source_provenance()
    raw = {'schema_version': 1, 'study': protocol['study'], 'suite': args.suite,
           'run_id': datetime.now(timezone.utc).strftime('holdout-%Y%m%dT%H%M%S%fZ'),
           'status': 'running', 'started_at_utc': stamp(),
           'protocol_sha256': provenance['protocol_sha256'],
           'manifest_sha256': provenance['manifest_sha256'],
           'runner_sha256': provenance['runner_sha256'], 'provenance': provenance,
           'protocol_snapshot': protocol,
           'methods': protocol['methods'], 'expected_groups': protocol['natural']['repositories'],
           'command': f'python scripts/run_incremental_holdout.py run --suite {args.suite} --output NEW_RUN.json',
           'environment': base.environment(), 'timing_rows': [], 'memory_trials': [],
           'cold_reference': [],
           'timing_orders': [{'group': repo['repository'], 'repetition': rep + 1,
                'methods': protocol['methods'][(rep + offset) % len(protocol['methods']):]
                    + protocol['methods'][:(rep + offset) % len(protocol['methods'])]}
                for offset, repo in enumerate(manifest['repositories'])
                for rep in range(-protocol['warmup'], protocol['repetitions'])]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as handle:
        handle.write(json.dumps(raw, indent=2) + '\n')

    def checkpoint(location=None):
        if location is not None:
            raw['progress'] = location
        base.write(args.output, raw)

    try:
        for repo in manifest['repositories']:
            for row in cold_reference(repo, args.cache_dir, protocol):
                raw['cold_reference'].append(row)
                checkpoint({'phase': 'uncached_reference', 'group': row['group'],
                            'version_index': row['version_index']})
        if args.suite in ('timing', 'all'):
            for offset, repo in enumerate(manifest['repositories']):
                loaders = [corpus.source_loader(args.cache_dir, repo, v) for v in repo['versions']]
                selected = anchors(repo, loaders[0]())
                base.replay_group('natural:' + repo['repository'], loaders,
                                  [v['commit'] for v in repo['versions']], selected,
                                  protocol['repetitions'], offset, rows=raw['timing_rows'],
                                  checkpoint=checkpoint, progress=checkpoint, methods=protocol['methods'],
                                  policy=protocol['resolver_policy'], warmup=protocol['warmup'],
                                  reference={r['version_index']: r['graphs'] for r in raw['cold_reference']
                                             if r['group'] == repo['repository']})
        if args.suite in ('memory', 'all'):
            for offset, repo in enumerate(manifest['repositories']):
                for rep in range(1, protocol['memory_repetitions'] + 1):
                    shift = (rep + offset) % len(protocol['methods'])
                    order = protocol['methods'][shift:] + protocol['methods'][:shift]
                    for method in order:
                        for modality in MODALITIES:
                            location = {'group': repo['repository'], 'method': method,
                                        'modality': modality, 'repetition': rep}
                            checkpoint(location)
                            process = subprocess.run([sys.executable, str(Path(__file__).resolve()), 'worker',
                                '--repository', repo['repository'], '--method', method, '--modality', modality,
                                '--cache-dir', str(args.cache_dir)], capture_output=True, text=True, timeout=600)
                            if process.returncode:
                                raw['failed_child'] = {**location, 'returncode': process.returncode}
                                print(process.stderr, file=sys.stderr)
                                raise RuntimeError('memory worker failed / 内存子进程失败')
                            trial = json.loads(process.stdout)
                            if any(trial.get(key) != location[key] for key in ('group', 'method', 'modality')):
                                raise ValueError('memory child identity differs from requested job')
                            if trial.get('provenance') != provenance:
                                raise ValueError('memory child source/input drift')
                            trial['repetition'] = rep
                            raw['memory_trials'].append(trial)
                            checkpoint()
                    print(repo['repository'], 'memory repetition', rep, flush=True)
        if source_provenance() != provenance:
            raise ValueError('source/input drift during run')
        raw['status'] = 'passed'
        raw['summary'] = summarize(raw, protocol, manifest)
        raw.pop('progress', None)
    except (Exception, KeyboardInterrupt) as error:
        raw['status'] = 'interrupted' if isinstance(error, KeyboardInterrupt) else 'failed'
        raw['error_type'] = type(error).__name__
        raise
    finally:
        raw['finished_at_utc'] = stamp()
        checkpoint()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('run', 'analyze', 'worker'))
    parser.add_argument('--suite', choices=('timing', 'memory', 'all'), default='all')
    parser.add_argument('--cache-dir', type=Path, default=ROOT / 'work/incremental-holdout/archives')
    parser.add_argument('--output', type=Path, help='new run or saved analysis JSON / 新结果或已有分析文件')
    parser.add_argument('--repository')
    parser.add_argument('--method')
    parser.add_argument('--modality', choices=MODALITIES)
    args = parser.parse_args()
    if args.action == 'worker':
        protocol, manifest = load_inputs()
        repo = next(r for r in manifest['repositories'] if r['repository'] == args.repository)
        print(json.dumps(memory_worker(repo, args.method, args.modality, args.cache_dir, protocol)))
    elif args.action == 'analyze':
        if args.output is None:
            parser.error('--output must point to saved JSON / 请指定结果文件')
        raw = json.loads(args.output.read_text())
        if (raw['protocol_sha256'] != base.digest((DATA / 'protocol.json').read_bytes())
                or raw['manifest_sha256'] != base.digest((DATA / 'manifest.json').read_bytes())):
            raise ValueError('analysis must use the measured source/protocol pins / 分析版本漂移')
        print(json.dumps(summarize(raw, *load_inputs()), indent=2))
    else:
        if args.output is None:
            args.output = DATA / 'results' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ.json')
        run(args)


if __name__ == '__main__':
    main()
