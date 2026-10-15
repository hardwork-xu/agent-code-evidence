"""Exploratory labels remain explicit / 消融标签不能冒充主要实验。"""
from copy import deepcopy
import pytest
from scripts.run_selective_ablation import METHODS, analyze
from scripts.run_selective_reuse import replay_group, synthetic_loaders


def test_ablation_keeps_raw_labels_and_has_no_confirmatory_target():
    loaders, ids, anchors = synthetic_loaders(10, 'unrelated_file_change')
    rows = replay_group('synthetic:10:unrelated_file_change', loaders, ids, anchors,
                        1, methods=METHODS)
    raw = {'status': 'passed', 'rows': rows, 'repetitions': 1}
    saved = deepcopy(raw)
    report = analyze(raw)
    assert raw == saved
    assert 'utility_target_met' not in report
    assert 'natural_repositories_meeting_target' not in report
    assert 'read_set_any_status' in report['groups']['synthetic:10:unrelated_file_change']
    assert 'Exploratory' in report['interpretation']
    raw['rows'].pop()
    with pytest.raises(ValueError):
        analyze(raw)
