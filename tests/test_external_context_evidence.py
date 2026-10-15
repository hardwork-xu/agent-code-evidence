"""Published-result tampering must fail / 公开证据篡改必须失败。"""
import json
import shutil

import pytest
from benchmarks.external_context.check import RUN, validate


def test_frozen_result_is_recomputed():
    result = validate()
    assert result['selected_tasks'] == 39
    assert result['score_cells'] == 702
    assert result['prediction_statuses'] == {'predicted': 34, 'failed': 5}
    assert result['advance_to_confirmatory'] is False
    assert result['mature_research_established'] is False


@pytest.mark.parametrize('name', ['prediction-000.json', 'manifest.json', 'prediction-seal.json'])
def test_published_bundle_bytes_changed(tmp_path, name):
    run = tmp_path / 'run'
    shutil.copytree(RUN, run)
    (run / name).write_bytes((run / name).read_bytes() + b' ')
    with pytest.raises(ValueError):
        validate(run)


def test_positive_summary_cannot_replace_negative_result(tmp_path):
    run = tmp_path / 'run'
    shutil.copytree(RUN, run)
    summary = json.loads((run / 'summary.json').read_text())
    summary['advance_to_confirmatory'] = True
    (run / 'summary.json').write_text(json.dumps(summary))
    with pytest.raises(ValueError, match='summary'):
        validate(run)
