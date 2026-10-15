"""Claim promotion, evidence drift and same-data metric controls."""
from copy import deepcopy
import hashlib
import json
import shutil

import pytest

from scripts import check_research_claims as claims


@pytest.fixture
def copy_root(tmp_path):
    ledger = json.loads((claims.ROOT / 'research/claims.json').read_text())
    for name in ['research/claims.json', *ledger['evidence_sha256']]:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(claims.ROOT / name, target)
    return tmp_path


def edit(root, change):
    path = root / 'research/claims.json'
    ledger = json.loads(path.read_text())
    change(ledger)
    path.write_text(json.dumps(ledger))


def test_saved_facts_and_limits():
    report = claims.validate(claims.ROOT)
    assert report['record_validation'] == 'passed'
    assert report['maturity'] == 'mature_research_not_established'
    m = report['metrics']
    assert (m['complete_graphs'], m['reference_graphs']) == (0, 768)
    assert m['macro_graph_recall'] == pytest.approx(0.5392489487936633)
    broad = next(r for r in m['tasks'] if r['id'] == 'packaging-metadata-keywords')
    assert broad['execution_density'] == 13 / 3484
    assert broad['context_fraction'] == 3484 / 5653
    assert broad['graph_recall'] == broad['bm25_recall'] == 1


@pytest.mark.parametrize('promotion', ['decision', 'claim', 'gap', 'drop_claim', 'drop_gap'])
def test_cannot_promote_or_delete_uncertainty(copy_root, promotion):
    def change(j):
        if promotion == 'decision':
            j['decision'] = 'mature'
        elif promotion == 'claim':
            j['claims'][5]['state'] = 'supported'
        elif promotion == 'gap':
            j['unmet_criteria'][0]['status'] = 'met'
        elif promotion == 'drop_claim':
            j['claims'].pop()
        else:
            j['unmet_criteria'].pop()
    edit(copy_root, change)
    with pytest.raises(ValueError):
        claims.validate(copy_root, validate_artifacts=False)


def test_raw_tamper(copy_root):
    path = copy_root / claims.TASK / 'cases.json'
    path.write_text(path.read_text() + ' ')
    with pytest.raises(ValueError, match='hash mismatch'):
        claims.validate(copy_root, validate_artifacts=False)


def test_missing_hash(copy_root):
    edit(copy_root, lambda j: j['evidence_sha256'].pop(claims.HOLDOUT))
    with pytest.raises(ValueError, match='missing source/evidence'):
        claims.validate(copy_root, validate_artifacts=False)


def test_path_traversal(copy_root):
    edit(copy_root, lambda j: j['evidence_sha256'].update({'../outside': '0' * 64}))
    with pytest.raises(ValueError):
        claims.validate(copy_root, validate_artifacts=False)


def test_rehashing_changed_archive_cannot_relabel_historical_measurement(copy_root):
    name = 'src/contextproof/reuse.py'
    ledger = json.loads((copy_root / 'research/claims.json').read_text())
    archive = ledger['historical_sources'][name]
    path = copy_root / archive
    path.write_text(path.read_text() + '\n# changed archived implementation\n')
    edit(copy_root, lambda j: j['evidence_sha256'].update(
        {name: hashlib.sha256(path.read_bytes()).hexdigest(),
         archive: hashlib.sha256(path.read_bytes()).hexdigest()}))
    with pytest.raises(ValueError, match='differs from measured'):
        claims.validate(copy_root, validate_artifacts=False)


@pytest.mark.parametrize('tamper', ['missing_file', 'missing_hash', 'missing_mapping',
                                   'remapped_file', 'extra_mapping', 'changed_archive'])
def test_historical_archive_identity_cannot_be_dropped_or_remapped(copy_root, tamper):
    ledger = json.loads((copy_root / 'research/claims.json').read_text())
    name = 'src/contextproof/reuse.py'
    archive = ledger['historical_sources'][name]
    if tamper == 'missing_file':
        (copy_root / archive).unlink()
    elif tamper == 'missing_hash':
        edit(copy_root, lambda j: j['evidence_sha256'].pop(archive))
    elif tamper == 'missing_mapping':
        edit(copy_root, lambda j: j['historical_sources'].pop(name))
    elif tamper == 'remapped_file':
        edit(copy_root, lambda j: j['historical_sources'].update(
            {name: j['historical_sources']['src/contextproof/graph.py']}))
    elif tamper == 'extra_mapping':
        edit(copy_root, lambda j: j['historical_sources'].update(
            {'src/contextproof/new.py': archive}))
    else:
        path = copy_root / archive
        path.write_bytes(path.read_bytes() + b'\n# tampered\n')
    with pytest.raises((ValueError, OSError)):
        claims.validate(copy_root, validate_artifacts=False)


@pytest.mark.parametrize('change', ['changed', 'added', 'deleted'])
def test_current_runtime_can_evolve_without_relabeling_old_measurements(copy_root, change):
    name = 'src/contextproof/reuse.py'
    if change == 'changed':
        (copy_root / name).write_text('current_feature = True\n')
    elif change == 'added':
        (copy_root / 'src/contextproof/current_catalog.py').write_text('new_feature = True\n')
    else:
        (copy_root / name).unlink()
    report = claims.validate(copy_root, validate_artifacts=False)
    assert report['historical_implementation']['current_runtime_evolved']
    assert report['historical_implementation']['binding'] == 'archived_source'
    assert report['historical_implementation']['measured_commit'] == claims.MEASURED_COMMIT
    assert report['maturity'] == 'mature_research_not_established'
    assert report['metrics']['complete_graphs'] == 0
    ledger = json.loads((copy_root / 'research/claims.json').read_text())
    measured = json.loads((copy_root / claims.HOLDOUT).read_text())['provenance']['implementation_files']
    assert all(ledger['evidence_sha256'][path] == value for path, value in measured.items())


def test_rehashing_provenance_cannot_change_the_registered_measured_source(copy_root):
    path = copy_root / claims.HOLDOUT
    record = json.loads(path.read_text())
    record['provenance']['implementation_files']['src/contextproof/reuse.py'] = '0' * 64
    path.write_text(json.dumps(record))
    edit(copy_root, lambda j: j['evidence_sha256'].update(
        {claims.HOLDOUT: hashlib.sha256(path.read_bytes()).hexdigest()}))
    with pytest.raises(ValueError, match='provenance differs from measured profile'):
        claims.validate(copy_root, validate_artifacts=False)


def test_legacy_ledger_still_requires_the_original_current_runtime(copy_root):
    ledger = json.loads((copy_root / 'research/claims.json').read_text())
    for original, archived in ledger['historical_sources'].items():
        (copy_root / original).write_bytes((copy_root / archived).read_bytes())
    edit(copy_root, lambda j: j.pop('historical_sources'))
    report = claims.validate(copy_root, validate_artifacts=False)
    assert report['historical_implementation']['binding'] == 'current_runtime_legacy'
    assert report['maturity'] == 'mature_research_not_established'
    name = 'src/contextproof/reuse.py'
    path = copy_root / name
    path.write_bytes(path.read_bytes() + b'\n# current runtime drift\n')
    edit(copy_root, lambda j: j['evidence_sha256'].update(
        {name: hashlib.sha256(path.read_bytes()).hexdigest()}))
    with pytest.raises(ValueError, match='differs from measured'):
        claims.validate(copy_root, validate_artifacts=False)


@pytest.mark.parametrize('key,value', [('baseline', 'warm_ast_rebuild'), ('unit', 'anchor')])
def test_comparator_and_unit_bound(copy_root, key, value):
    edit(copy_root, lambda j: j['holdout'].update({key: value}))
    with pytest.raises(ValueError, match='comparator or observation unit'):
        claims.validate(copy_root, validate_artifacts=False)


def test_cli_maturity_gate_and_generated_page_drift(tmp_path, monkeypatch, capsys):
    report = claims.validate(claims.ROOT)
    monkeypatch.setattr(claims, 'ROOT', tmp_path)
    monkeypatch.setattr(claims, 'validate', lambda root: deepcopy(report))
    for lang in ('en', 'zh'):
        directory = tmp_path / 'docs' / lang
        directory.mkdir(parents=True)
        (directory / 'RESEARCH_STATUS.md').write_text(claims.render(report, lang))
    assert claims.main([]) == 0
    assert claims.main(['--require-mature']) == 2
    path = tmp_path / 'docs/en/RESEARCH_STATUS.md'
    path.write_text('mature research established')
    assert claims.main([]) == 1
    assert claims.main(['--write-docs']) == 0
    assert path.read_text() == claims.render(report, 'en')
    assert 'record_validation' in capsys.readouterr().out


def test_docs_match_bilingual_metrics():
    report = claims.validate(claims.ROOT)
    for lang in ('en', 'zh'):
        text = claims.render(report, lang)
        assert '0/768' in text and '24/25' in text
        assert '53.92%' in text and '37.45%' in text
        assert claims.MEASURED_COMMIT in text
        assert 'frozen-20261004-source/contextproof' in text
        assert (claims.ROOT / f'docs/{lang}/RESEARCH_STATUS.md').read_text() == text
