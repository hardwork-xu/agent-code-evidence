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


def test_rehashing_changed_runtime_cannot_relabel_historical_measurement(copy_root):
    name = 'src/contextproof/reuse.py'
    path = copy_root / name
    path.write_text(path.read_text() + '\n# changed runtime\n')
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
        assert (claims.ROOT / f'docs/{lang}/RESEARCH_STATUS.md').read_text() == text
