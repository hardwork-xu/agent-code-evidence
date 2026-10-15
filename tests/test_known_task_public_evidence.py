"""Owned bookkeeping fixtures only; never import or execute upstream projects.

Synthetic 39/87/5842 counts exercise the fixed export contract. They are not
observations or scientific evidence. / 自编计数仅验证导出判据，不代表实测结果。
"""
from collections import Counter
import copy
import hashlib
import io
import json
from pathlib import Path

import pytest

from benchmarks.known_task_execution import contract
from benchmarks.known_task_execution import public_check as checker
from benchmarks.known_task_execution import transport
from benchmarks.known_task_execution import report


def test_bounded_read_limits_the_actual_read_instead_of_prior_stat(monkeypatch):
    requests = []

    class OwnedStream(io.BytesIO):
        def read(self, size=-1):
            requests.append(size)
            return super().read(size)

    monkeypatch.setattr(Path, 'open', lambda *a, **k: OwnedStream(b'12345'))
    with pytest.raises(ValueError, match='owned exceeds read cap'):
        checker.read_bounded('owned', 3, 'owned')
    assert requests == [4]


def test_transport_bounds_index_before_hash_or_json(tmp_path, monkeypatch):
    (tmp_path / 'INDEX.json').write_bytes(b'x' * 9)
    monkeypatch.setattr(transport, 'MAX_INDEX', 8)
    with pytest.raises(ValueError, match='index exceeds read cap'):
        transport.verify(tmp_path, 'a' * 64, contract)


def test_transport_bounds_actual_compressed_read(tmp_path, monkeypatch):
    (tmp_path / 'part.gz').write_bytes(b'x' * 9)
    monkeypatch.setattr(transport, 'MAX_PART', 8)
    with pytest.raises(ValueError, match='compressed part exceeds read cap'):
        transport.decode(tmp_path, {'name': 'part.gz'})


def digest(value):
    return hashlib.sha256(checker.canonical(value)).hexdigest()


def refresh_counts(evidence):
    conditions = evidence['conditions']
    evidence['latest_status_counts'] = dict(Counter(t['status'] for t in evidence['tasks']))
    evidence['coverage_counts'] = {
        'tasks': 39, 'complete_pair_conditions': len(conditions),
        'qualified_conditions': sum(c['qualified'] for c in conditions),
        'latest_qualified_tasks': evidence['latest_status_counts'].get('finite_qualified', 0),
        'selected_role_outcomes': sum(len(r['effective_record']['results'])
            for c in conditions for r in c['roles'].values()),
        'phase_reports': sum(len(r['effective_record']['phase_reports'])
            for c in conditions for r in c['roles'].values()),
        'partial_conditions_with_retained_records': len(evidence['partial_conditions']),
        'partial_progress_phase_reports': sum(p['observed_phase_report_count']
            for p in evidence['partial_conditions']),
    }


def owned_condition(task, run_id='owned-first', freeze='2026-10-15T00:00:00Z'):
    units = [{'kind': kind, 'metadata_id': label}
        for kind in ['F2P', 'P2P'] for label in task['original_labels'][kind]]
    spec = dict(task, f2p_units=task['original_F2P'], p2p_units=task['original_P2P'],
                pathless_aliases={}, test_units=units)
    node = contract.selector(units[0]['metadata_id'])['selector']
    roles = {}
    for role in ['base', 'gold']:
        reports = []
        for phase in ['setup', 'call', 'teardown']:
            failed = role == 'base' and phase == 'call'
            reports.append({'nodeid': node, 'phase': phase,
                'state': 'failed' if failed else 'passed', 'kind': 'behavior',
                'raw_outcome': 'failed' if failed else 'passed', 'wasxfail': False,
                'strict_xpass': False, 'error_type': 'AssertionError' if failed else None,
                'seconds': 0.0})
        roles[role] = {'schema_version': 1, 'instance_id': task['instance_id'],
            'role': role, 'base_commit': task['base_commit'],
            'code_patch_sha256': task['code_patch_sha256'] if role == 'gold' else None,
            'test_patch_sha256': task['test_patch_sha256'],
            'pathless_aliases_sha256': contract.digest({}),
            'environment_sha256': 'e' * 64, 'collection_status': 'complete',
            'runner_status': 'completed', 'process_exit_code': 1 if role == 'base' else 0,
            'collected_all': [node], 'collected': [node], 'selected': [node],
            'deselected': [], 'results': [copy.deepcopy(reports[1])],
            'phase_reports': reports}
    qualification = contract.evaluate_pair(spec, roles['base'], roles['gold'])
    protocol_sha = 'd' * 64
    return {'instance_id': task['instance_id'], 'run_id': run_id,
        'condition_key': digest([task['instance_id'], run_id, protocol_sha]),
        'protocol_sha256': protocol_sha, 'protocol_created_utc': freeze,
        'adapter_program_commitments': [{'kind': 'contract', 'sha256': checker.CONTRACT_SHA256}],
        'environment': {'sha256': 'e' * 64},
        'protocol_binding_checks': {role: {'environment_fingerprint_matches_protocol': True}
            for role in roles},
        'qualification': qualification, 'qualified': qualification['qualified'],
        'unit_denominators': qualification['unit_denominators'],
        'unit_reproduced': qualification['unit_reproduced'],
        'roles': {role: {'effective_record': record} for role, record in roles.items()}}


@pytest.fixture
def evidence():
    tasks = []
    for i in range(39):
        fp, pp = (49, 5842) if i == 0 else (1, 0)
        labels = {kind: [f'test_owned.py:None:test_{kind.lower()}_{j}' for j in range(count)]
            for kind, count in [('F2P', fp), ('P2P', pp)]}
        tasks.append({'instance_id': f'owned-{i}', 'original_F2P': fp, 'original_P2P': pp,
            'original_labels': labels, 'base_commit': 'a' * 40,
            'code_patch_sha256': 'b' * 64, 'test_patch_sha256': 'c' * 64,
            'condition_keys': [], 'status': 'no_completed_target_pair',
            'latest_declared_condition_run_id': None})
    condition = owned_condition(tasks[1])
    tasks[1].update(condition_keys=[condition['condition_key']], status='finite_qualified',
                    latest_declared_condition_run_id=condition['run_id'])
    value = {'schema_version': 1, 'original_denominator': {'tasks': 39, 'F2P': 87, 'P2P': 5842},
        'tasks': tasks, 'conditions': [condition],
        'research_claims': dict.fromkeys(['holdout', 'mature', 'generated_repair_success',
            'necessary_context', 'model_quality_improvement', 'official_harness_score',
            'independent_SUT_replication_by_exporter'], False),
        'partial_conditions': [{'instance_id': 'owned-2', 'qualification': None,
            'structured_progress': [{'events': [{'event': 'phase_report'} for _ in range(3)]}],
            'observed_phase_report_count': 3}]}
    refresh_counts(value)
    return value


def test_owned_full_denominator_recomputes(evidence):
    result = checker.check(evidence, contract)
    assert result['qualified_conditions'] == 1
    assert result['phase_reports_checked'] == 6
    assert result['partial_conditions_not_qualified'] == 1


@pytest.mark.parametrize('reproduced', [{'F2P': 1}, {}])
@pytest.mark.parametrize('language', ['en', 'zh'])
def test_result_table_retains_zero_pp_and_zero_reproduced_negative(evidence, reproduced, language):
    evidence['snapshot_recorded_utc'] = '2026-10-15T00:00:00Z'
    evidence['conditions'][0]['unit_reproduced'] = reproduced
    text = report.render(evidence, 'a' * 64, language)
    expected_fp = reproduced.get('F2P', 0)
    assert f'| `owned-1` | {expected_fp}/1 | 0/0 |' in text
    assert '| `owned-0` | 0/49 | 0/5842 |' in text


def test_removing_all_observed_phases_is_not_vacuously_valid(evidence):
    evidence['conditions'][0]['roles']['base']['effective_record']['phase_reports'] = []
    refresh_counts(evidence)
    with pytest.raises(ValueError, match='lacks phase evidence'):
        checker.check(evidence, contract)


def test_condition_membership_cannot_move_to_other_task(evidence):
    evidence['tasks'][2]['condition_keys'] = evidence['tasks'][1]['condition_keys']
    evidence['tasks'][1]['condition_keys'] = []
    with pytest.raises(ValueError, match='different task'):
        checker.check(evidence, contract)


def test_recounting_fabricated_latest_status_does_not_validate_it(evidence):
    evidence['tasks'][2]['status'] = 'finite_qualified'
    refresh_counts(evidence)
    with pytest.raises(ValueError, match='most-recent'):
        checker.check(evidence, contract)


def test_partial_condition_cannot_claim_qualification(evidence):
    evidence['partial_conditions'][0]['qualification'] = {'qualified': True}
    with pytest.raises(ValueError, match='partial condition cannot'):
        checker.check(evidence, contract)


@pytest.mark.parametrize('replacement', [{}, {'mature': False}])
def test_research_claim_guard_cannot_disappear(evidence, replacement):
    evidence['research_claims'] = replacement
    with pytest.raises(ValueError, match='research claim guard'):
        checker.check(evidence, contract)


def test_only_hash_checked_contract_bytes_are_executed(tmp_path, monkeypatch):
    approved = Path(contract.__file__).read_bytes()
    assert hashlib.sha256(approved).hexdigest() == checker.CONTRACT_SHA256
    path = tmp_path / 'approved.py'
    path.write_bytes(approved)
    read_bytes = Path.read_bytes
    bounded_read = checker.read_bounded

    def swap_after_read(target, limit, label):
        raw = bounded_read(target, limit, label)
        if target == path:
            path.write_text('OWNED_SWAPPED_SOURCE = True\n', encoding='utf8')
        return raw

    monkeypatch.setattr(checker, 'read_bounded', swap_after_read)
    loaded = checker.load_contract(path)
    assert callable(loaded.evaluate_pair)
    assert not getattr(loaded, 'OWNED_SWAPPED_SOURCE', False)
    assert read_bytes(path) == b'OWNED_SWAPPED_SOURCE = True\n'


@pytest.mark.parametrize('bad', ['', None, '2026-10-15T00:00:00',
    '2026-10-15T08:00:00+08:00', '2026-02-30T00:00:00Z'])
def test_invalid_or_empty_declared_utc_rejected(evidence, bad):
    evidence['conditions'][0]['protocol_created_utc'] = bad
    with pytest.raises(ValueError, match='UTC'):
        checker.check(evidence, contract)


def test_latest_order_uses_utc_value_not_fraction_string_order(evidence):
    task = evidence['tasks'][1]
    later = owned_condition(task, run_id='owned-later', freeze='2026-10-15T00:00:00.9Z')
    evidence['conditions'].insert(0, later)
    task['condition_keys'].append(later['condition_key'])
    task['latest_declared_condition_run_id'] = later['run_id']
    refresh_counts(evidence)
    assert checker.check(evidence, contract)['finite_qualifications_recomputed'] == 2
    task['latest_declared_condition_run_id'] = 'owned-first'
    with pytest.raises(ValueError, match='most-recent'):
        checker.check(evidence, contract)


@pytest.fixture
def bundle(evidence, tmp_path):
    source = tmp_path / 'evidence.json'
    source.write_bytes(checker.canonical(evidence) + b'\n')
    root = tmp_path / 'bundle'
    packed = transport.pack(source, transport.sha(source.read_bytes()), root)
    return root, packed['index_sha256'], source


def rewrite_index(root, update):
    index = json.loads((root / 'INDEX.json').read_bytes())
    update(index)
    data = checker.canonical(index) + b'\n'
    (root / 'INDEX.json').write_bytes(data)
    return transport.sha(data)


def test_transport_roundtrip_is_exact(bundle, tmp_path):
    root, expected_sha, source = bundle
    output = tmp_path / 'decoded.json'
    result = transport.verify(root, expected_sha, contract, output)
    assert result['qualified_conditions'] == 1
    assert output.read_bytes() == source.read_bytes()


def test_wrong_external_transport_hash_rejected(bundle):
    root, _, _ = bundle
    with pytest.raises(ValueError, match='trusted external SHA'):
        transport.verify(root, '0' * 64, contract)


@pytest.mark.parametrize('mutation', ['extra', 'missing', 'symlink', 'bitflip'])
def test_transport_file_set_and_bytes_fail_closed(bundle, mutation):
    root, expected_sha, _ = bundle
    part = next((root / 'conditions').iterdir())
    if mutation == 'extra':
        (root / 'unreviewed.log').write_text('owned sentinel')
    elif mutation == 'missing':
        part.unlink()
    elif mutation == 'symlink':
        (root / 'link.json.gz').symlink_to(part)
    else:
        raw = bytearray(part.read_bytes())
        raw[-1] ^= 1
        part.write_bytes(raw)
    with pytest.raises(ValueError):
        transport.verify(root, expected_sha, contract)


@pytest.mark.parametrize('mutation', ['traversal', 'identity', 'partcap', 'totalcap'])
def test_transport_resigned_index_cannot_override_constraints(bundle, mutation, monkeypatch):
    root, _, _ = bundle

    def update(index):
        part = index['conditions'][0]
        if mutation == 'traversal':
            part['name'] = '../outside.json.gz'
        elif mutation == 'identity':
            part['instance_id'] = 'owned-wrong'
        elif mutation == 'partcap':
            part['uncompressed_bytes'] = transport.MAX_PART + 1
        else:
            monkeypatch.setattr(transport, 'MAX_TOTAL', 1)

    sha = rewrite_index(root, update)
    with pytest.raises(ValueError):
        transport.verify(root, sha, contract)


def test_privacy_known_patterns_rejected_before_pack(evidence, tmp_path):
    evidence['unreviewed_note'] = 'private@example.invalid'
    source = tmp_path / 'evidence.json'
    source.write_bytes(checker.canonical(evidence) + b'\n')
    with pytest.raises(ValueError, match='private'):
        transport.pack(source, transport.sha(source.read_bytes()), tmp_path / 'bundle')
