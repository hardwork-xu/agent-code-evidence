"""Execution qualification counterexamples / 执行配对资格反例。"""
from copy import deepcopy

import pytest

from benchmarks.semantic_observer.run import (
    paired_parity, validate_protocol, verify_prediction_seal, save, sha, canonical,
)
from benchmarks.semantic_observer.worker import ThreadGuard, safe_relative, reviewed_pytest_args


def recorded(outcome='passed'):
    return {'status': 'completed', 'selected': ['test_real.py::test_case'], 'pytest_exit_code': int(outcome == 'failed'),
            'phase_reports': [{'nodeid': 'test_real.py::test_case', 'phase': 'setup',
                              'outcome': 'passed', 'wasxfail': False, 'error_type': None, 'seconds': 0},
                             {'nodeid': 'test_real.py::test_case', 'phase': 'call',
                              'outcome': outcome, 'wasxfail': False,
                              'error_type': 'AssertionError' if outcome == 'failed' else None,
                              'seconds': 1},
                             {'nodeid': 'test_real.py::test_case', 'phase': 'teardown',
                              'outcome': 'passed', 'wasxfail': False, 'error_type': None, 'seconds': 0}],
            'collection_errors': [], 'source_before_after_verified': True,
            'network_denials': [], 'process_denials': [], 'thread_denials': 0}


@pytest.mark.parametrize('outcome', ['passed', 'failed'])
def test_real_test_failure_may_preserve_trace_parity(outcome):
    before = recorded(outcome)
    after = deepcopy(before)
    after['phase_reports'][0]['seconds'] = 500
    assert paired_parity(before, after)['passed']


def test_zero_calls_are_not_validation():
    row = recorded()
    row['phase_reports'] = []
    assert not paired_parity(row, row)['passed']
    assert not paired_parity(None, row)['passed']


@pytest.mark.parametrize('key,value', [('collection_errors', ['error']),
                                     ('missing_selectors', ['absent']),
                                     ('network_denials', ['denied']),
                                     ('process_denials', ['denied']),
                                     ('thread_denials', 1),
                                     ('source_before_after_verified', False)])
def test_resource_and_identity_failures_retained(key, value):
    plain, traced = recorded(), recorded()
    traced[key] = value
    assert not paired_parity(plain, traced)['passed']


def test_changed_assertion_outcome_cannot_pass():
    assert not paired_parity(recorded(), recorded('failed'))['passed']
    row = recorded()
    row['phase_reports'][0]['wasxfail'] = True
    assert not paired_parity(recorded(), row)['passed']


@pytest.mark.parametrize('name', ['../a.py', '/a.py', 'a/../b.py', 'a//b.py', 'a\\b.py', 'a:b.py', ''])
def test_source_path_rejects_escape(name):
    with pytest.raises(ValueError):
        safe_relative(name)


def test_thread_guards_restore_after_exception():
    import _thread
    import threading
    old_start, old_low = threading.Thread.start, _thread.start_new_thread
    with pytest.raises(RuntimeError, match='single-thread'):
        with ThreadGuard() as guard:
            threading.Thread(target=lambda: None).start()
    assert guard.denied == 1
    assert threading.Thread.start is old_start
    assert _thread.start_new_thread is old_low


def test_unbound_worker_source_is_rejected(tmp_path):
    with pytest.raises(ValueError, match='implementation'):
        validate_protocol({}, tmp_path)


def test_original_warning_policy_and_pinned_plugin_are_explicit():
    assert reviewed_pytest_args({'dependency_versions': {}}) == []
    assert reviewed_pytest_args({'pytest_plugins': ['pytest_mock.plugin'],
                                'pytest_warning_filters': ['error'],
                                'dependency_versions': {'pytest-mock': '3.14.0'}}) == [
                                    '-p', 'pytest_mock.plugin', '-W', 'error']
    with pytest.raises(ValueError, match='version pin'):
        reviewed_pytest_args({'pytest_plugins': ['pytest_mock.plugin'], 'dependency_versions': {}})
    with pytest.raises(ValueError, match='unreviewed'):
        reviewed_pytest_args({'pytest_plugins': ['unreviewed_target_plugin'], 'dependency_versions': {}})
    with pytest.raises(ValueError, match='warning'):
        reviewed_pytest_args({'pytest_warning_filters': ['ignore'], 'dependency_versions': {}})


def test_prediction_seal_requires_all_tasks_and_current_bytes(tmp_path):
    manifest = {'tasks': [{'task_id': 'owned'}]}
    protocol = {'implementation_sha256': {'owned.py': 'a' * 64}}
    task_path = tmp_path / 'task-000.json'
    save(task_path, {'status': 'failed', 'failure': 'failure still retained'})
    row = {'task_id': 'owned', 'filename': task_path.name,
           'task_config_sha256': sha(canonical(manifest['tasks'][0])),
           'sha256': sha(task_path.read_bytes()), 'artifacts': []}
    seal = {'manifest_sha256': sha(canonical(manifest)),
            'protocol_sha256': sha(canonical(protocol)),
            'implementation_sha256': protocol['implementation_sha256'],
            'implementation_unchanged': True, 'all_selected_rows_sealed': True,
            'all_selected_count': 1, 'rows': [row]}
    save(tmp_path / 'SEAL.json', seal)
    assert verify_prediction_seal(tmp_path, manifest, protocol)
    with pytest.raises(ValueError, match='complete experiment'):
        verify_prediction_seal(tmp_path, {'tasks': []}, protocol)
    task_path.write_text('altered prediction')
    with pytest.raises(ValueError, match='artifact changed'):
        verify_prediction_seal(tmp_path, manifest, protocol)
    with pytest.raises(ValueError, match='requires'):
        verify_prediction_seal(None, manifest, protocol)


# Independent pre-unseal integrity controls / 解封前的独立完整性反例。
def complete_owned_result():
    value = recorded()
    call = next(row.copy() for row in value['phase_reports'] if row['phase'] == 'call')
    value.update({'status': 'completed', 'task_id': 'owned', 'role': 'base_tests',
                  'config_sha256': 'a' * 64, 'source_tree_sha256': 'b' * 64,
                  'missing_selectors': []})
    value['phase_reports'] = [
        {**call, 'phase': 'setup', 'outcome': 'passed', 'wasxfail': False, 'error_type': None},
        call,
        {**call, 'phase': 'teardown', 'outcome': 'passed', 'wasxfail': False, 'error_type': None}]
    return value


def complete_owned_closure(result):
    return {'closed': True, 'returncode': result['pytest_exit_code'],
            'termination_reason': None, 'result_present': True, 'result_error': None,
            'config_sha256': result['config_sha256'],
            'result_sha256': sha(canonical(result) + b'\n')}


@pytest.mark.parametrize('limit', ['wall_limit', 'rss_limit'])
def test_written_result_cannot_override_controller_resource_termination(limit):
    from benchmarks.semantic_observer import run as runner
    result = complete_owned_result()
    closure = complete_owned_closure(result)
    closure['termination_reason'] = limit
    # Even equal apparent exit codes cannot erase a recorded resource violation.
    assert not runner.condition_qualified(result, closure)['passed']


def test_written_result_cannot_override_actual_process_exit_mismatch():
    from benchmarks.semantic_observer import run as runner
    result = complete_owned_result()
    closure = complete_owned_closure(result)
    closure['returncode'] = -9
    assert not runner.condition_qualified(result, closure)['passed']


@pytest.mark.parametrize('mutation', ['open', 'missing', 'parse_error'])
def test_unclosed_or_unreadable_condition_never_qualifies(mutation):
    from benchmarks.semantic_observer import run as runner
    result = complete_owned_result()
    closure = complete_owned_closure(result)
    if mutation == 'open':
        closure['closed'] = False
    elif mutation == 'missing':
        closure['result_present'] = False
    else:
        closure['result_error'] = 'JSONDecodeError'
    assert not runner.condition_qualified(result, closure)['passed']


@pytest.mark.parametrize('code', [2, 3, 4, 5, -9])
def test_equal_internal_or_interrupted_pytest_exits_do_not_qualify_as_parity(code):
    value = complete_owned_result()
    value['pytest_exit_code'] = code
    assert not paired_parity(value, deepcopy(value))['passed']


@pytest.mark.parametrize('mutation', ['silent_selected', 'unselected_call', 'duplicate_call',
                                      'missing_setup', 'missing_teardown'])
def test_equal_incomplete_or_foreign_phase_panels_are_not_qualified(mutation):
    value = complete_owned_result()
    if mutation == 'silent_selected':
        value['selected'].append('test_real.py::never_started')
    elif mutation == 'unselected_call':
        for phase in value['phase_reports']:
            phase['nodeid'] = 'test_real.py::not_selected'
    elif mutation == 'duplicate_call':
        value['phase_reports'].insert(2, value['phase_reports'][1].copy())
    elif mutation == 'missing_setup':
        value['phase_reports'] = [row for row in value['phase_reports'] if row['phase'] != 'setup']
    elif mutation == 'missing_teardown':
        value['phase_reports'] = [row for row in value['phase_reports'] if row['phase'] != 'teardown']
    assert not paired_parity(value, deepcopy(value))['passed']


def test_complete_original_failure_and_original_setup_skip_can_preserve_parity():
    from benchmarks.semantic_observer import run as runner
    value = complete_owned_result()
    value['pytest_exit_code'] = 1
    value['phase_reports'][1].update({'outcome': 'failed', 'error_type': 'AssertionError'})
    skipped = 'test_real.py::original_skip'
    value['selected'].append(skipped)
    value['phase_reports'].extend([
        {'nodeid': skipped, 'phase': 'setup', 'outcome': 'skipped', 'wasxfail': False,
         'error_type': None, 'seconds': 0.0},
        {'nodeid': skipped, 'phase': 'teardown', 'outcome': 'passed', 'wasxfail': False,
         'error_type': None, 'seconds': 0.0}])
    assert paired_parity(value, deepcopy(value))['passed']
    assert runner.condition_qualified(value, complete_owned_closure(value))['passed']
