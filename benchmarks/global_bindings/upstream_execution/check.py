"""Read-only retained record checks. / 仅读核验保留记录。

Record integrity is not scientific maturity or independent peer review.
记录一致性不等同成熟科研或独立同行复核。
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
DATA = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from scripts.prepare_global_execution_sources import safe_relative, source_name, validate_inputs  # noqa: E402


def normalized(node: str, testfile: str) -> str:
    return testfile + node if node.startswith('::') else node


def verify_record(record: dict, source: dict, *, expected_cases: int,
                  package_path: str, tests: list[str]) -> dict:
    if (record.get('schema_version') != 1 or not record['production_hashes_verified']
            or record['repository'] != source['repository'] or record['source_sha'] != source['sha']):
        raise ValueError('source/record identity mismatch')
    testfiles = {node.split('::')[0] for node in tests}
    if len(testfiles) != 1:
        raise ValueError('record normalization requires one fixed test file')
    testfile = next(iter(testfiles))
    cases = [normalized(node, testfile) for node in record['collected_cases']]
    if len(cases) != expected_cases or len(set(cases)) != len(cases):
        raise ValueError('missing/duplicate collected cases')
    for node in cases:
        if not any(node == base or node.startswith(base + '[') for base in tests):
            raise ValueError('unselected test in retained record')
    calls = {}
    for report in record['reports']:
        node = normalized(report['nodeid'], testfile)
        if node not in cases or report['outcome'] not in {'passed', 'failed', 'skipped'}:
            raise ValueError('invalid test report')
        duration = report.get('duration')
        if type(duration) not in {int, float} or not math.isfinite(duration) or duration < 0:
            raise ValueError('nonfinite or invalid per-phase measurement')
        if report['when'] == 'call':
            if node in calls:
                raise ValueError('duplicate call report')
            calls[node] = report['outcome']
        elif report['when'] not in {'setup', 'teardown'} or report['outcome'] != 'passed':
            raise ValueError('non-call failure must remain explicit')
    if set(calls) != set(cases):
        raise ValueError('missing test call outcomes')
    counts = {name: sum(value == name for value in calls.values())
              for name in ['passed', 'failed', 'skipped']}
    expected_code = 1 if counts['failed'] else 0
    if record['exit_code'] != expected_code:
        raise ValueError('pytest exit/outcome mismatch')
    if not record['loaded_source_modules']:
        raise ValueError('actual imported production identity missing')
    for module in record['loaded_source_modules'].values():
        path = safe_relative(module['relative_path'])
        if (not path.startswith(package_path + '/') or path not in source['regular_files']
                or module['sha256'] != source['regular_files'][path]['sha256']):
            raise ValueError('imported source identity differs from selected role')
    for node, paths in record['execution_trace'].items():
        if node != '__import__' and normalized(node, testfile) not in cases:
            raise ValueError('trace has unknown test node')
        for path, lines in paths.items():
            safe_relative(path)
            if (not path.startswith(package_path + '/') or path not in source['regular_files']
                    or lines != sorted(set(lines))
                    or any(type(line) is not int or line <= 0 for line in lines)):
                raise ValueError('trace line/path invalid')
    for field in ['peak_rss_mib', 'elapsed_seconds']:
        number = record[field]
        if (type(number) not in {int, float} or not math.isfinite(number)
                or number < 0 or (field == 'peak_rss_mib' and number == 0)):
            raise ValueError('nonfinite or invalid resource observation')
    return counts


def verify_all(inputs: dict, primary: dict, global_record: dict) -> dict:
    validate_inputs(inputs)
    sources = {(s['repository'], s['sha']): s for s in inputs['sources']}
    if primary['source_input_sha256'] != hashlib.sha256(
            (DATA / 'inputs.json').read_bytes()).hexdigest():
        raise ValueError('retained run input hash mismatch')
    expected_roles = {(c['repository'], role) for c in inputs['cases'] for role in ['fixed', 'parent']}
    actual_roles = [(r['repository'], r['role']) for r in primary['runs']]
    if set(actual_roles) != expected_roles or len(actual_roles) != len(expected_roles):
        raise ValueError('missing/duplicate source role run')
    totals = {'fixed': {'passed': 0, 'failed': 0, 'skipped': 0},
              'parent': {'passed': 0, 'failed': 0, 'skipped': 0}}
    for record in primary['runs']:
        case = next(c for c in inputs['cases'] if c['repository'] == record['repository'])
        if (record['source_sha'] != case[record['role'] + '_sha']
                or record['label_source_sha'] != case['fixed_sha']):
            raise ValueError('wrong production/test role')
        counts = verify_record(record, sources[(record['repository'], record['source_sha'])],
                               expected_cases=case['expected_parameterized_cases'],
                               package_path=case['package_path'], tests=case['tests'])
        for name, number in counts.items():
            totals[record['role']][name] += number
    if (totals != {'fixed': {'passed': 43, 'failed': 0, 'skipped': 0},
                   'parent': {'passed': 15, 'failed': 28, 'skipped': 0}}
            or primary['upstream_change_units'] != 4 or primary['test_cases_per_source_role'] != 43
            or primary['fixed_passed'] != 43 or primary['parent_passed'] != 15
            or primary['parent_failed'] != 28 or primary['skipped'] != 0):
        raise ValueError('retained upstream behavior counts disagree')
    panel = inputs['global_panel']
    counts = verify_record(global_record, sources[(panel['repository'], panel['sha'])],
                           expected_cases=panel['expected_test_cases'],
                           package_path=panel['package_path'], tests=panel['tests'])
    if counts != {'passed': 23, 'failed': 0, 'skipped': 0}:
        raise ValueError('whole lexical global panel counts disagree')
    observations = global_record['global_observations']
    if len(observations) != 200:
        raise ValueError('missing global-state observations')
    first = observations[0]['state']
    second = observations[1]['state']
    if (first['_trim_arity_call_line']['type'] != 'NoneType'
            or second['_trim_arity_call_line']['type'] != 'FrameSummary'
            or first['pa_call_line_synth']['tuple_length'] != 0
            or second['pa_call_line_synth']['tuple_length'] != 2):
        raise ValueError('retained literal/runtime binding difference missing')
    return {'status': 'verified', 'upstream_change_units': 4, 'fixed_cases_passed': 43,
            'parent_cases_failed': 28, 'global_whole_panel_tests': 23,
            'global_observations': 200, 'scientific_maturity_established': False}



def verify_portable_replay(inputs: dict, directory: Path, *, script_root: Path = DATA,
                           preparer_path: Path = ROOT / 'scripts/prepare_global_execution_sources.py',
                           dependency_path: Path = DATA / 'dependencies.json') -> dict:
    """Check known preflight replay records without execution. / 不执行源码，核验预飞重放记录。"""
    index_path = directory / 'index.json'
    if not index_path.is_file() or index_path.is_symlink():
        raise ValueError('portable replay index missing')
    index = json.loads(index_path.read_text())
    if (index.get('schema_version') != 1 or not index['all_source_role_and_loaded_module_hashes_verified']
            or not index['upstream_assertions_unmodified'] or not index['raw_logs_private_outside_git']):
        raise ValueError('portable replay schema/provenance mismatch')
    if index['input_sha256'] != hashlib.sha256((DATA / 'inputs.json').read_bytes()).hexdigest():
        raise ValueError('portable replay fixed input hash mismatch')
    for field, name in [('worker_sha256', 'worker.py'), ('runner_sha256', 'run.py')]:
        if index[field] != hashlib.sha256((script_root / name).read_bytes()).hexdigest():
            raise ValueError('portable replay historical script hash mismatch')
    amendment = index.get('provenance_amendment')
    if not isinstance(amendment, dict) or amendment.get('new_measurement') is not False:
        raise ValueError('portable replay post-execution amendment missing/invalid')
    original_path = directory / 'index-original-v1.json'
    if (not original_path.is_file() or original_path.is_symlink()
            or hashlib.sha256(original_path.read_bytes()).hexdigest() !=
            amendment['original_index_sha256']):
        raise ValueError('portable replay original index missing or changed')
    original = json.loads(original_path.read_text())
    amended_fields = {'preparer_sha256', 'dependency_metadata_sha256', 'provenance_amendment'}
    if {key: value for key, value in index.items() if key not in amended_fields} != original:
        raise ValueError('portable replay amendment altered original measurements/provenance')
    amended_time = datetime.fromisoformat(amendment['time_utc'])
    completed_time = datetime.fromisoformat(index['completed_at_utc'])
    if (amended_time.tzinfo is None or completed_time.tzinfo is None
            or amended_time <= completed_time
            or 'after execution' not in amendment['reason']
            or 'not captured by the original worker' not in amendment['reason']):
        raise ValueError('portable replay amendment misstates its post-execution origin')
    for field, path in [('preparer_sha256', preparer_path),
                        ('dependency_metadata_sha256', dependency_path)]:
        if index[field] != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError('portable replay historical helper/dependency fingerprint mismatch')
    sources = {(row['repository'], row['sha']): row for row in inputs['sources']}
    expected = {}
    for case in inputs['cases']:
        for role in ['fixed', 'parent']:
            name = source_name(case['repository'], case[role + '_sha']) + '-' + role + '.json'
            expected[name] = {'repository': case['repository'], 'role': role,
                              'source_sha': case[role + '_sha'], 'label_source_sha': case['fixed_sha'],
                              'tests': case['tests'], 'package_path': case['package_path'],
                              'cases': case['expected_parameterized_cases']}
    panel = inputs['global_panel']
    expected['global-whole-panel.json'] = {
        'repository': panel['repository'], 'role': 'current_head_global_writer_preflight',
        'source_sha': panel['sha'], 'label_source_sha': panel['sha'],
        'tests': panel['tests'], 'package_path': panel['package_path'],
        'cases': panel['expected_test_cases']}
    files = index['files']
    if set(files) != set(expected) | {'runs.json'}:
        raise ValueError('portable replay missing or extra result files')
    loaded = {}
    for name, digest in files.items():
        safe_relative(name)
        path = directory / name
        if (path.is_symlink() or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != digest):
            raise ValueError('portable replay file missing or digest mismatch')
        loaded[name] = json.loads(path.read_text())
    cards = index['records']
    if (len(cards) != len(expected) or {card['file'] for card in cards} != set(expected)
            or len({card['file'] for card in cards}) != len(cards)):
        raise ValueError('portable replay missing or duplicate record card')
    controller = loaded['runs.json']
    if (controller['schema_version'] != 1 or controller['input_sha256'] != index['input_sha256']
            or controller['worker_sha256'] != index['worker_sha256']
            or controller['raw_logs_private_outside_git'] is not True):
        raise ValueError('portable replay controller provenance mismatch')
    runs = controller['runs']
    if (len(runs) != len(expected) or len({(r['repository'], r['role']) for r in runs}) != len(runs)):
        raise ValueError('portable replay missing/duplicate controller run')
    totals = {'fixed': {'passed': 0, 'failed': 0, 'skipped': 0},
              'parent': {'passed': 0, 'failed': 0, 'skipped': 0}}
    for name, identity in expected.items():
        record = loaded[name]
        if any(record[key] != identity[key] for key in
               ['repository', 'role', 'source_sha', 'label_source_sha']):
            raise ValueError('portable replay fixed source/test role mismatch')
        counts = verify_record(record, sources[(identity['repository'], identity['source_sha'])],
                               expected_cases=identity['cases'], package_path=identity['package_path'],
                               tests=identity['tests'])
        card = next(card for card in cards if card['file'] == name)
        if (card['repository'] != identity['repository'] or card['role'] != identity['role']
                or card['counts'] != counts
                or card['observations'] != len(record['global_observations'])):
            raise ValueError('portable replay card/actual outcomes disagree')
        matching = [r for r in runs if r['repository'] == identity['repository']
                    and r['role'] == identity['role']]
        if len(matching) != 1:
            raise ValueError('portable replay controller role missing')
        run = matching[0]
        if (run['source_sha'] != identity['source_sha'] or run['status'] != 'executed'
                or run['process_exit_code'] != 0 or run['expected_cases'] != identity['cases']
                or run['collected_cases'] != identity['cases']
                or run['upstream_pytest_exit_code'] != record['exit_code']
                or type(run['started_unix']) not in {int, float}
                or not math.isfinite(run['started_unix']) or run['started_unix'] <= 0):
            raise ValueError('portable replay controller/outcome or measurement disagreement')
        if identity['role'] in totals:
            for outcome, number in counts.items():
                totals[identity['role']][outcome] += number
        elif counts != {'passed': 23, 'failed': 0, 'skipped': 0} or card['observations'] != 200:
            raise ValueError('portable replay whole lexical panel changed')
    if (totals != {'fixed': {'passed': 43, 'failed': 0, 'skipped': 0},
                   'parent': {'passed': 15, 'failed': 28, 'skipped': 0}}
            or index['totals'] != totals):
        raise ValueError('portable replay failure denominator disagreement')
    return {'status': 'verified', 'real_upstream_replay_processes': 9,
            'fixed_cases_passed': 43, 'parent_cases_failed': 28,
            'global_whole_panel_tests': 23, 'metadata_only_validation': True,
            'new_independent_holdout': False, 'scientific_maturity_established': False,
            'helper_fingerprints_recorded_after_execution': True}

def main() -> int:
    inputs = json.loads((DATA / 'inputs.json').read_text())
    primary = json.loads((DATA / 'results/upstream-preflight.json').read_text())
    global_record = json.loads((DATA / 'results/global-whole-panel.json').read_text())
    for source in inputs['sources']:
        for license_record in source['licenses']:
            path = DATA / safe_relative(license_record['local_path'])
            if hashlib.sha256(path.read_bytes()).hexdigest() != license_record['sha256']:
                raise ValueError('original license bytes changed')
    print(json.dumps({'original_preflight': verify_all(inputs, primary, global_record),
                      'portable_replay': verify_portable_replay(
                          inputs, DATA / 'results/portable-replay-20261014')}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
