"""Recompute finite qualification from exported records without private inputs.

Requires the explicitly pinned, author-written contract module in this checkout.
This executes only that SHA-verified bookkeeping implementation, never SUT code.
The evidence SHA must come from a separately trusted release/commit or review;
SHA consistency alone is not authenticity or proof that tests actually ran.
重算公开观测与有限判据的一致性，不执行上游；哈希一致不等于原始执行认证。
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta
import hashlib
import types
import json
from pathlib import Path
import re

CONTRACT_SHA256 = 'e48afe3dac122e96a7075a72ab406e0e68fb4cc5ac09b98f74ed362211ded9b3'
MAX_EVIDENCE_BYTES = 128 * 1024 * 1024
MAX_CONTRACT_BYTES = 1024 * 1024
COMPARABLE_KEYS = [
    'schema_version', 'classification', 'instance_id', 'pathless_aliases_sha256',
    'pathless_aliases', 'common_environment', 'both_collections_complete',
    'qualified', 'both_runners_completed', 'gold_process_successful',
    'base_process_consistent', 'both_outcomes_complete', 'missing_outcomes',
    'runner_outcomes', 'infrastructure_clean', 'gold_reported_suite_clean',
    'unit_denominators', 'unit_reproduced', 'all_outcome_counts', 'units',
]
PRIVATE_PATTERN = re.compile(
    r'(?i)(?:(?<![A-Za-z0-9_.-])/(?:Users|home|private|var|tmp|Library|Applications|Volumes)/|'
    r'(?<![A-Za-z0-9_.-])[A-Z]:[\\/]|file://|gh[pousr]_[A-Za-z0-9]{12,}|'
    r'github_pat_[A-Za-z0-9_]{12,}|sk-[A-Za-z0-9_-]{16,}|'
    r'[A-Za-z0-9_.+%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|'
    r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)')
FORBIDDEN_KEYS = {'prompt', 'chat', 'chat_history', 'raw_log', 'stdout', 'stderr',
                  'test_patch', 'patch', 'csv_text', 'source_text', 'command',
                  'interpreter_command', 'environment_path', 'token', 'credentials'}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def read_bounded(path, limit, label):
    """Read at most limit+1 bytes once / 单次读取最多limit+1字节，不信任预先stat。"""
    require(type(limit) is int and limit >= 0, 'invalid byte cap')
    with Path(path).open('rb') as handle:
        raw = handle.read(limit + 1)
    require(len(raw) <= limit, label + ' exceeds read cap')
    return raw


def load_contract(path):
    """Execute only verified own contract bytes / 只执行已核验的自主判据字节。"""
    data = read_bounded(path, MAX_CONTRACT_BYTES, 'contract')
    require(hashlib.sha256(data).hexdigest() == CONTRACT_SHA256,
            'contract source differs from explicitly reviewed public pin')
    contract = types.ModuleType('reviewed_public_contract')
    contract.__file__ = str(path)
    # Compile exactly the SHA-verified own bookkeeping bytes, never reopen source.
    exec(compile(data, str(path), 'exec'), contract.__dict__)
    return contract


def scan_privacy(value):
    """Known leak-pattern rejection, not proof that all private facts are absent."""
    if isinstance(value, dict):
        for key, item in value.items():
            require(key not in FORBIDDEN_KEYS, 'forbidden raw/private field')
            scan_privacy(key)
            scan_privacy(item)
    elif isinstance(value, list):
        for item in value:
            scan_privacy(item)
    elif isinstance(value, str):
        require(not PRIVATE_PATTERN.search(value)
                and not value.startswith(('/', '~/', '\\\\')),
                'private path/contact/secret-like text')


def aggregate_node(nodeid, reports):
    """Recompute schema-1 adapter priority and non-call failure normalization.

    setup/teardown failures are errors, never F2P behavioral call failures.
    This matches the retained fixed worker semantics; it does not change tests.
    """
    rows = [row for row in reports if row['nodeid'] == nodeid]
    groups = [
        [row for row in rows if row['state'] == 'failed' and row['phase'] != 'call'],
        [row for row in rows if row['state'] == 'failed'],
        [row for row in rows if row['state'] in {'xfailed', 'xpassed'}],
        [row for row in rows if row['state'] == 'skipped'],
        [row for row in rows if row['phase'] == 'call'],
        [{'nodeid': nodeid, 'phase': 'not_run', 'state': 'not_run', 'kind': 'unknown'}],
    ]
    selected = dict(next(group[0] for group in groups if group))
    if selected['state'] == 'failed' and selected['phase'] != 'call':
        selected['state'] = 'error'
    return selected



def frozen_utc(value):
    """Validate declared UTC syntax/order, not clock authenticity. / 校验声明UTC格式，不认证时钟。"""
    require(isinstance(value, str) and re.fullmatch(
        r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)', value),
        'complete condition requires explicit nonempty ISO UTC freeze time')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise ValueError('invalid declared protocol UTC time') from error
    require(parsed.utcoffset() == timedelta(0), 'protocol freeze time must be UTC')
    return parsed


def check(evidence, contract):
    """Recompute every retained condition and latest state / 重算保留条件及最新状态。"""
    scan_privacy(evidence)
    require(evidence['schema_version'] == 1, 'unsupported evidence schema')
    require(evidence['original_denominator'] == {'tasks': 39, 'F2P': 87, 'P2P': 5842},
            'original denominator changed')
    tasks = {t['instance_id']: t for t in evidence['tasks']}
    require(len(tasks) == len(evidence['tasks']) == 39, 'unique task denominator')
    require(sum(t['original_F2P'] for t in tasks.values()) == 87
            and sum(t['original_P2P'] for t in tasks.values()) == 5842,
            'task unit denominator mismatch')
    required_claims = {'holdout', 'mature', 'generated_repair_success',
        'necessary_context', 'model_quality_improvement', 'official_harness_score',
        'independent_SUT_replication_by_exporter'}
    require(set(evidence['research_claims']) == required_claims
            and all(v is False for v in evidence['research_claims'].values()),
            'missing/unsupported research claim guard')
    condition_keys = set()
    by_task = {task_id: [] for task_id in tasks}
    outcomes = phases = qualified = 0
    for condition in evidence['conditions']:
        parent = tasks[condition['instance_id']]
        key = condition['condition_key']
        require(key not in condition_keys, 'duplicate condition key')
        condition_keys.add(key)
        require(key in parent['condition_keys'], 'condition belongs to a different task')
        by_task[parent['instance_id']].append(condition)
        expected_key = hashlib.sha256(canonical([
            condition['instance_id'], condition['run_id'],
            condition['protocol_sha256']])).hexdigest()
        require(key == expected_key, 'condition identity digest mismatch')
        require(any(p['kind'] == 'contract' and p['sha256'] == CONTRACT_SHA256
                    for p in condition['adapter_program_commitments']),
                'condition contract pin absent or different')
        q = condition['qualification']
        labels = parent['original_labels']
        units = [{'kind': kind, 'metadata_id': label}
                 for kind in ['F2P', 'P2P'] for label in labels[kind]]
        require(len(labels['F2P']) == parent['original_F2P']
                and len(labels['P2P']) == parent['original_P2P'],
                'original label/count mismatch')
        task = {'instance_id': parent['instance_id'],
                'base_commit': parent['base_commit'],
                'code_patch_sha256': parent['code_patch_sha256'],
                'test_patch_sha256': parent['test_patch_sha256'],
                'f2p_units': parent['original_F2P'],
                'p2p_units': parent['original_P2P'],
                'pathless_aliases': q['pathless_aliases'], 'test_units': units}
        roles = {name: row['effective_record'] for name, row in condition['roles'].items()}
        require(set(roles) == {'base', 'gold'}, 'both exact source roles required')
        recomputed = contract.evaluate_pair(task, roles['base'], roles['gold'])
        # Export bookkeeping fields change private-record canonical hashes. Never
        # pretend those can be reconstructed from the privacy-filtered projection.
        for k in COMPARABLE_KEYS:
            left, right = recomputed[k], q[k]
            if k == 'units':
                left = sorted(left, key=lambda x: (x['kind'], x['metadata_id']))
                right = sorted(right, key=lambda x: (x['kind'], x['metadata_id']))
            require(canonical(left) == canonical(right),
                    'finite qualification differs: ' + k)
        require(recomputed['qualified'] == condition['qualified'],
                'condition qualification flag differs')
        require(condition['unit_denominators'] == q['unit_denominators']
                and condition['unit_reproduced'] == q['unit_reproduced'],
                'summary and detailed qualification differ')
        # An honestly retained negative environment mismatch is data, not an
        # excuse to drop that condition or call its proof successful.
        for role, record in roles.items():
            expected_binding = condition['protocol_binding_checks'][role][
                'environment_fingerprint_matches_protocol']
            require((record['environment_sha256'] == condition['environment']['sha256'])
                    == expected_binding, 'declared environment-proof flag differs')
        for role, record in roles.items():
            observations = {(r['nodeid'], r['phase']): r
                            for r in record['phase_reports']}
            reports_by_node = {}
            for report in record['phase_reports']:
                reports_by_node.setdefault(report['nodeid'], []).append(report)
            require(len(observations) == len(record['phase_reports']),
                    'duplicate node/phase observation')
            require(all(r['nodeid'] in record['selected'] for r in record['phase_reports']),
                    'phase outside actual selected subset')
            for row in record['results']:
                observed = (row['phase'] in {'setup', 'call', 'teardown'} and row['state']
                    in {'passed', 'failed', 'skipped', 'error', 'xfailed', 'xpassed'})
                if observed:
                    require(reports_by_node.get(row['nodeid']), 'observed result lacks phase evidence')
                    require(canonical(aggregate_node(row['nodeid'],
                            reports_by_node.get(row['nodeid'], [])))
                            == canonical(row), 'result and phase report differ')
            outcomes += len(record['results'])
            phases += len(record['phase_reports'])
        qualified += recomputed['qualified']
    derived_statuses = Counter()
    for task_id, task in tasks.items():
        conditions = sorted(by_task[task_id], key=lambda c: (frozen_utc(c.get('protocol_created_utc')), c['run_id']))
        require(len(task['condition_keys']) == len(set(task['condition_keys']))
                and set(task['condition_keys']) == {c['condition_key'] for c in conditions},
                'per-task condition membership differs')
        labels = task['original_labels']
        require(set(labels) == {'F2P', 'P2P'} and len(labels['F2P']) == task['original_F2P']
                and len(labels['P2P']) == task['original_P2P'], 'fixed original task labels differ')
        if not conditions:
            state, latest = 'no_completed_target_pair', None
        else:
            last = conditions[-1]
            latest = last['run_id']
            calls = sum(row['phase'] == 'call' for role in last['roles'].values()
                        for row in role['effective_record']['results'])
            state = ('finite_qualified' if last['qualified'] else
                     'paired_unqualified_with_calls' if calls else 'paired_no_observed_target_calls')
        require(task['latest_declared_condition_run_id'] == latest and task['status'] == state,
                'most-recent completed-condition status differs')
        derived_statuses[state] += 1
    require(dict(derived_statuses) == evidence['latest_status_counts']
            and derived_statuses['finite_qualified'] == evidence['coverage_counts']['latest_qualified_tasks'],
            'derived latest status counters differ')
    for partial in evidence['partial_conditions']:
        require(partial['qualification'] is None, 'partial condition cannot be qualified')
        observed = sum(event['event'] == 'phase_report'
            for stream in partial['structured_progress'] for event in stream['events'])
        require(observed == partial['observed_phase_report_count'], 'partial phase count differs')
    require(len(evidence['partial_conditions']) == evidence['coverage_counts']['partial_conditions_with_retained_records']
            and sum(p['observed_phase_report_count'] for p in evidence['partial_conditions'])
                == evidence['coverage_counts']['partial_progress_phase_reports'], 'partial totals differ')
    require(condition_keys == {k for t in tasks.values() for k in t['condition_keys']},
            'task/condition membership differs')
    require(len(condition_keys) == evidence['coverage_counts']['complete_pair_conditions']
            and qualified == evidence['coverage_counts']['qualified_conditions']
            and outcomes == evidence['coverage_counts']['selected_role_outcomes']
            and phases == evidence['coverage_counts']['phase_reports'],
            'coverage counters differ')
    require(dict(Counter(t['status'] for t in tasks.values())) == evidence['latest_status_counts'],
            'latest status counter differs')
    return {'status': 'passed', 'finite_qualifications_recomputed': len(condition_keys),
            'qualified_conditions': qualified, 'phase_reports_checked': phases,
            'partial_conditions_not_qualified': len(evidence['partial_conditions']),
            'limits': [
                'Checks publicly exported observations and qualification arithmetic only.',
                'Does not independently prove original executions or full private source/venv inventories.',
                'Cannot reconstruct SHA-bound private raw artifacts or perform independent SUT replication.',
                'Trusted external evidence digest required; not an authenticity/signature scheme.']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence', required=True, help='exported JSON / 导出JSON')
    p.add_argument('--expected-sha256', required=True, help='trusted external digest / 外部可信摘要')
    p.add_argument('--contract', required=True, help='pinned own contract source / 固定自主判据源码')
    a = p.parse_args()
    try:
        data = read_bounded(a.evidence, MAX_EVIDENCE_BYTES, 'evidence')
        require(hashlib.sha256(data).hexdigest() == a.expected_sha256,
                'evidence differs from trusted external SHA')
        result = check(json.loads(data), load_contract(a.contract))
    except (ValueError, OSError) as error:
        p.exit(2, 'Validation failed / 核验失败: ' + str(error) + '\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
