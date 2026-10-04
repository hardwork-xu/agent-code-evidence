#!/usr/bin/env python3
"""Reproducible static-evidence replay / 可复现静态证据回放；不执行上游代码。"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import platform
import statistics
import subprocess
import sys
import tarfile
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from contextproof.evidence import sha256  # noqa: E402
from contextproof.graph import canonical_graph_bytes  # noqa: E402
from contextproof.reuse import GraphSession  # noqa: E402

DATA = ROOT / 'benchmarks/selective_reuse'
PREFIXES = {'Textualize/rich': ['rich/'], 'python-humanize/humanize': ['src/humanize/'],
            'more-itertools/more-itertools': ['more_itertools/'], 'PyCQA/pyflakes': ['pyflakes/']}
METHODS = ['warm_ast_rebuild', 'whole_corpus_guard', 'read_set_certificate']


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n')


def api(route):
    return json.loads(subprocess.check_output(['gh', 'api', route], timeout=40))


def pin_repository(repo):
    result = subprocess.run(['gh', 'api', f'repos/{repo}/releases/latest'],
                            capture_output=True, text=True, timeout=40)
    release = json.loads(result.stdout)
    if result.returncode:
        if release.get('status') != '404':
            raise RuntimeError('release discovery failed: ' + repo)
        tag = api(f'repos/{repo}/tags?per_page=1')[0]['name']
        kind = 'tag-fallback-no-github-release'
    else:
        if release['draft'] or release['prerelease']:
            raise RuntimeError('unexpected prerelease')
        tag, kind = release['tag_name'], 'github-latest-release'
    head = api(f'repos/{repo}/commits/{tag}')
    versions = []
    for _ in range(6):
        versions.append({'commit': head['sha'], 'date': head['commit']['committer']['date'],
                         'parents': [p['sha'] for p in head['parents']],
                         'archive_url': f"https://codeload.github.com/{repo}/tar.gz/{head['sha']}"})
        if len(versions) < 6:
            head = api(f"repos/{repo}/commits/{head['parents'][0]['sha']}")
    return {'repository': repo, 'selection_kind': kind, 'tag': tag,
            'prefixes': PREFIXES[repo], 'versions': list(reversed(versions))}


def archive_path(cache, repo, version):
    return cache / f"{repo['repository'].replace('/', '--')}--{version['commit']}.tar.gz"


def read_sources(path, prefixes):
    texts, licenses, excluded = {}, {}, Counter()
    with tarfile.open(path, 'r:gz') as archive:
        for member in archive:
            parts = PurePosixPath(member.name)
            if parts.is_absolute() or '..' in parts.parts:
                raise ValueError('unsafe archive path')
            if not member.isfile() or member.size > 2 * 1024 * 1024:
                continue
            relative = '/'.join(parts.parts[1:])
            if len(parts.parts) == 2 and parts.name.lower().startswith(('license', 'licence', 'copying')):
                licenses[relative] = archive.extractfile(member).read()
            if not relative.endswith(('.py', '.pyi')):
                continue
            if not any(relative.startswith(prefix) for prefix in prefixes):
                excluded['outside_package'] += 1
                continue
            if any(p.lower() in {'test', 'tests', 'fixtures', 'vendor', 'vendored', '_vendor', 'generated'}
                   for p in parts.parts[1:]) or parts.name.startswith('test_'):
                excluded['test_vendor_generated'] += 1
                continue
            raw = archive.extractfile(member).read()
            try:
                text = raw.decode('utf-8')
            except UnicodeDecodeError:
                excluded['non_utf8'] += 1
                continue
            if relative in texts:
                raise ValueError('duplicate source path')
            texts[relative] = text
    if not texts or not licenses:
        raise ValueError('missing source or license')
    return texts, licenses, dict(excluded)


def anchors_for(texts, limit=24):
    candidates = []
    for path, source in sorted(texts.items()):
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError, RecursionError):
            continue
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            start = min([node.lineno, *(x.lineno for x in node.decorator_list)])
            text = ''.join(source.splitlines(keepends=True)[start - 1:node.end_lineno])
            candidates.append({'id': sha256(path + ':' + node.name), 'path': path,
                               'symbol': node.name, 'kind': 'function', 'start_line': start,
                               'end_line': node.end_lineno, 'text': text,
                               'text_sha256': sha256(text), 'file_sha256': sha256(source)})
    # One anchor per qualified identity; overload/redefinition ambiguity remains
    # in the complete source corpus instead of being silently filtered away.
    unique = {}
    for candidate in candidates:
        unique.setdefault(candidate['id'], candidate)
    return sorted(unique.values(), key=lambda x: x['id'])[:limit]


def prepare(cache):
    protocol = json.loads((DATA / 'protocol.json').read_text())
    manifest_path = DATA / 'natural-manifest.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        allowed = {digest((DATA / 'protocol.json').read_bytes()),
                   *protocol.get('supersedes_protocol_sha256', [])}
        if manifest['protocol_sha256'] not in allowed:
            raise ValueError('unacknowledged protocol change; preserve pins and record amendment')
    else:
        with ThreadPoolExecutor(max_workers=4) as pool:
            repos = list(pool.map(pin_repository, protocol['natural']['repositories']))
        manifest = {'schema_version': 1, 'pinned_at_utc': datetime.now(timezone.utc).isoformat(),
                    'protocol_sha256': digest((DATA / 'protocol.json').read_bytes()),
                    'repositories': repos}
        write(manifest_path, manifest)  # Before downloading sources or measuring outcomes.
    cache.mkdir(parents=True, exist_ok=True)
    def download(item):
        repo, version = item
        path = archive_path(cache, repo, version)
        if not path.exists():
            pending = path.with_suffix('.partial')
            subprocess.run(['curl', '-L', '--fail', '--silent', '--show-error',
                            '--max-time', '90', '--output', str(pending), version['archive_url']],
                           check=True, timeout=95)
            pending.replace(path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(download, [(r, v) for r in manifest['repositories'] for v in r['versions']]))
    for repo in manifest['repositories']:
        for version in repo['versions']:
            path = archive_path(cache, repo, version)
            if not path.exists():
                pending = path.with_suffix('.partial')
                subprocess.run(['curl', '-L', '--fail', '--silent', '--show-error',
                                '--max-time', '90', '--output', str(pending), version['archive_url']],
                               check=True, timeout=95)
                pending.replace(path)
            raw_hash = digest(path.read_bytes())
            if version.get('archive_sha256', raw_hash) != raw_hash:
                raise ValueError('archive bytes changed')
            texts, licenses, excluded = read_sources(path, repo['prefixes'])
            version['archive_sha256'] = raw_hash
            version['files'] = {p: sha256(s) for p, s in sorted(texts.items())}
            version['excluded'] = excluded
            version['licenses'] = []
            for name, raw in licenses.items():
                dest = DATA / 'licenses' / repo['repository'].replace('/', '--') / version['commit'] / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(raw)
                version['licenses'].append({'path': name, 'sha256': digest(raw),
                                            'local': dest.relative_to(ROOT).as_posix()})
            print(repo['repository'], version['commit'][:8], len(texts), flush=True)
        first, _, _ = read_sources(archive_path(cache, repo, repo['versions'][0]), repo['prefixes'])
        selected = anchors_for(first)
        repo['anchors'] = [{k: v for k, v in a.items() if k != 'text'} for a in selected]
        if not selected:
            raise ValueError('no anchors: ' + repo['repository'])
        write(manifest_path, manifest)
    manifest['sources_frozen_at_utc'] = datetime.now(timezone.utc).isoformat()
    write(manifest_path, manifest)


def validate_manifest(manifest, protocol):
    """Reject protocol/data drift before measurement / 测量前拒绝协议或数据漂移。"""
    allowed = {digest((DATA / 'protocol.json').read_bytes()),
               *protocol.get('supersedes_protocol_sha256', [])}
    if manifest.get('protocol_sha256') not in allowed or not manifest.get('sources_frozen_at_utc'):
        raise ValueError('source manifest is not frozen under this protocol lineage')
    if [r['repository'] for r in manifest['repositories']] != protocol['natural']['repositories']:
        raise ValueError('repository selection drift')
    for repo in manifest['repositories']:
        if len({v['commit'] for v in repo['versions']}) != len(repo['versions']):
            raise ValueError('duplicate pinned commits')
        if repo.get('prefixes') != PREFIXES[repo['repository']]:
            raise ValueError('source prefix drift')
        if len(repo['versions']) != protocol['natural']['versions'] or not repo.get('anchors'):
            raise ValueError('incomplete pinned source corpus')
        for index, version in enumerate(repo['versions']):
            if not version.get('files') or not version.get('licenses') or len(version.get('archive_sha256', '')) != 64:
                raise ValueError('missing source or license record')
            if index and version['parents'][0] != repo['versions'][index - 1]['commit']:
                raise ValueError('broken first-parent chain')
        seen = set()
        for anchor in repo['anchors']:
            required = {'id', 'path', 'symbol', 'kind', 'start_line', 'end_line', 'text_sha256', 'file_sha256'}
            if not isinstance(anchor, dict) or set(anchor) != required:
                raise ValueError('invalid anchor metadata schema')
            if (anchor['id'] in seen or anchor['id'] != sha256(anchor['path'] + ':' + anchor['symbol'])
                    or anchor['path'] not in repo['versions'][0]['files']
                    or anchor['file_sha256'] != repo['versions'][0]['files'][anchor['path']]
                    or type(anchor['start_line']) is not int or type(anchor['end_line']) is not int
                    or not 1 <= anchor['start_line'] <= anchor['end_line']
                    or anchor['kind'] != 'function' or len(anchor['text_sha256']) != 64):
                raise ValueError('invalid or duplicate anchor metadata')
            seen.add(anchor['id'])
        if len(seen) > 24:
            raise ValueError('anchor selection limit exceeded')


def source_loader(cache, repo, version):
    path = archive_path(cache, repo, version)
    def load():
        # Hash and reopen archives for every method: warm OS filesystem cache,
        # not a claim about cold disk or network latency.
        if digest(path.read_bytes()) != version['archive_sha256']:
            raise ValueError('source archive checksum mismatch')
        texts, _, _ = read_sources(path, repo['prefixes'])
        if {p: sha256(s) for p, s in texts.items()} != version['files']:
            raise ValueError('source manifest mismatch')
        return texts
    return load


def replay_group(name, loaders, ids, anchors, repetitions, offset=0, *, rows=None, checkpoint=None, progress=None):
    rows = [] if rows is None else rows
    for repetition in range(-1, repetitions):
        order = METHODS[(repetition + offset) % 3:] + METHODS[:(repetition + offset) % 3]
        outputs = {}
        for method in order:
            session = GraphSession(anchors, mode=method)
            previous = None
            for index, (load, sid) in enumerate(zip(loaders, ids)):
                if progress:
                    progress({"group": name, "method": method, "repetition": repetition + 1,
                              "version_index": index, "snapshot_id": sid})
                started = time.perf_counter_ns()
                texts = load()
                loaded = time.perf_counter_ns()
                result = session.update(texts, sid)
                stopped = time.perf_counter_ns()
                changed_paths = ([] if previous is None else sorted(p for p in previous.keys() | texts.keys()
                                   if previous.get(p) != texts.get(p)))
                catalog_changed = previous is not None and previous.keys() != texts.keys()
                previous = texts
                output = [digest(canonical_graph_bytes(g)) for g in result.graphs]
                key = index
                if key in outputs and outputs[key] != output:
                    rows.append({'group': name, 'repetition': repetition + 1, 'method': method,
                                 'version_index': index, 'status': 'failed',
                                 'expected_graphs': outputs[key], 'actual_graphs': output,
                                 'error': 'canonical_graph_mismatch'})
                    if checkpoint:
                        checkpoint()
                    raise RuntimeError(f'canonical graph mismatch: {name}/{method}/{index}')
                outputs[key] = output
                if repetition >= 0:
                    rows.append({'group': name, 'repetition': repetition + 1, 'method': method,
                                 'version_index': index, 'phase': 'capture' if index == 0 else 'replay',
                                 'snapshot_id': sid, 'elapsed_ns': stopped - started,
                                 'load_ns': loaded - started, 'graph_ns': stopped - loaded,
                                 'source_changed': bool(changed_paths),
                                 'changed_paths': changed_paths, 'catalog_changed': catalog_changed,
                                 'reused': result.reused, 'rebuilt': result.rebuilt,
                                 'reasons': result.reasons, 'graphs': output,
                                 'complete': sum(not g['frontier'] for g in result.graphs),
                                 'equivalence': True, 'status': 'passed'})
                    if checkpoint:
                        checkpoint()
        print(name, 'warmup' if repetition == -1 else f'repetition {repetition+1}', flush=True)
    return rows


def synthetic_loaders(n, workload):
    texts = {f'm{i}.py': f'def value():\n    return {i}\n' for i in range(n)}
    anchors = [anchors_for({f'm{i}.py': texts[f'm{i}.py']}, 1)[0] for i in range(4)]
    changed = dict(texts)
    if workload == 'unrelated_file_change':
        changed[f'm{n-1}.py'] += '\nEXTRA = 1\n'
    elif workload == 'referenced_file_change':
        for i in range(4):
            changed[f'm{i}.py'] = changed[f'm{i}.py'].replace(f'return {i}', f'return {i+1}')
    else:
        changed['added.py'] = 'FLAG = 1\n'
    return [lambda: dict(texts), lambda: dict(changed)], ['before', 'after'], anchors


def environment():
    cpu = subprocess.run(['sysctl', '-n', 'machdep.cpu.brand_string'], capture_output=True,
                         text=True) if sys.platform == 'darwin' else None
    return {'python': platform.python_version(), 'system': platform.system(),
            'release': platform.release(), 'architecture': platform.machine(),
            'cpu': cpu.stdout.strip() if cpu and not cpu.returncode else platform.processor(),
            'implementation': platform.python_implementation(), 'third_party_runtime': 'none',
            'memory_bytes': int(subprocess.check_output(['sysctl', '-n', 'hw.memsize']))
                if sys.platform == 'darwin' else None,
            'logical_cpus': __import__('os').cpu_count(),
            'threads': 1, 'source_commit': subprocess.check_output(
                ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'source_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)),
            'implementation_files': {p.relative_to(ROOT).as_posix(): digest(p.read_bytes())
                                     for p in sorted((ROOT / 'src/contextproof').glob('*.py'))},
            'runner_sha256': digest(Path(__file__).read_bytes())}


def validate_measurements(result):
    if result.get('status', 'passed') != 'passed':
        raise ValueError('only a completed passed run can be summarized')
    rows = result['rows']
    if not rows or any(r.get('status') != 'passed' for r in rows):
        raise ValueError('cannot summarize an empty or failed measurement as success')
    groups = {r['group'] for r in rows}
    if 'expected_groups' in result and groups != set(result['expected_groups']):
        raise ValueError('missing study group')
    keys = [(r['group'], r['repetition'], r['method'], r['version_index']) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError('duplicate measurement')
    invariant_rows = {}
    for row in rows:
        phase = 'capture' if row['version_index'] == 0 else 'replay'
        if (row['phase'] != phase or row['elapsed_ns'] < 0 or row['load_ns'] < 0
                or row['graph_ns'] < 0 or row['elapsed_ns'] != row['load_ns'] + row['graph_ns']):
            raise ValueError('invalid phase or timing record')
        if (row['source_changed'] != bool(row['changed_paths'])
                or row['changed_paths'] != sorted(set(row['changed_paths']))
                or (row['catalog_changed'] and not row['source_changed'])):
            raise ValueError('inconsistent source-change metadata')
        key = row['group'], row['version_index']
        invariant = {k: row[k] for k in ['graphs', 'phase', 'snapshot_id', 'source_changed',
                                        'changed_paths', 'catalog_changed']}
        if key in invariant_rows and invariant_rows[key] != invariant:
            raise ValueError('fixed-snapshot output or metadata drift across methods/repeats')
        invariant_rows[key] = invariant
    for group in groups:
        selected = [r for r in rows if r['group'] == group]
        reps = set(range(1, result.get('repetitions', max(r['repetition'] for r in selected)) + 1))
        versions = set(range(max(r['version_index'] for r in selected) + 1))
        expected_count = 6 if group.startswith('natural:') else 2
        if len(versions) != expected_count:
            raise ValueError('incomplete revision trajectory')
        expected = {(group, rep, method, version) for rep in reps for method in METHODS for version in versions}
        if set(k for k in keys if k[0] == group) != expected:
            raise ValueError('incomplete method/repetition/version grid')
        for rep in reps:
            for version in versions:
                pair = [r for r in selected if r['repetition'] == rep and r['version_index'] == version]
                if (len({tuple(r['graphs']) for r in pair}) != 1
                        or any(not r.get('equivalence') for r in pair)):
                    raise ValueError('canonical graph mismatch in raw results')
    return 0


def summarize(result):
    if not result.get('_changed_only'):
        validate_measurements(result)
    groups = {}
    if any(r.get('status') != 'passed' for r in result['rows']):
        raise ValueError('cannot summarize a failed measurement as success')
    for name in sorted({r['group'] for r in result['rows']}):
        rows = [r for r in result['rows'] if r['group'] == name and r['phase'] == 'replay']
        per_method = {}
        for method in METHODS:
            selected = [r for r in rows if r['method'] == method]
            totals = [sum(r['elapsed_ns'] for r in selected if r['repetition'] == repetition)
                      / 1e6 for repetition in sorted({r['repetition'] for r in selected})]
            per_method[method] = {'median_ms': statistics.median(totals), 'min_ms': min(totals),
                                  'max_ms': max(totals),
                                  'reused_per_repeat': sum(r['reused'] for r in selected) / len(totals),
                                  'rebuilt_per_repeat': sum(r['rebuilt'] for r in selected) / len(totals)}
        base = per_method[METHODS[0]]['median_ms']
        for metrics in per_method.values():
            metrics['reduction_vs_rebuild'] = 1 - metrics['median_ms'] / base
        groups[name] = per_method
    natural = [v for k, v in groups.items() if k.startswith('natural:')]
    wins = sum(v['read_set_certificate']['reduction_vs_rebuild'] >= .20 for v in natural)
    changed = [r for r in result['rows'] if r.get('source_changed') or r['phase'] == 'capture']
    changed_groups = {}
    if not result.get('_changed_only') and any(r['phase'] == 'replay' for r in changed):
        eligible = {r['group'] for r in changed if r['phase'] == 'replay'}
        changed_groups = summarize({'rows': [r for r in changed if r['group'] in eligible],
                                    '_changed_only': True})['groups']
    return {'groups': groups, 'source_changing_groups': changed_groups,
            'natural_repositories_meeting_target': wins,
            'utility_target_met': len(natural) == 4 and wins >= 3,
            'canonical_mismatches': 0, 'timing_unit': 'ms, sum of replay transitions per repeat',
            'inference': 'descriptive only; four convenience-sampled repositories'}


def run(args):
    protocol = json.loads((DATA / 'protocol.json').read_text())
    if args.suite in {'all', 'natural'}:
        validate_manifest(json.loads((DATA / 'natural-manifest.json').read_text()), protocol)
    result = {'schema_version': 1, 'run_id': datetime.now(timezone.utc).strftime('selective-%Y%m%dT%H%M%SZ'),
              'command': 'python scripts/run_selective_reuse.py run --suite ' + args.suite,
              'started_at_utc': datetime.now(timezone.utc).isoformat(),
              'protocol_sha256': digest((DATA / 'protocol.json').read_bytes()),
              'environment': environment(), 'rows': [], 'status': 'running'}
    result['repetitions'] = protocol['timing']['repetitions']
    result['expected_groups'] = []
    if args.suite in {'all', 'synthetic'}:
        result['expected_groups'] += [f'synthetic:{n}:{w}' for n in protocol['synthetic']['module_counts']
                                      for w in protocol['synthetic']['workloads']]
    if args.suite in {'all', 'natural'}:
        result['expected_groups'] += ['natural:' + r for r in protocol['natural']['repositories']]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as handle:
        handle.write(json.dumps(result, indent=2) + '\n')
    def progress(location):
        result['progress'] = location
        write(args.output, result)
    try:
        if args.suite in {'all', 'synthetic'}:
            for n in protocol['synthetic']['module_counts']:
                for workload in protocol['synthetic']['workloads']:
                    loaders, ids, anchors = synthetic_loaders(n, workload)
                    replay_group(f'synthetic:{n}:{workload}', loaders, ids, anchors,
                                 protocol['timing']['repetitions'], n, rows=result['rows'],
                                 checkpoint=lambda: write(args.output, result), progress=progress)
                    write(args.output, result)
        if args.suite in {'all', 'natural'}:
            manifest = json.loads((DATA / 'natural-manifest.json').read_text())
            validate_manifest(manifest, protocol)
            result['natural_manifest_sha256'] = digest((DATA / 'natural-manifest.json').read_bytes())
            for index, repo in enumerate(manifest['repositories']):
                loaders = [source_loader(args.cache_dir, repo, version) for version in repo['versions']]
                first = loaders[0]()
                expected = [{k: v for k, v in a.items() if k != 'text'} for a in anchors_for(first)]
                if expected != repo['anchors']:
                    raise ValueError('deterministic anchor selection drift')
                anchors = [{**a, 'text': ''.join(first[a['path']].splitlines(keepends=True)[
                    a['start_line'] - 1:a['end_line']])} for a in repo['anchors']]
                replay_group('natural:' + repo['repository'], loaders,
                    [v['commit'] for v in repo['versions']], anchors,
                    protocol['timing']['repetitions'], index, rows=result['rows'],
                    checkpoint=lambda: write(args.output, result), progress=progress)
                write(args.output, result)
        result['status'] = 'passed'
        result['summary'] = summarize(result)
    except (Exception, KeyboardInterrupt) as exc:
        result['status'] = 'interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed'
        result['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        result['error_type'] = type(exc).__name__
        # Keep paths and exception detail in local stderr rather than public data.
        write(args.output, result)
        raise
    result.pop('progress', None)
    result['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    write(args.output, result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run', 'analyze'], help='准备 / 实验 / 汇总')
    parser.add_argument('--cache-dir', type=Path, default=ROOT / 'work/selective-reuse/archives',
                        help='private download cache / 不提交的下载缓存')
    parser.add_argument('--suite', choices=['synthetic', 'natural', 'all'], default='all')
    parser.add_argument('--output', type=Path, help='new raw run path, never overwritten / 不覆盖既有原始记录')
    args = parser.parse_args()
    if args.output is None and args.action == 'analyze':
        parser.error('analyze requires --output pointing to a saved run / 请指定已有结果')
    if args.output is None:
        args.output = DATA / 'results' / (datetime.now(timezone.utc).strftime('replay-%Y%m%dT%H%M%S%fZ') + '.json')
    if args.action == 'prepare':
        prepare(args.cache_dir)
    elif args.action == 'run':
        run(args)
    else:
        print(json.dumps(summarize(json.loads(args.output.read_text())), indent=2))


if __name__ == '__main__':
    main()
