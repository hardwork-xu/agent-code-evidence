"""Unit-test synthetic ledger records; no upstream imports or execution."""
from copy import deepcopy

import pytest

from benchmarks.known_task_execution.contract import digest, evaluate_pair, resolve, selector, selector_manifest


@pytest.mark.parametrize('metadata, expected', [
    ('tests/cache.py:None:test_cache', 'tests/cache.py::test_cache'),
    ('tests/models.py:ModelTest:test_cache', 'tests/models.py::ModelTest::test_cache'),
    ('tests/models.py:ModelTest:test_cache[one:two]', 'tests/models.py::ModelTest::test_cache[one:two]'),
    ('tests/models.py:ModelTest:test_cache2', 'tests/models.py::ModelTest::test_cache2'),
])
def test_candidate_selector_preserves_exact_parameterized_or_generated_names(metadata, expected):
    assert selector(metadata)['selector'] == expected
    assert selector(metadata)['status'] == 'awaiting_actual_collection'
    assert resolve(metadata, {expected})['status'] == 'collected_exactly'


@pytest.mark.parametrize('metadata', [':testRepr:', ':testEquals', 'x.py:None:',
    '../x.py:None:test_x', '/x.py:None:test_x', 'x.py:Nested.Class:test_x',
    'x.py:None:bad-name', 'x.py:None:test_x[unclosed', 'x.py:None:test_x\0'])
def test_ambiguous_or_unsafe_metadata_never_guesses_a_selector(metadata):
    assert selector(metadata)['status'] == 'metadata_ambiguous'
    assert selector(metadata)['selector'] is None


def test_parameter_suffix_and_inheritance_have_no_fuzzy_fallback():
    assert resolve('tests/x.py:C:test_x2', {'tests/x.py::C::test_x[2]'})['status'] == 'not_collected'
    assert resolve('tests/x.py:Derived:test_x', {'tests/x.py::Base::test_x'})['status'] == 'not_collected'


def records():
    task = {'instance_id': 'synthetic-1', 'base_commit': 'a' * 40,
            'test_patch_sha256': 'b' * 64, 'code_patch_sha256': 'c' * 64,
            'f2p_units': 1, 'p2p_units': 1,
            'test_units': [{'kind': 'F2P', 'metadata_id': 'tests/x.py:None:test_fix'},
                           {'kind': 'P2P', 'metadata_id': 'tests/x.py:C:test_unchanged'}]}
    before = {'schema_version': 1, 'role': 'base', 'instance_id': 'synthetic-1',
              'base_commit': 'a' * 40, 'test_patch_sha256': 'b' * 64,
              'code_patch_sha256': None, 'environment_sha256': 'd' * 64,
              'collection_status': 'complete', 'runner_status': 'completed', 'process_exit_code': 1,
              'collected': ['tests/x.py::test_fix', 'tests/x.py::C::test_unchanged'],
              'collected_all': ['tests/x.py::test_fix', 'tests/x.py::C::test_unchanged'],
              'selected': ['tests/x.py::test_fix', 'tests/x.py::C::test_unchanged'], 'deselected': [],
              'results': [{'nodeid': 'tests/x.py::test_fix', 'state': 'failed',
                           'phase': 'call', 'kind': 'behavior'},
                          {'nodeid': 'tests/x.py::C::test_unchanged', 'state': 'passed',
                           'phase': 'call', 'kind': 'behavior'}]}
    after = deepcopy(before)
    after['role'] = 'gold'
    after['process_exit_code'] = 0
    after['code_patch_sha256'] = 'c' * 64
    after['results'][0]['state'] = 'passed'
    return task, before, after


def test_finite_before_failure_after_pass_with_p2p_is_qualified_not_own_repair():
    task, before, after = records()
    outcome = evaluate_pair(task, before, after)
    assert outcome['qualified']
    assert outcome['unit_denominators'] == {'F2P': 1, 'P2P': 1}
    assert outcome['unit_reproduced'] == {'F2P': 1, 'P2P': 1}
    assert 'not a generated repair' in outcome['limits']


@pytest.mark.parametrize('state', ['skipped', 'error', 'not_run', 'timeout', 'blocked'])
def test_gold_skips_or_operational_failures_cannot_be_passes(state):
    task, before, after = records()
    after['results'][0]['state'] = state
    assert not evaluate_pair(task, before, after)['qualified']


@pytest.mark.parametrize('phase, kind', [('setup', 'behavior'), ('call', 'dependency'),
                                       ('call', 'network'), ('call', 'resource'),
                                       ('collection', 'framework')])
def test_administrative_baseline_failure_is_not_f2p_evidence(phase, kind):
    task, before, after = records()
    before['results'][0].update(phase=phase, kind=kind)
    assert not evaluate_pair(task, before, after)['qualified']


def test_all_p2p_required_and_missing_outcome_kept_unknown():
    task, before, after = records()
    after['results'][1]['state'] = 'failed'
    assert not evaluate_pair(task, before, after)['qualified']
    after['results'].pop()
    outcome = evaluate_pair(task, before, after)
    assert not outcome['qualified']
    assert outcome['unit_denominators']['P2P'] == 1
    assert outcome['units'][1]['gold'] is None


def test_metadata_only_source_id_change_is_not_behavioral_change():
    task, before, after = records()
    # With identical behavior on both branches the declared F2P does not reproduce,
    # even if snapshot IDs differ. Such a control cannot be called a semantic fix.
    before['results'][0]['state'] = 'passed'
    before['snapshot_id'] = 'metadata-one'
    after['snapshot_id'] = 'metadata-two'
    assert not evaluate_pair(task, before, after)['qualified']


def test_metadata_ambiguity_stays_in_denominator_without_suffix_matching():
    task, before, after = records()
    task['test_units'][0]['metadata_id'] = ':test_fix:'
    outcome = evaluate_pair(task, before, after)
    assert outcome['unit_denominators']['F2P'] == 1
    assert not outcome['qualified']
    assert outcome['units'][0]['base_mapping']['status'] == 'metadata_ambiguous'


def test_different_environments_and_incomplete_collection_block_qualification():
    task, before, after = records()
    after['environment_sha256'] = 'e' * 64
    assert not evaluate_pair(task, before, after)['qualified']
    after['environment_sha256'] = before['environment_sha256']
    after['collection_status'] = 'error'
    assert not evaluate_pair(task, before, after)['qualified']


@pytest.mark.parametrize('mutation', [
    lambda task, before, after: after.update(test_patch_sha256='0' * 64),
    lambda task, before, after: after.update(base_commit='0' * 40),
    lambda task, before, after: before.update(code_patch_sha256=task['code_patch_sha256']),
    lambda task, before, after: task.update(f2p_units=0),
    lambda task, before, after: after['results'].append(deepcopy(after['results'][0])),
])
def test_source_provenance_and_row_denominator_tampering_are_rejected(mutation):
    task, before, after = records()
    mutation(task, before, after)
    with pytest.raises(ValueError):
        evaluate_pair(task, before, after)


def test_nonmetadata_outcomes_are_retained_and_operational_errors_block():
    task, before, after = records()
    after['collected'].append('tests/x.py::test_extra')
    after['collected_all'].append('tests/x.py::test_extra')
    after['selected'].append('tests/x.py::test_extra')
    after['results'].append({'nodeid': 'tests/x.py::test_extra', 'state': 'error',
                             'phase': 'setup', 'kind': 'dependency'})
    outcome = evaluate_pair(task, before, after)
    assert not outcome['qualified']
    assert len(outcome['all_execution_outcomes']['gold']) == 3
    assert outcome['all_outcome_counts']['gold']['error'] == 1


@pytest.mark.parametrize('exit_code', [1, 2, 3, 4, 5, -9])
def test_gold_nonzero_exit_blocks_even_when_every_selected_test_passed(exit_code):
    task, before, after = records()
    after['process_exit_code'] = exit_code
    outcome = evaluate_pair(task, before, after)
    assert not outcome['qualified']
    assert not outcome['gold_process_successful']
    assert outcome['unit_reproduced'] == {'F2P': 1, 'P2P': 1}


@pytest.mark.parametrize('exit_code', [0, 2, 3, 4, 5, -9])
def test_baseline_process_exit_must_match_actual_behavior_failure(exit_code):
    task, before, after = records()
    before['process_exit_code'] = exit_code
    assert not evaluate_pair(task, before, after)['qualified']


@pytest.mark.parametrize('role', ['base', 'gold'])
@pytest.mark.parametrize('status', ['blocked', 'timeout', 'crashed'])
def test_incomplete_runner_retains_observations_without_qualifying(role, status):
    task, before, after = records()
    record = before if role == 'base' else after
    record.update(runner_status=status, process_exit_code=None)
    outcome = evaluate_pair(task, before, after)
    assert not outcome['qualified']
    assert not outcome['both_runners_completed']
    assert len(outcome['all_execution_outcomes'][role]) == 2


@pytest.mark.parametrize('role, index', [('gold', 0), ('gold', 1), ('base', 1)])
@pytest.mark.parametrize('phase', ['setup', 'teardown', 'collection', 'not_run'])
def test_setup_teardown_or_collection_pass_is_not_actual_call_pass(role, index, phase):
    task, before, after = records()
    record = before if role == 'base' else after
    record['results'][index]['phase'] = phase
    assert not evaluate_pair(task, before, after)['qualified']


@pytest.mark.parametrize('role', ['base', 'gold'])
@pytest.mark.parametrize('state', ['skipped', 'error', 'not_run', 'xfailed', 'xpassed'])
def test_absence_of_p2p_failure_is_not_an_observed_p2p_pass(role, state):
    task, before, after = records()
    record = before if role == 'base' else after
    record['results'][1]['state'] = state
    outcome = evaluate_pair(task, before, after)
    # Empty intersection with "failed" would accept this P2P observation.
    # This independently authored contract requires actual call-phase passes.
    assert outcome['all_outcome_counts'][role].get('failed', 0) == (1 if role == 'base' else 0)
    assert not outcome['qualified']
    assert outcome['unit_denominators']['P2P'] == 1


@pytest.mark.parametrize('role', ['base', 'gold'])
def test_empty_results_never_qualify_and_missing_nodes_remain_visible(role):
    task, before, after = records()
    record = before if role == 'base' else after
    record['results'] = []
    outcome = evaluate_pair(task, before, after)
    assert not outcome['qualified']
    assert not outcome['both_outcomes_complete']
    assert outcome['missing_outcomes'][role] == record['collected']


def test_unreported_nonmetadata_collected_test_blocks_complete_result_claim():
    task, before, after = records()
    after['collected'].append('tests/x.py::test_missing')
    after['collected_all'].append('tests/x.py::test_missing')
    after['selected'].append('tests/x.py::test_missing')
    outcome = evaluate_pair(task, before, after)
    assert not outcome['qualified']
    assert outcome['missing_outcomes']['gold'] == ['tests/x.py::test_missing']
    assert outcome['unit_reproduced'] == {'F2P': 1, 'P2P': 1}


@pytest.mark.parametrize('mutation', [
    lambda record: record.pop('runner_status'),
    lambda record: record.pop('process_exit_code'),
    lambda record: record.update(process_exit_code=True),
    lambda record: record.update(runner_status='completed', process_exit_code=None),
    lambda record: record.update(runner_status='timeout', process_exit_code=0),
    lambda record: record.update(results=None),
    lambda record: record.update(collected=['tests/x.py::test_fix', 1]),
])
def test_malformed_runner_or_result_records_are_rejected(mutation):
    task, before, after = records()
    mutation(after)
    with pytest.raises(ValueError):
        evaluate_pair(task, before, after)


def test_deselected_unrelated_tests_need_no_outcome_and_scope_stays_finite():
    task, before, after = records()
    for record in (before, after):
        record['collected_all'].append('tests/x.py::test_unrelated_live_service')
        record['deselected'].append('tests/x.py::test_unrelated_live_service')
    outcome = evaluate_pair(task, before, after)
    assert outcome['qualified']
    assert outcome['both_outcomes_complete']
    assert len(outcome['all_execution_outcomes']['gold']) == 2
    assert outcome['collection_partitions']['gold']['deselected'] == [
        'tests/x.py::test_unrelated_live_service']


@pytest.mark.parametrize('mutation', [
    lambda record: record.pop('collected_all'),
    lambda record: record['deselected'].append(record['selected'][0]),
    lambda record: record['collected_all'].pop(),
    lambda record: record['selected'].pop(),
    lambda record: record['collected_all'].append(record['collected_all'][0]),
])
def test_actual_collection_partition_provenance_cannot_be_guessed_or_tampered(mutation):
    task, before, after = records()
    mutation(after)
    with pytest.raises(ValueError):
        evaluate_pair(task, before, after)


def explicit_alias_records():
    task, before, after = records()
    task['test_units'][0]['metadata_id'] = ':test_fix:'
    task['pathless_aliases'] = {':test_fix:': {
        'canonical_selector': 'tests/x.py::test_fix', 'source_path': 'tests/x.py',
        'source_sha256': 'e' * 64, 'class': 'None', 'method': 'test_fix'}}
    for record in (before, after):
        record['pathless_aliases_sha256'] = digest(task['pathless_aliases'])
    return task, before, after


def test_explicit_pathless_alias_is_source_bound_and_requires_actual_collection():
    task, before, after = explicit_alias_records()
    outcome = evaluate_pair(task, before, after)
    assert outcome['qualified']
    unit = outcome['units'][0]
    assert unit['metadata_id'] == ':test_fix:'
    assert unit['base_mapping']['mapping_kind'] == 'explicit_source_alias'
    assert unit['base_mapping']['source_sha256'] == 'e' * 64
    assert resolve(':test_fix:', set(), task['pathless_aliases'])['status'] == 'not_collected'
    assert resolve(':test_fix:', {'tests/x.py::test_fix2'}, task['pathless_aliases'])['status'] == 'not_collected'


@pytest.mark.parametrize('metadata', [':test_fix', ':test_fix:'])
def test_explicit_alias_supports_only_exact_identifier_without_guessing(metadata):
    task, _, _ = explicit_alias_records()
    alias = {metadata: task['pathless_aliases'][':test_fix:']}
    assert selector(metadata, alias)['selector'] == 'tests/x.py::test_fix'
    assert selector(metadata, alias)['status'] == 'awaiting_actual_collection'


@pytest.mark.parametrize('mutation', [
    lambda aliases: aliases[':test_fix:'].update(method='test_fix2'),
    lambda aliases: aliases[':test_fix:'].update(canonical_selector='tests/x.py::test_fix2'),
    lambda aliases: aliases[':test_fix:'].update(source_path='../x.py'),
    lambda aliases: aliases[':test_fix:'].update(source_sha256='e' * 63),
    lambda aliases: aliases[':test_fix:'].update(**{'class': 'Nested.Class'}),
    lambda aliases: aliases.update({'tests/x.py:None:test_fix': aliases.pop(':test_fix:')}),
    lambda aliases: aliases.update({':test_fix[1]:': aliases.pop(':test_fix:')}),
    lambda aliases: aliases.update({':test_fix_suffix:': aliases.pop(':test_fix:')}),
])
def test_alias_cannot_override_regular_label_or_change_exact_method_or_source(mutation):
    task, before, after = explicit_alias_records()
    mutation(task['pathless_aliases'])
    for record in (before, after):
        record['pathless_aliases_sha256'] = digest(task['pathless_aliases'])
    with pytest.raises(ValueError):
        evaluate_pair(task, before, after)


@pytest.mark.parametrize('role', ['base', 'gold'])
@pytest.mark.parametrize('missing', [True, False])
def test_alias_digest_is_bound_to_both_role_records(role, missing):
    task, before, after = explicit_alias_records()
    record = before if role == 'base' else after
    if missing:
        record.pop('pathless_aliases_sha256')
    else:
        record['pathless_aliases_sha256'] = 'f' * 64
    with pytest.raises(ValueError):
        evaluate_pair(task, before, after)


def test_alias_mapping_metadata_change_is_not_behavioral_success():
    task, before, after = explicit_alias_records()
    before['results'][0]['state'] = 'passed'
    before['process_exit_code'] = 0
    assert not evaluate_pair(task, before, after)['qualified']


def test_two_original_alias_labels_cannot_inflate_one_canonical_test():
    task, before, after = explicit_alias_records()
    task['test_units'].append({'kind': 'F2P', 'metadata_id': ':test_fix'})
    task['f2p_units'] += 1
    task['pathless_aliases'][':test_fix'] = deepcopy(task['pathless_aliases'][':test_fix:'])
    for record in (before, after):
        record['pathless_aliases_sha256'] = digest(task['pathless_aliases'])
    with pytest.raises(ValueError):
        evaluate_pair(task, before, after)


def test_selector_manifest_retains_original_alias_and_never_claims_collection():
    task, _, _ = explicit_alias_records()
    result = selector_manifest({'tasks': [task]})
    assert result['upstream_code_executed'] is False
    assert result['statuses'] == {'awaiting_actual_collection': 2}
    assert result['rows'][0]['metadata_id'] == ':test_fix:'
    assert result['rows'][0]['mapping_kind'] == 'explicit_source_alias'
    assert result['rows'][0]['pathless_aliases_sha256'] == digest(task['pathless_aliases'])
