"""Sequential, non-overwriting execution controller / 串行、保留失败的执行入口。

Inputs must be reviewed local task configs. No arbitrary dataset command is
executed. Paths and raw logs are private; publish only a separately reviewed
projection. 输入为已审本地配置；原始日志与路径不直接公开。
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    with path.open('xb') as stream:
        stream.write(canonical(value) + b'\n')
    path.chmod(0o600)


def stop_child(child):
    """Stop only our process group; tolerate a just-finished child / 只终止本条件进程组。"""
    if child.poll() is None:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def validate_protocol(protocol, repository):
    """Bind executable source before every condition / 每个条件核验执行源码。"""
    required = {'benchmarks/semantic_observer/observer.py',
                'benchmarks/semantic_observer/worker.py',
                'benchmarks/semantic_observer/run.py',
                'benchmarks/known_task_execution/worker.py'}
    bindings = protocol.get('implementation_sha256', {})
    if not required <= bindings.keys():
        raise ValueError('protocol lacks actual implementation bindings')
    for name, expected in bindings.items():
        parts = Path(name).parts
        if not parts or Path(name).is_absolute() or any(p in {'.', '..'} for p in parts):
            raise ValueError('invalid protocol source path')
        path = repository / name
        if path.is_symlink() or not path.resolve().is_relative_to(repository.resolve()):
            raise ValueError('source binding escaped repository')
        if sha(path.read_bytes()) != expected:
            raise ValueError('frozen implementation changed: ' + name)
    for key, lower, upper in [('cpu_seconds', 1, 600), ('wall_seconds', 1, 1200),
                               ('max_rss_mib', 64, 4096), ('max_observations', 1, 100000)]:
        value = protocol.get(key)
        if type(value) is not int or not lower <= value <= upper:
            raise ValueError('invalid resource protocol: ' + key)


def normalized_phases(result):
    """Ignore durations only; preserve all outcomes / 只忽略耗时，保留全部结果。"""
    return [{key: row[key] for key in ('nodeid', 'phase', 'outcome', 'wasxfail', 'error_type')}
            for row in result['phase_reports']]


def verify_prediction_seal(directory, manifest, protocol):
    """Require every selected prediction before execution / 执行前验证全任务预测封存。"""
    if directory is None:
        raise ValueError('primary execution requires an existing prediction seal')
    directory = Path(directory).resolve(strict=True)
    seal = json.loads((directory / 'SEAL.json').read_bytes())
    if (seal.get('manifest_sha256') != sha(canonical(manifest))
            or seal.get('protocol_sha256') != sha(canonical(protocol))
            or seal.get('implementation_sha256') != protocol['implementation_sha256']
            or seal.get('implementation_unchanged') is not True
            or seal.get('all_selected_rows_sealed') is not True
            or seal.get('all_selected_count') != len(manifest['tasks'])
            or len(seal.get('rows', [])) != len(manifest['tasks'])):
        raise ValueError('prediction seal does not bind this complete experiment')
    for index, (row, task) in enumerate(zip(seal['rows'], manifest['tasks'], strict=True)):
        if (row['task_id'] != task['task_id'] or row['filename'] != f'task-{index:03d}.json'
                or row['task_config_sha256'] != sha(canonical(task))):
            raise ValueError('prediction task/config mismatch')
        for artifact in [row, *row.get('artifacts', [])]:
            name = artifact['filename']
            path = directory / name
            if (Path(name).is_absolute() or '..' in Path(name).parts or path.is_symlink()
                    or not path.resolve(strict=True).is_relative_to(directory)
                    or sha(path.read_bytes()) != artifact['sha256']):
                raise ValueError('sealed prediction artifact changed')
    return sha((directory / 'SEAL.json').read_bytes())


def paired_parity(plain, traced):
    """No zero-call or incomplete pair can pass / 无调用或不完整配对不可通过。"""
    if plain is None or traced is None:
        return {'passed': False, 'reason': 'incomplete_pair'}
    calls = sum(row['phase'] == 'call' for row in plain['phase_reports'])
    def finished(result):
        selected = result['selected']
        phases = result['phase_reports']
        if (len(selected) != len(set(selected))
                or {row['nodeid'] for row in phases} != set(selected)):
            return False
        for nodeid in selected:
            rows = [row for row in phases if row['nodeid'] == nodeid]
            names = [row['phase'] for row in rows]
            if names == ['setup', 'call', 'teardown']:
                if rows[0]['outcome'] != 'passed':
                    return False
            elif names == ['setup', 'teardown']:
                if rows[0]['outcome'] not in {'failed', 'skipped'}:
                    return False
            else:
                return False
        return True
    checks = {
        'same_selected': plain['selected'] == traced['selected'],
        'same_phase_outcomes': normalized_phases(plain) == normalized_phases(traced),
        'same_exit_code': plain['pytest_exit_code'] == traced['pytest_exit_code'],
        'no_collection_errors': not plain['collection_errors'] and not traced['collection_errors'],
        'no_missing_selectors': not plain.get('missing_selectors') and not traced.get('missing_selectors'),
        'actual_calls': calls > 0,
        'complete_selected_phases': finished(plain) and finished(traced),
        'regular_pytest_exit': all(type(x['pytest_exit_code']) is int
                                   and x['pytest_exit_code'] in {0, 1} for x in (plain, traced)),
        'sources_verified': plain['source_before_after_verified'] and traced['source_before_after_verified'],
        'no_denied_operations': all(not x.get(key) for x in (plain, traced)
                                    for key in ('network_denials', 'process_denials', 'thread_denials')),
    }
    return {'passed': all(checks.values()), 'checks': checks, 'untraced_call_count': calls}


def condition_qualified(result, closure):
    """A result written before a crash is not completion / 写出结果后崩溃不等于完成。"""
    checks = {
        'closed': closure.get('closed') is True,
        'no_termination': closure.get('termination_reason') is None,
        'result_present': closure.get('result_present') is True and result is not None,
        'result_readable': closure.get('result_error') is None,
        'regular_process_exit': type(closure.get('returncode')) is int
                                and closure['returncode'] in {0, 1},
        'process_matches_pytest': result is not None and
            closure.get('returncode') == result.get('pytest_exit_code'),
        'worker_completed': result is not None and result.get('status') == 'completed',
    }
    return {'passed': all(checks.values()), 'checks': checks}


def execute_condition(python, config, output, *, wall_seconds, max_rss_mib, repository):
    """Run one fresh process; timeout/crash logs survive / 新进程运行，超时崩溃均留存。"""
    output.mkdir(mode=0o700)
    scratch = output / 'scratch'
    scratch.mkdir(mode=0o700)
    for name in ('home', 'tmp', 'cache'):
        (scratch / name).mkdir(mode=0o700)
    config = {**config, 'progress_path': str(output / 'progress.jsonl')}
    config_path, result_path = output / 'config.json', output / 'result.json'
    save(config_path, config)
    command = [str(python), '-B', '-s', '-m', 'benchmarks.semantic_observer.worker',
               '--config', str(config_path), '--output', str(result_path)]
    environment = {'PATH': str(python.parent) + os.pathsep + os.defpath,
                   'HOME': str(scratch / 'home'), 'TMPDIR': str(scratch / 'tmp'),
                   'XDG_CACHE_HOME': str(scratch / 'cache'), 'LANG': 'en_US.UTF-8',
                   'LC_ALL': 'en_US.UTF-8', 'PYTHONHASHSEED': '0',
                   'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
                   'PYTHONPATH': str(repository) + os.pathsep + str(repository / 'src'),
                   'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
                   'MKL_NUM_THREADS': '1', 'NUMEXPR_NUM_THREADS': '1'}
    started = datetime.now(timezone.utc).isoformat()
    start = time.perf_counter()
    reason, peak_kib = None, 0
    with (output / 'stdout.log').open('xb') as stdout, (output / 'stderr.log').open('xb') as stderr:
        child = subprocess.Popen(command, cwd=repository, env=environment,
                                 stdout=stdout, stderr=stderr, start_new_session=True)
        try:
            while child.poll() is None:
                elapsed = time.perf_counter() - start
                try:
                    rss = subprocess.run(['ps', '-o', 'rss=', '-p', str(child.pid)],
                                         capture_output=True, text=True, timeout=2)
                    value = rss.stdout.strip()
                    if rss.returncode == 0 and value.isdigit():
                        peak_kib = max(peak_kib, int(value))
                except subprocess.TimeoutExpired:
                    pass
                if elapsed > wall_seconds:
                    reason = 'wall_limit'
                elif peak_kib > max_rss_mib * 1024:
                    reason = 'rss_limit'
                if reason:
                    stop_child(child)
                    break
                time.sleep(0.2)
        except BaseException:
            stop_child(child)
            child.wait()
            save(output / 'INTERRUPTED.json', {'started_utc': started,
                 'state': 'controller_interrupted', 'partial_files_retained': True})
            raise
        returncode = child.wait()
    result, result_error = None, None
    if result_path.is_file():
        try:
            result = json.loads(result_path.read_bytes())
        except (ValueError, OSError) as error:
            result_error = type(error).__name__
    state = {'started_utc': started, 'command': command, 'environment': environment,
             'config_sha256': sha(canonical(config)), 'returncode': returncode,
             'termination_reason': reason, 'wall_seconds': time.perf_counter() - start,
             'sampled_peak_rss_mib': peak_kib / 1024, 'result_present': result is not None,
             'result_error': result_error, 'closed': True,
             'result_sha256': sha(result_path.read_bytes()) if result is not None else None}
    save(output / 'closure.json', state)
    for file in output.glob('*.log'):
        file.chmod(0o600)
    return state, result


def run(manifest, protocol, output, *, repository, predictions=None):
    """All selected tasks remain in the result / 保留全部已选任务，包括无法运行者。"""
    if output.exists() or output.is_symlink():
        raise ValueError('refuse existing run directory / 拒绝覆盖运行目录')
    validate_protocol(protocol, repository)
    seal_sha256 = (verify_prediction_seal(predictions, manifest, protocol)
                   if protocol.get('require_prediction_seal') else None)
    tasks = manifest.get('tasks')
    if (not isinstance(tasks, list) or not tasks
            or len({t['task_id'] for t in tasks}) != len(tasks)):
        raise ValueError('selected task list must be nonempty and distinct')
    for task in tasks:
        roles = task.get('roles', [])
        names = [role.get('role') for role in roles]
        if (len(names) != 2 or len(set(names)) != 2
                or any(type(name) is not str or not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', name)
                       for name in names)):
            raise ValueError('exactly two distinct safe source roles are required')
    output.mkdir(mode=0o700, parents=True)
    save(output / 'manifest.json', manifest)
    save(output / 'protocol.json', protocol)
    rows = []
    for index, task in enumerate(manifest['tasks']):
        role_rows = []
        for role in task['roles']:
            results = {}
            condition_checks = {}
            # Counterbalance instrumentation order without inspecting outcomes.
            order = (False, True) if index % 2 == 0 else (True, False)
            conditions = []
            for observe in order:
                validate_protocol(protocol, repository)
                if seal_sha256 is not None and verify_prediction_seal(
                        predictions, manifest, protocol) != seal_sha256:
                    raise ValueError('prediction seal changed after execution began')
                name = f'{index:03d}-{role["role"]}-' + ('traced' if observe else 'plain')
                config = {**role['config'], 'observe': observe,
                          'task_id': task['task_id'], 'role': role['role'],
                          'max_observations': protocol['max_observations'],
                          'cpu_seconds': protocol['cpu_seconds'], 'schema_version': 1}
                state, result = execute_condition(Path(task['python']), config, output / name,
                    wall_seconds=protocol['wall_seconds'], max_rss_mib=protocol['max_rss_mib'],
                    repository=repository)
                try:
                    validate_protocol(protocol, repository)
                except ValueError:
                    save(output / name / 'INVALID_SOURCE_DRIFT.json',
                         {'valid': False, 'reason': 'implementation_changed_during_condition'})
                    raise
                results[observe] = result
                condition_checks[observe] = condition_qualified(result, state)
                conditions.append({'directory': name, 'observe': observe, 'closure': state})
            parity = paired_parity(results[False], results[True])
            parity['condition_qualification'] = {
                'plain': condition_checks[False], 'traced': condition_checks[True]}
            parity['checks'] = {**parity.get('checks', {}), 'closed_regular_conditions':
                               all(x['passed'] for x in condition_checks.values())}
            parity['passed'] = parity['passed'] and parity['checks']['closed_regular_conditions']
            role_rows.append({'role': role['role'], 'conditions': conditions, 'parity': parity})
        row = {'task_id': task['task_id'], 'roles': role_rows}
        rows.append(row)
        save(output / f'task-{index:03d}.json', row)
    summary = {'schema_version': 1, 'classification': protocol['classification'],
               'tasks': rows, 'all_selected_count': len(manifest['tasks']),
               'manifest_sha256': sha(canonical(manifest)),
               'protocol_sha256': sha(canonical(protocol)),
               'prediction_seal_sha256': seal_sha256,
               'new_generated_repairs': False, 'mature_research_established': False}
    save(output / 'summary.json', summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True, help='Reviewed frozen task manifest / 固定任务清单')
    parser.add_argument('--protocol', type=Path, required=True, help='Frozen execution protocol / 固定执行协议')
    parser.add_argument('--output', type=Path, required=True, help='New private run directory / 新私人运行目录')
    parser.add_argument('--predictions', type=Path, help='Previously sealed prediction directory / 已封存预测目录')
    args = parser.parse_args(argv)
    result = run(json.loads(args.manifest.read_bytes()), json.loads(args.protocol.read_bytes()),
                 args.output.resolve(), repository=Path(__file__).resolve().parents[2],
                 predictions=args.predictions)
    print(json.dumps({'all_selected_tasks': result['all_selected_count'],
                      'summary': str(args.output / 'summary.json')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
