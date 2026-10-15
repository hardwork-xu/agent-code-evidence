"""Strict finite regression qualification / 严格有限回归验收。

Inputs are typed execution records; this module never imports or executes
upstream source. It requires actual exact collection, observed passes for every
P2P unit, successful gold-run termination and retained failure states. These
conditions are deliberately stricter than upstream absence-of-P2P-failure
scoring; this is an unofficial adapted qualification, not an official score.
``collected_all`` records the complete actual pre-filter collection;
``collected`` and ``selected`` contain only the exact F2P/P2P nodes chosen for
execution. ``deselected`` is their disjoint complement and needs no outcome.
Only this fixed finite subset is qualified, never every test in the files.
An optional fixed ``pathless_aliases`` map can resolve only ``:identifier:?``
labels using reviewed exact test source identities. It is hashed into both role
records, never inferred here, and still requires actual exact collection.

本模块只处理结构化执行记录，不导入或执行上游源码。要求真实精确收集、
全部 P2P 实际通过、gold 正常结束及保留失败；比上游仅检查无 P2P 失败更严，
属于非官方适配验收，不等同官方分数或完整语义证明。
collected_all 是过滤前真实收集；collected/selected 是固定标签精确选择的节点，
deselected 是互斥补集，无需执行结果。本判据只验收固定子集，不声称完整测试文件通过。
可选固定 pathless_aliases 只映射无路径标识符，绑定已核验测试源码及两侧摘要；
本模块不自动推断映射，映射后仍必须真实精确收集。
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


STATES = {'passed', 'failed', 'skipped', 'error', 'not_run', 'timeout', 'blocked',
          'xfailed', 'xpassed'}
ROLES = {'base', 'gold'}
RUNNER_STATES = {'completed', 'blocked', 'timeout', 'crashed'}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'),
                      allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def validate_aliases(aliases):
    """Check explicit pathless identities / 校验显式无路径身份，不作推断。"""
    if not isinstance(aliases, dict):
        raise ValueError('pathless aliases must be a fixed mapping')
    canonical_nodes = set()
    for metadata_id, row in aliases.items():
        match = re.fullmatch(r':([^:]+):?', metadata_id) if isinstance(metadata_id, str) else None
        if not match or not match[1].isidentifier() or not isinstance(row, dict):
            raise ValueError('alias only permits a pathless exact identifier')
        if row.get('method') != match[1]:
            raise ValueError('alias method differs from original exact identifier')
        if (not isinstance(row.get('source_sha256'), str)
                or not re.fullmatch('[0-9a-f]{64}', row['source_sha256'])):
            raise ValueError('alias exact source SHA missing or invalid')
        if not isinstance(row.get('source_path'), str) or not isinstance(row.get('class'), str):
            raise ValueError('alias source path and class missing')
        regular = selector(row['source_path'] + ':' + row['class'] + ':' + row['method'])
        if regular['selector'] is None or row.get('canonical_selector') != regular['selector']:
            raise ValueError('alias canonical selector differs from exact path/class/method')
        if regular['selector'] in canonical_nodes:
            raise ValueError('alias labels duplicate one canonical test')
        canonical_nodes.add(regular['selector'])
    return aliases


def selector(metadata_id, pathless_aliases=None):
    """Candidate exact selector; never guess collection / 候选节点，禁止猜测收集。"""
    aliases = validate_aliases(pathless_aliases) if pathless_aliases is not None else {}
    if isinstance(metadata_id, str) and metadata_id in aliases:
        row = aliases[metadata_id]
        return {'status': 'awaiting_actual_collection', 'reason': None,
                'selector': row['canonical_selector'], 'mapping_kind': 'explicit_source_alias',
                'source_path': row['source_path'], 'source_sha256': row['source_sha256'],
                'class': row['class'], 'method': row['method']}
    if not isinstance(metadata_id, str) or '\0' in metadata_id or '\n' in metadata_id or '\r' in metadata_id:
        return {'status': 'metadata_ambiguous', 'reason': 'invalid_metadata_id', 'selector': None}
    parts = metadata_id.split(':', 2)
    if len(parts) != 3 or not parts[0] or not parts[1] or not parts[2]:
        return {'status': 'metadata_ambiguous', 'reason': 'missing_path_class_or_name', 'selector': None}
    path, class_name, name = parts
    if (path.startswith('/') or '\\' in path or ':' in path
            or any(part in {'', '.', '..'} for part in path.split('/'))
            or not path.endswith('.py')):
        return {'status': 'metadata_ambiguous', 'reason': 'unsafe_or_non_python_path', 'selector': None}
    if class_name != 'None' and not class_name.isidentifier():
        return {'status': 'metadata_ambiguous', 'reason': 'unsupported_class_encoding', 'selector': None}
    stem = name.split('[', 1)[0]
    if not stem.isidentifier() or ('[' in name and not name.endswith(']')):
        return {'status': 'metadata_ambiguous', 'reason': 'unsupported_test_name_encoding', 'selector': None}
    # The full generated/parameterized name remains unchanged. Nothing strips
    # numeric suffixes, translates named parameters or walks inheritance here.
    value = path + ('::' + class_name if class_name != 'None' else '') + '::' + name
    return {'status': 'awaiting_actual_collection', 'reason': None, 'selector': value}


def resolve(metadata_id, collected, pathless_aliases=None):
    """Require actual exact collection / 只接受真实收集的精确节点。"""
    result = selector(metadata_id, pathless_aliases)
    if result['selector'] is not None:
        result['status'] = 'collected_exactly' if result['selector'] in collected else 'not_collected'
    return result


def validate_execution(record, task, role):
    if (record.get('schema_version') != 1 or record.get('role') != role
            or record.get('instance_id') != task['instance_id']
            or record.get('base_commit') != task['base_commit']
            or record.get('test_patch_sha256') != task['test_patch_sha256']
            or record.get('code_patch_sha256') != (task['code_patch_sha256'] if role == 'gold' else None)):
        raise ValueError('role/task/source/test-patch provenance differs')
    aliases = validate_aliases(task.get('pathless_aliases', {}))
    if ((aliases or 'pathless_aliases_sha256' in record)
            and record.get('pathless_aliases_sha256') != digest(aliases)):
        raise ValueError('fixed pathless alias digest differs or missing')
    if not isinstance(record.get('environment_sha256'), str) or not re.fullmatch('[0-9a-f]{64}', record['environment_sha256']):
        raise ValueError('environment fingerprint missing')
    if record.get('collection_status') not in {'complete', 'error', 'timeout', 'blocked'}:
        raise ValueError('collection status invalid')
    if record.get('runner_status') not in RUNNER_STATES or 'process_exit_code' not in record:
        raise ValueError('runner termination status missing or invalid')
    exit_code = record['process_exit_code']
    if record['runner_status'] == 'completed':
        if not isinstance(exit_code, int) or isinstance(exit_code, bool):
            raise ValueError('completed runner requires integer process exit code')
    elif exit_code is not None:
        raise ValueError('incomplete runner must retain unknown process exit code')
    collected = record.get('collected')
    if (not isinstance(collected, list) or not all(isinstance(node, str) and node for node in collected)
            or len(collected) != len(set(collected))):
        raise ValueError('collected node IDs must be distinct')
    all_nodes, selected, deselected = (record.get(key) for key in ('collected_all', 'selected', 'deselected'))
    if any(not isinstance(nodes, list) or not all(isinstance(node, str) and node for node in nodes)
           or len(nodes) != len(set(nodes)) for nodes in (all_nodes, selected, deselected)):
        raise ValueError('actual pre-filter collection and selection partition missing or invalid')
    if (selected != collected or set(selected) & set(deselected)
            or set(selected) | set(deselected) != set(all_nodes)):
        raise ValueError('actual collection selection partition differs')
    if not isinstance(record.get('results'), list):
        raise ValueError('testcase results must be a list, including explicit empty results')
    outcomes = {}
    for row in record['results']:
        if not isinstance(row, dict):
            raise ValueError('testcase outcome must be a record')
        nodeid = row.get('nodeid')
        if nodeid not in collected or nodeid in outcomes or row.get('state') not in STATES:
            raise ValueError('missing, duplicate or invalid testcase outcome')
        if row.get('phase') not in {'call', 'setup', 'teardown', 'collection', 'not_run'}:
            raise ValueError('testcase phase missing')
        if row.get('kind') not in {'behavior', 'dependency', 'network', 'resource', 'framework', 'unknown'}:
            raise ValueError('testcase failure category missing')
        outcomes[nodeid] = row
    return set(collected), outcomes


def evaluate_pair(task, base, gold):
    """Finite unofficial qualification / 有限非官方验收，不证明自主修复或完整语义。"""
    labels = [(unit['kind'], unit['metadata_id']) for unit in task['test_units']]
    counts = Counter(kind for kind, _ in labels)
    if (len(labels) != len(set(labels)) or counts['F2P'] != task['f2p_units']
            or counts['P2P'] != task['p2p_units'] or task['f2p_units'] <= 0):
        raise ValueError('fixed unit denominator differs or has no F2P')
    aliases = validate_aliases(task.get('pathless_aliases', {}))
    if set(aliases) - {metadata_id for _, metadata_id in labels}:
        raise ValueError('alias does not belong to a fixed metadata unit')
    selectors = [selector(metadata_id, aliases)['selector'] for _, metadata_id in labels]
    exact_selectors = [value for value in selectors if value is not None]
    if len(exact_selectors) != len(set(exact_selectors)):
        raise ValueError('metadata units duplicate one canonical test')
    collected_base, outcomes_base = validate_execution(base, task, 'base')
    collected_gold, outcomes_gold = validate_execution(gold, task, 'gold')
    common_environment = base['environment_sha256'] == gold['environment_sha256']
    complete = base['collection_status'] == gold['collection_status'] == 'complete'
    runners_completed = base['runner_status'] == gold['runner_status'] == 'completed'
    gold_process_successful = gold['runner_status'] == 'completed' and gold['process_exit_code'] == 0
    # pytest/unittest normally exit 1 for observed test failures, and 0 without
    # failures. Other exits include usage/internal/collection/no-test failures.
    # 实际失败对应退出码 1；异常终止或结果与退出码矛盾不能合格。
    expected_base_exit = 1 if any(row['state'] == 'failed' for row in base['results']) else 0
    base_process_consistent = (base['runner_status'] == 'completed'
                              and base['process_exit_code'] == expected_base_exit)
    missing_outcomes = {'base': [node for node in base['collected'] if node not in outcomes_base],
                        'gold': [node for node in gold['collected'] if node not in outcomes_gold]}
    outcomes_complete = not any(missing_outcomes.values())
    units = []
    for unit in task['test_units']:
        metadata_id = unit['metadata_id']
        left = resolve(metadata_id, collected_base, aliases)
        right = resolve(metadata_id, collected_gold, aliases)
        before = outcomes_base.get(left['selector'])
        after = outcomes_gold.get(right['selector'])
        observed = left['status'] == right['status'] == 'collected_exactly' and before is not None and after is not None
        if unit['kind'] == 'F2P':
            met = bool(observed and before['state'] == 'failed' and before['phase'] == 'call'
                       and before['kind'] == 'behavior' and after['state'] == 'passed'
                       and after['phase'] == 'call')
        elif unit['kind'] == 'P2P':
            met = bool(observed and before['state'] == after['state'] == 'passed'
                       and before['phase'] == after['phase'] == 'call')
        else:
            raise ValueError('unknown metadata unit category')
        units.append({'kind': unit['kind'], 'metadata_id': metadata_id, 'base_mapping': left,
                      'gold_mapping': right, 'base': before, 'gold': after,
                      'finite_label_reproduced': met})
    errors = {role: dict(Counter(row['state'] for row in record['results']))
              for role, record in [('base', base), ('gold', gold)]}
    infrastructure_clean = all(row['state'] not in {'error', 'timeout', 'blocked', 'not_run'}
        and (row['state'] != 'failed' or row['kind'] == 'behavior')
        for row in [*base['results'], *gold['results']])
    gold_suite_clean = all(row['state'] in {'passed', 'skipped'} for row in gold['results'])
    qualified = (common_environment and complete and runners_completed and gold_process_successful
                 and base_process_consistent and outcomes_complete and infrastructure_clean and gold_suite_clean
                 and all(row['finite_label_reproduced'] for row in units))
    # Preserve every reported testcase, including those not in F2P/P2P metadata.
    # No skip is a pass, and no unresolved metadata label disappears from the denominator.
    return {'schema_version': 1, 'classification': 'known_development_task_finite_regression_qualification',
            'instance_id': task['instance_id'], 'base_record_sha256': digest(base),
            'pathless_aliases_sha256': digest(aliases), 'pathless_aliases': aliases,
            'gold_record_sha256': digest(gold), 'common_environment': common_environment,
            'both_collections_complete': complete, 'qualified': qualified,
            'both_runners_completed': runners_completed, 'gold_process_successful': gold_process_successful,
            'base_process_consistent': base_process_consistent, 'both_outcomes_complete': outcomes_complete,
            'missing_outcomes': missing_outcomes,
            'runner_outcomes': {role: {'runner_status': record['runner_status'],
                                      'process_exit_code': record['process_exit_code']}
                                for role, record in [('base', base), ('gold', gold)]},
            'infrastructure_clean': infrastructure_clean, 'gold_reported_suite_clean': gold_suite_clean,
            'unit_denominators': dict(Counter(row['kind'] for row in units)),
            'unit_reproduced': dict(Counter(row['kind'] for row in units if row['finite_label_reproduced'])),
            'all_outcome_counts': errors, 'units': units,
            'all_execution_outcomes': {'base': base['results'], 'gold': gold['results']},
            'collection_partitions': {role: {key: record[key] for key in
                                             ('collected_all', 'selected', 'deselected')}
                                      for role, record in [('base', base), ('gold', gold)]},
            'limits': 'Gold code is an evaluation oracle, not a generated repair. These tests cover finite observations, not necessary context or general semantic equivalence.'}


def selector_manifest(review):
    rows = []
    for task in review['tasks']:
        aliases = validate_aliases(task.get('pathless_aliases', {}))
        if set(aliases) - {unit['metadata_id'] for unit in task['test_units']}:
            raise ValueError('alias does not belong to a fixed metadata unit')
        for unit in task['test_units']:
            rows.append({'instance_id': task['instance_id'], 'kind': unit['kind'],
                         'metadata_id': unit['metadata_id'], 'pathless_aliases_sha256': digest(aliases),
                         **selector(unit['metadata_id'], aliases)})
    return {'schema_version': 1, 'classification': 'candidate_selectors_not_executed_or_collected',
            'tasks': len(review['tasks']), 'unit_counts': dict(Counter(row['kind'] for row in rows)),
            'statuses': dict(Counter(row['status'] for row in rows)), 'rows': rows,
            'upstream_code_executed': False,
            'instruction': 'Accept only exact matches in actual collection from the fixed prepared branch. AST candidates do not validate parameterized or inherited selectors.'}


def read(path):
    return json.loads(Path(path).read_bytes())


def write_new(path, payload):
    with Path(path).open('xb') as stream:
        stream.write(canonical(payload) + b'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    ids = sub.add_parser('audit-ids')
    ids.add_argument('--review', type=Path, required=True)
    ids.add_argument('--output', type=Path, required=True)
    pair = sub.add_parser('evaluate-pair')
    pair.add_argument('--review', type=Path, required=True)
    pair.add_argument('--task', required=True)
    pair.add_argument('--base', type=Path, required=True)
    pair.add_argument('--gold', type=Path, required=True)
    pair.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    review = read(args.review)
    if args.command == 'audit-ids':
        result = selector_manifest(review)
    else:
        task = next(row for row in review['tasks'] if row['instance_id'] == args.task)
        result = evaluate_pair(task, read(args.base), read(args.gold))
    write_new(args.output, result)
    print(args.command, 'wrote', args.output.name)


if __name__ == '__main__':
    main()
