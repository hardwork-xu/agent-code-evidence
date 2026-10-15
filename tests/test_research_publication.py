"""Offline publication gates; no upstream execution or benchmark measurements.

仅核查公开文件及许可完整性，不执行上游代码、不采集性能结果。
"""
import json
from pathlib import Path
import shutil

import pytest

from scripts import check_attribution as attribution
from scripts import check_research_artifacts as artifacts
from scripts.build_release import check_retained_licenses, retained_licenses

ROOT = Path(__file__).resolve().parents[1]


def copy_file(root, relative):
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / relative, target)


@pytest.fixture
def heldout(tmp_path):
    shutil.copytree(ROOT / 'benchmarks/incremental_holdout',
                    tmp_path / 'benchmarks/incremental_holdout',
                    ignore=shutil.ignore_patterns('results', '__pycache__'))
    return tmp_path


@pytest.fixture
def task_root(tmp_path):
    shutil.copytree(ROOT / 'benchmarks/task_evidence', tmp_path / 'benchmarks/task_evidence',
                    ignore=shutil.ignore_patterns('__pycache__'))
    for relative in (*attribution.BASE_MANIFESTS, attribution.HISTORY, attribution.PROTOCOL,
                     attribution.HUMAN_PROTOCOL, attribution.TASK_PILOT_RETENTION):
        copy_file(tmp_path, relative)
    return tmp_path


def test_new_studies_have_exact_license_and_case_coverage(heldout, task_root):
    holdout_report = attribution.check_incremental_holdout(heldout)
    assert holdout_report['initial_selection_preserved']
    assert holdout_report['pinned_revisions'] == holdout_report['license_files'] == 32
    task_report = attribution.check_task_evidence(task_root)
    assert task_report['pinned_revisions'] == 6
    assert task_report['license_files'] == 10
    assert task_report['reviewed_test_cases'] == 9
    assert task_report['retained_invalid_pilot_files'] == 5


@pytest.mark.parametrize('change', ['initial-bytes', 'license-bytes', 'unlisted-license',
                                    'embedded-source', 'unknown-source-file'])
def test_heldout_attribution_rejects_undisclosed_or_modified_material(heldout, change):
    directory = heldout / 'benchmarks/incremental_holdout'
    if change == 'initial-bytes':
        path = directory / 'initial-manifest.json'
        path.write_bytes(path.read_bytes() + b'\n')
    elif change == 'license-bytes':
        path = next((directory / 'licenses').rglob('LICENSE.md'))
        path.write_bytes(path.read_bytes() + b' ')
    elif change == 'unlisted-license':
        (directory / 'licenses/EXTRA').write_text('undeclared material')
    elif change == 'embedded-source':
        (directory / 'extra.json').write_text(json.dumps({'payload': '{"text":"return 7"}'}))
    else:
        (directory / 'unreviewed.py').write_text('VALUE = 1\n')
    with pytest.raises(ValueError):
        attribution.check_incremental_holdout(heldout)


@pytest.mark.parametrize('change', ['protocol', 'license-bytes', 'missing-second-license',
                                    'modified-license-and-hash', 'case-selection', 'unpinned-test',
                                    'source-hash', 'embedded-source', 'unknown-source-file'])
def test_task_attribution_cannot_bless_changed_sources_or_missing_licenses(task_root, change):
    directory = task_root / 'benchmarks/task_evidence'
    path = directory / 'manifest.json'
    manifest = json.loads(path.read_text())
    license_path = directory / 'licenses/packaging/after/LICENSE.BSD'
    if change == 'protocol':
        (directory / 'PROTOCOL.md').write_text('changed protocol')
    elif change in {'license-bytes', 'modified-license-and-hash'}:
        license_path.write_bytes(license_path.read_bytes() + b' ')
        if change == 'modified-license-and-hash':
            row = next(r for r in manifest['repositories']['packaging']['versions']['after']['license_files']
                       if r['path'] == 'LICENSE.BSD')
            row['sha256'] = attribution.digest(license_path.read_bytes())
    elif change == 'missing-second-license':
        license_path.unlink()
    elif change == 'case-selection':
        manifest['cases'].pop()
    elif change == 'unpinned-test':
        case = manifest['cases'][0]
        commit = manifest['repositories'][case['repository']]['versions']['after']['commit']
        case['test_url'] = case['test_url'].replace(commit, 'main')
    elif change == 'source-hash':
        manifest['repositories']['packaging']['versions']['after']['source_files']['src/packaging/specifiers.py'] = 'invalid'
    elif change == 'embedded-source':
        (directory / 'extra.json').write_text(json.dumps({'code': 'return 17'}))
    else:
        (directory / 'upstream.py').write_text('VALUE = 1\n')
    path.write_text(json.dumps(manifest))
    with pytest.raises((ValueError, OSError)):
        attribution.check_task_evidence(task_root)


def test_source_license_gate_preserves_formatting_and_covers_new_license_names():
    expected = {'benchmarks/task_evidence/licenses/p/after/LICENSE.APACHE': b'line  \r\nend \n'}
    check_retained_licenses(dict(expected), expected)
    with pytest.raises(ValueError, match='missing/changed'):
        check_retained_licenses({}, expected)
    with pytest.raises(ValueError, match='missing/changed'):
        check_retained_licenses({next(iter(expected)): b'line\nend\n'}, expected)
    actual = retained_licenses(ROOT)
    assert len([p for p in actual if p.startswith('benchmarks/incremental_holdout/')]) == 32
    assert len([p for p in actual if p.startswith('benchmarks/task_evidence/')]) == 10
    assert any(p.endswith('/LICENSE.APACHE') for p in actual)


def test_offline_holdout_preparation_does_not_claim_a_measurement(heldout):
    assert artifacts.check_holdout(heldout)['status'] == 'prepared_without_results'


@pytest.mark.parametrize('change', ['missing-all-suite', 'running', 'changed-summary', 'failed-success-summary'])
def test_offline_holdout_result_gate_rejects_incomplete_publication(heldout, monkeypatch, change):
    results = heldout / 'benchmarks/incremental_holdout/results'
    results.mkdir()
    monkeypatch.setattr(artifacts.holdout, 'summarize', lambda *args: {'verified': True})
    raw = {'status': 'passed', 'suite': 'all', 'summary': {'verified': True}}
    if change == 'missing-all-suite':
        raw['suite'] = 'timing'
    elif change == 'running':
        raw['status'] = 'running'
    elif change == 'changed-summary':
        raw['summary'] = {'verified': False}
    else:
        raw.update(status='failed', error_type='RuntimeError')
    (results / 'authored.json').write_text(json.dumps(raw))
    with pytest.raises(ValueError):
        artifacts.check_holdout(heldout)


def test_failed_holdout_attempt_is_retained_separately_from_completed_evidence(heldout, monkeypatch):
    results = heldout / 'benchmarks/incremental_holdout/results'
    results.mkdir()
    monkeypatch.setattr(artifacts.holdout, 'summarize', lambda *args: {'verified': True})
    (results / 'complete.json').write_text(json.dumps(
        {'status': 'passed', 'suite': 'all', 'summary': {'verified': True}}))
    (results / 'failed.json').write_text(json.dumps({'status': 'failed', 'error_type': 'ValueError'}))
    report = artifacts.check_holdout(heldout)
    assert report['passed'] == report['complete_all_suite_runs'] == report['retained_failures'] == 1


def test_invalid_task_pilot_cannot_be_reclassified(task_root):
    (task_root / 'benchmarks/task_evidence/results/initial/STATUS.md').write_text('passed')
    with pytest.raises(ValueError, match='disclosure'):
        artifacts.check_tasks(task_root)


@pytest.mark.parametrize('change', ['bytes', 'missing-inventory-entry', 'missing-file', 'status'])
def test_invalid_pilot_history_cannot_be_silently_rewritten(task_root, change):
    path = task_root / attribution.TASK_PILOT_RETENTION
    retained = json.loads(path.read_text())
    pilot = task_root / 'benchmarks/task_evidence/results/initial/runs.json'
    if change == 'bytes':
        pilot.write_bytes(pilot.read_bytes() + b'\n')
    elif change == 'missing-file':
        pilot.unlink()
    elif change == 'missing-inventory-entry':
        retained['files'].pop(next(iter(retained['files'])))
    else:
        retained['status'] = 'passed'
    path.write_text(json.dumps(retained))
    with pytest.raises((ValueError, OSError)):
        attribution.check_task_pilot(task_root)


def test_additional_task_results_require_explicit_review(task_root):
    (task_root / 'benchmarks/task_evidence/results/unreviewed').mkdir()
    with pytest.raises(ValueError, match='unreviewed task result'):
        artifacts.check_tasks(task_root)
