"""Independent integrity counterexamples; authored data is never performance evidence.

独立审计配对、来源、内存隔离和失败保留；微型自编数据不构成基准结果。
"""
from argparse import Namespace
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from scripts import run_incremental_holdout as runner
from contextproof.graph import build_graph, canonical_graph_bytes


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture
def study(tmp_path, monkeypatch):
    methods = ['warm_ast_rebuild', 'whole_corpus_guard', 'read_set_any_status',
               'incremental_index_rebuild', 'incremental_read_set']
    protocol = {'study': 'authored-integrity-test', 'methods': methods,
                'natural': {'repositories': ['owner/authored'], 'versions': 3},
                'repetitions': 2, 'memory_repetitions': 2, 'warmup': 1,
                'primary_comparison': {'baseline': 'incremental_index_rebuild',
                                       'candidate': 'incremental_read_set'},
                'resolver_policy': {'max_depth': 4, 'max_nodes': 256},
                'targets': {'replay_reduction': .2, 'min_repositories': 1,
                            'max_rss_bytes': 10_000_000, 'max_rss_ratio': 2}}
    texts = [
        {'pkg/api.py': 'def entry():\n    return 1\n', 'pkg/other.py': 'VALUE = 0\n'},
        {'pkg/api.py': 'def entry():\n    return 1\n', 'pkg/other.py': 'VALUE = 2\n'},
        {'pkg/api.py': 'def entry():\n    return 3\n', 'pkg/other.py': 'VALUE = 2\n'},
    ]
    anchors = runner.corpus.anchors_for(texts[0])
    repo = {'repository': 'owner/authored', 'prefixes': ['pkg/'],
            'anchors': [{k: v for k, v in a.items() if k != 'text'} for a in anchors],
            'versions': [{'commit': format(i + 1, '040x'),
                          'files': {p: sha(s) for p, s in sources.items()}}
                         for i, sources in enumerate(texts)]}
    data = tmp_path / 'data'
    data.mkdir()
    protocol_raw = json.dumps(protocol, sort_keys=True).encode()
    manifest = {'protocol_sha256': hashlib.sha256(protocol_raw).hexdigest(),
                'repositories': [repo]}
    (data / 'protocol.json').write_bytes(protocol_raw)
    (data / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True))
    monkeypatch.setattr(runner, 'DATA', data)
    environment = {'source_commit': '1' * 40, 'implementation_files': {
        p.relative_to(runner.ROOT).as_posix(): runner.base.digest(p.read_bytes())
        for p in sorted((runner.ROOT / 'src/contextproof').glob('*.py'))}}
    raw = {'schema_version': 1, 'study': protocol['study'], 'suite': 'all',
           'status': 'passed', 'methods': methods, 'expected_groups': ['owner/authored'],
           'protocol_sha256': runner.base.digest(protocol_raw),
           'manifest_sha256': runner.base.digest((data / 'manifest.json').read_bytes()),
           'runner_sha256': runner.base.digest(Path(runner.__file__).read_bytes()),
           'protocol_snapshot': deepcopy(protocol), 'environment': environment,
           'timing_rows': [], 'memory_trials': []}
    raw['provenance'] = {k: raw[k] for k in ('runner_sha256', 'protocol_sha256', 'manifest_sha256')}
    raw['provenance']['implementation_files'] = deepcopy(environment['implementation_files'])
    raw['provenance']['supporting_scripts'] = {
        Path(module.__file__).relative_to(runner.ROOT).as_posix(): runner.base.digest(
            Path(module.__file__).read_bytes())
        for module in (runner.base, runner.corpus)}
    for rep in (1, 2):
        for method in methods:
            elapsed = 60 if method == 'incremental_read_set' else 100
            for index, version in enumerate(repo['versions']):
                raw['timing_rows'].append({
                    'group': 'natural:owner/authored', 'method': method, 'repetition': rep,
                    'version_index': index, 'snapshot_id': version['commit'],
                    'graphs': [sha('output-' + str(index))], 'reused': 0, 'rebuilt': 1,
                    'complete': 1, 'phase': 'capture' if index == 0 else 'replay',
                    'elapsed_ns': elapsed, 'load_ns': 20, 'graph_ns': elapsed - 20,
                    'status': 'passed', 'equivalence': True, 'reasons': {'rebuild': 1},
                    'source_changed': index != 0, 'catalog_changed': False,
                    'changed_paths': [] if index == 0 else ['pkg/other.py' if index == 1 else 'pkg/api.py'],
                })
            for modality in runner.MODALITIES:
                rows = [{'version_index': index, 'snapshot_id': version['commit'],
                         'graphs': [sha('output-' + str(index))], 'reused': 0, 'rebuilt': 1,
                         'complete': 1, 'rss_peak_bytes': 1_000_000 + index * 1000,
                         'python_retained_bytes': 100 + index if modality == 'python_traced' else None,
                         'python_peak_bytes': 200 + index if modality == 'python_traced' else None}
                        for index, version in enumerate(repo['versions'])]
                raw['memory_trials'].append({
                    'group': 'owner/authored', 'method': method, 'modality': modality,
                    'repetition': rep, 'status': 'passed', 'pid': 100 + len(raw['memory_trials']),
                    'rows': rows, 'rss_peak_bytes': rows[-1]['rss_peak_bytes'],
                    'python_peak_bytes': rows[-1]['python_peak_bytes'],
                    'provenance': deepcopy(raw['provenance']),
                })
    return SimpleNamespace(protocol=protocol, manifest=manifest, raw=raw, repo=repo,
                           texts=texts, data=data, tmp=tmp_path, environment=environment)


def test_authored_complete_grid_and_repository_trajectory_totals(study):
    summary = runner.summarize(study.raw, study.protocol, study.manifest)
    result = summary['groups']['owner/authored']
    assert result['candidate_replay_reduction'] == pytest.approx(.4)
    assert result['methods']['incremental_read_set']['replay_ms']['raw'] == [120 / 1e6] * 2
    assert result['methods']['incremental_read_set']['capture_plus_replay_ms']['raw'] == [180 / 1e6] * 2
    assert summary['memory_gate_met'] is True


def test_provenance_covers_the_executed_loader_and_timing_harness(study):
    assert runner.source_provenance()['supporting_scripts'] == study.raw['provenance']['supporting_scripts']


@pytest.mark.parametrize('change', ['missing-timing', 'duplicate-timing', 'missing-memory',
                                    'duplicate-memory', 'missing-version', 'duplicate-version',
                                    'cross-method-graph', 'cross-repeat-graph', 'memory-graph',
                                    'failed-trial', 'false-equivalence', 'snapshot', 'counts',
                                    'source-hash-change', 'source-added', 'source-removed',
                                    'bare-timing-group'])
def test_incomplete_or_mismatched_evidence_cannot_be_summarized(study, change):
    raw = study.raw
    if change == 'missing-timing':
        raw['timing_rows'].pop()
    elif change == 'duplicate-timing':
        raw['timing_rows'].append(deepcopy(raw['timing_rows'][0]))
    elif change == 'missing-memory':
        raw['memory_trials'].pop()
    elif change == 'duplicate-memory':
        raw['memory_trials'].append(deepcopy(raw['memory_trials'][0]))
    elif change == 'missing-version':
        raw['memory_trials'][0]['rows'].pop()
    elif change == 'duplicate-version':
        raw['memory_trials'][0]['rows'][1] = deepcopy(raw['memory_trials'][0]['rows'][0])
    elif change == 'cross-method-graph':
        raw['timing_rows'][3]['graphs'] = [sha('wrong graph')]
    elif change == 'cross-repeat-graph':
        for row in raw['timing_rows']:
            if row['repetition'] == 2:
                row['graphs'] = [sha('wrong graph')]
    elif change == 'memory-graph':
        raw['memory_trials'][0]['rows'][0]['graphs'] = [sha('wrong graph')]
    elif change == 'failed-trial':
        raw['memory_trials'][0]['status'] = 'failed'
    elif change == 'false-equivalence':
        raw['timing_rows'][0]['equivalence'] = False
    elif change == 'snapshot':
        raw['memory_trials'][0]['rows'][0]['snapshot_id'] = 'f' * 40
    elif change == 'counts':
        raw['memory_trials'][0]['rows'][0]['rebuilt'] = 2
    elif change.startswith('source-'):
        files = study.repo['versions'][1]['files']
        if change == 'source-hash-change':
            files['pkg/api.py'] = sha('silently changed anchor file')
        elif change == 'source-added':
            files['pkg/added.py'] = sha('new import path')
        else:
            del files['pkg/api.py']
    else:
        raw['timing_rows'][-1]['group'] = 'owner/authored'
    with pytest.raises(ValueError):
        runner.summarize(raw, study.protocol, study.manifest)


@pytest.mark.parametrize('field', ['protocol_sha256', 'manifest_sha256'])
def test_saved_run_cannot_be_reinterpreted_under_different_pins(study, field):
    study.raw[field] = sha('unrelated frozen inputs')
    with pytest.raises(ValueError):
        runner.summarize(study.raw, study.protocol, study.manifest)


def test_mutated_protocol_snapshot_cannot_relax_saved_target(study):
    study.raw['protocol_snapshot']['targets']['replay_reduction'] = 0
    with pytest.raises(ValueError):
        runner.summarize(study.raw, study.protocol, study.manifest)


@pytest.mark.parametrize('change', ['runner-hash', 'implementation-empty', 'implementation-hash',
                                    'implementation-path', 'source-commit', 'top-level-disagreement'])
def test_runtime_provenance_rejects_missing_or_invalid_identities(study, change):
    provenance = study.raw['provenance']
    if change == 'runner-hash':
        provenance['runner_sha256'] = 'not-a-digest'
    elif change == 'implementation-empty':
        provenance['implementation_files'] = {}
    elif change == 'implementation-hash':
        provenance['implementation_files']['src/contextproof/reuse.py'] = 'g' * 64
    elif change == 'implementation-path':
        provenance['implementation_files']['../private.py'] = 'a' * 64
    elif change == 'source-commit':
        study.raw['environment']['source_commit'] = 'not-a-commit'
    else:
        study.raw['runner_sha256'] = sha('another runner')
    with pytest.raises(ValueError):
        runner.summarize(study.raw, study.protocol, study.manifest)


def test_historical_source_hashes_do_not_silently_mean_the_current_code(study):
    # Source identity remains explicit even if a later analyzer's code differs.
    # This is historical schema acceptance, never current-code attestation.
    historical = {p: sha('historical-' + p) for p in study.raw['provenance']['implementation_files']}
    study.raw['provenance']['implementation_files'] = historical
    study.raw['environment']['implementation_files'] = deepcopy(historical)
    for trial in study.raw['memory_trials']:
        trial['provenance']['implementation_files'] = deepcopy(historical)
    runner.validate(study.raw, study.protocol, study.manifest)


@pytest.mark.parametrize('change', ['instrumented-rss', 'negative', 'retained-over-peak',
                                    'decreasing-rss', 'decreasing-traced-peak', 'summary'])
def test_memory_evidence_rejects_impossible_trajectories(study, change):
    trial = study.raw['memory_trials'][1 if change in ('retained-over-peak', 'decreasing-traced-peak') else 0]
    if change == 'instrumented-rss':
        trial['rows'][0]['python_retained_bytes'] = 1
    elif change == 'negative':
        trial['rows'][0]['rss_peak_bytes'] = -1
    elif change == 'retained-over-peak':
        trial['rows'][0]['python_retained_bytes'] = 999
    elif change == 'decreasing-rss':
        trial['rows'][1]['rss_peak_bytes'] = 1
    elif change == 'decreasing-traced-peak':
        trial['rows'][1]['python_peak_bytes'] = 150
    else:
        trial['rss_peak_bytes'] += 1
    with pytest.raises(ValueError):
        runner.summarize(study.raw, study.protocol, study.manifest)


def test_tracemalloc_process_rss_cannot_influence_the_rss_gate(study):
    for trial in study.raw['memory_trials']:
        if trial['modality'] == 'python_traced':
            trial['rss_peak_bytes'] = 10**12
            for row in trial['rows']:
                row['rss_peak_bytes'] = 10**12
    assert runner.summarize(study.raw, study.protocol, study.manifest)['memory_gate_met'] is True


def test_rss_units_are_explicit_and_unknown_platforms_fail():
    assert runner.rss_bytes(123, 'darwin') == 123
    assert runner.rss_bytes(123, 'linux') == 123 * 1024
    with pytest.raises(ValueError):
        runner.rss_bytes(123, 'unknown')


def install_authored_sources(study, monkeypatch):
    loads = []
    def source_loader(cache, repo, version):
        index = next(i for i, item in enumerate(study.repo['versions'])
                     if item['commit'] == version['commit'])
        def load():
            loads.append((index, runner.tracemalloc.is_tracing()))
            return dict(study.texts[index])
        return load
    monkeypatch.setattr(runner.corpus, 'source_loader', source_loader)
    return loads


@pytest.mark.parametrize('modality', runner.MODALITIES)
def test_authored_memory_trajectory_loads_each_version_once_with_correct_instrumentation(study, monkeypatch, modality):
    loads = install_authored_sources(study, monkeypatch)
    try:
        trial = runner.memory_worker(study.repo, 'warm_ast_rebuild', modality,
                                     study.tmp / 'cache', study.protocol)
        assert loads == [(i, modality == 'python_traced') for i in range(3)]
        assert len(trial['rows']) == 3
        assert all(row['rebuilt'] == 1 for row in trial['rows'])
        assert not runner.tracemalloc.is_tracing()
    finally:
        runner.tracemalloc.stop()


def test_memory_worker_graphs_match_direct_rebuild_on_authored_sources(study, monkeypatch):
    install_authored_sources(study, monkeypatch)
    selected = runner.corpus.anchors_for(study.texts[0])
    expected = [[runner.base.digest(canonical_graph_bytes(build_graph(
        texts, version['commit'], [anchor], **study.protocol['resolver_policy'])))
                 for anchor in selected]
                for texts, version in zip(study.texts, study.repo['versions'])]
    for method in study.protocol['methods']:
        trial = runner.memory_worker(study.repo, method, 'rss', study.tmp / 'cache', study.protocol)
        assert [row['graphs'] for row in trial['rows']] == expected


def install_run(study, monkeypatch, suite='memory'):
    monkeypatch.setattr(runner, 'load_inputs', lambda: (study.protocol, study.manifest))
    monkeypatch.setattr(runner.base, 'environment', lambda: deepcopy(study.environment))
    return Namespace(suite=suite, cache_dir=study.tmp / 'cache', output=study.tmp / 'run.json')


@pytest.mark.parametrize('failure', ['exit', 'timeout', 'malformed-json', 'interrupt'])
def test_memory_child_failure_preserves_prior_results_and_exact_progress(study, monkeypatch, failure):
    args = install_run(study, monkeypatch)
    first = deepcopy(study.raw['memory_trials'][0])
    calls = []
    def execute(command, **kwargs):
        calls.append(command)
        if len(calls) == 1:
            first.update(method=command[command.index('--method') + 1],
                         modality=command[command.index('--modality') + 1])
            return SimpleNamespace(returncode=0, stdout=json.dumps(first), stderr='')
        if failure == 'exit':
            return SimpleNamespace(returncode=7, stdout='', stderr='authored child failed')
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(command, 600)
        if failure == 'interrupt':
            raise KeyboardInterrupt
        return SimpleNamespace(returncode=0, stdout='invalid JSON', stderr='')
    monkeypatch.setattr(runner.subprocess, 'run', execute)
    with pytest.raises((RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError, KeyboardInterrupt)):
        runner.run(args)
    saved = json.loads(args.output.read_text())
    assert saved['status'] == ('interrupted' if failure == 'interrupt' else 'failed')
    assert len(saved['memory_trials']) == 1
    assert saved['memory_trials'][0]['rows'] == first['rows']
    assert saved['progress']['modality'] == 'python_traced'
    assert saved['finished_at_utc']
    assert 'summary' not in saved
    if failure == 'exit':
        assert saved['failed_child']['returncode'] == 7


def test_existing_run_is_never_overwritten(study, monkeypatch):
    args = install_run(study, monkeypatch)
    old = b'{"status": "failed", "evidence": "preserve"}\n'
    args.output.write_bytes(old)
    with pytest.raises(FileExistsError):
        runner.run(args)
    assert args.output.read_bytes() == old


def test_memory_trial_is_bound_to_the_invoked_method_not_just_a_complete_grid(study, monkeypatch):
    args = install_run(study, monkeypatch)
    methods = study.protocol['methods']
    calls = []
    def execute(command, **kwargs):
        calls.append(command)
        requested = command[command.index('--method') + 1]
        modality = command[command.index('--modality') + 1]
        # A permutation still fills the entire paired grid, but attributes each
        # real process result to another method. It must fail at the boundary.
        wrong = methods[(methods.index(requested) + 1) % len(methods)]
        trial = deepcopy(next(t for t in study.raw['memory_trials']
                              if t['method'] == wrong and t['modality'] == modality))
        return SimpleNamespace(returncode=0, stdout=json.dumps(trial), stderr='')
    monkeypatch.setattr(runner.subprocess, 'run', execute)
    with pytest.raises(ValueError):
        runner.run(args)
    assert len(calls) == 1
    assert json.loads(args.output.read_text())['status'] == 'failed'


@pytest.mark.parametrize('field', ['protocol_sha256', 'manifest_sha256', 'runner_sha256',
                                   'implementation_files'])
def test_memory_child_must_use_the_parent_frozen_inputs_and_implementation(study, monkeypatch, field):
    args = install_run(study, monkeypatch)
    calls = []
    def execute(command, **kwargs):
        calls.append(command)
        trial = deepcopy(study.raw['memory_trials'][0])
        trial.update(method=command[command.index('--method') + 1],
                     modality=command[command.index('--modality') + 1])
        if field == 'implementation_files':
            trial['provenance'][field]['src/contextproof/reuse.py'] = sha('other runtime')
        else:
            trial['provenance'][field] = sha('other input or runner')
        return SimpleNamespace(returncode=0, stdout=json.dumps(trial), stderr='')
    monkeypatch.setattr(runner.subprocess, 'run', execute)
    with pytest.raises(ValueError):
        runner.run(args)
    assert len(calls) == 1
    saved = json.loads(args.output.read_text())
    assert saved['status'] == 'failed'
    assert not saved['memory_trials']


def test_runtime_source_drift_during_run_cannot_be_marked_passed(study, monkeypatch):
    args = install_run(study, monkeypatch)
    calls = []
    def provenance():
        calls.append(None)
        state = deepcopy(study.raw['provenance'])
        if len(calls) > 1:
            state['implementation_files']['src/contextproof/reuse.py'] = sha('edit during execution')
        return state
    monkeypatch.setattr(runner, 'source_provenance', provenance)
    def execute(command, **kwargs):
        method = command[command.index('--method') + 1]
        modality = command[command.index('--modality') + 1]
        trial = deepcopy(next(t for t in study.raw['memory_trials']
                              if t['method'] == method and t['modality'] == modality))
        return SimpleNamespace(returncode=0, stdout=json.dumps(trial), stderr='')
    monkeypatch.setattr(runner.subprocess, 'run', execute)
    with pytest.raises(ValueError):
        runner.run(args)
    assert json.loads(args.output.read_text())['status'] == 'failed'


def test_rss_worker_rejects_preexisting_tracing_in_its_process(study, monkeypatch):
    install_authored_sources(study, monkeypatch)
    runner.tracemalloc.start()
    try:
        with pytest.raises(ValueError):
            runner.memory_worker(study.repo, 'warm_ast_rebuild', 'rss',
                                 study.tmp / 'cache', study.protocol)
    finally:
        runner.tracemalloc.stop()


def test_timing_runner_forwards_frozen_policy_and_warmups(study, monkeypatch):
    args = install_run(study, monkeypatch, 'timing')
    install_authored_sources(study, monkeypatch)
    study.protocol['resolver_policy'] = {'max_depth': 1, 'max_nodes': 7}
    study.protocol['warmup'] = 2
    captured = {}
    class StopBeforeTiming(Exception):
        pass
    def replay(*arguments, **kwargs):
        captured.update(kwargs)
        raise StopBeforeTiming
    monkeypatch.setattr(runner.base, 'replay_group', replay)
    with pytest.raises(StopBeforeTiming):
        runner.run(args)
    assert captured.get('policy') == study.protocol['resolver_policy']
    assert captured.get('warmup') == 2
