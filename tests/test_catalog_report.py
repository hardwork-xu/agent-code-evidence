"""Reporting retains regressions and measured units / 报告保留退化并核对单位。"""
from benchmarks.catalog_reuse import report
from benchmarks.catalog_reuse.suite import METHODS


def group(reduction):
    return {'methods': {METHODS[2]: {'replay': {'median_ms': 100.0}},
                        METHODS[3]: {'replay': {'median_ms': 107.142857}}},
            'primary_replay_reduction_D_vs_C': reduction,
            'secondary_replay_reduction_D_vs_A': 0.12,
            'median_peak_rss_ratio_D_vs_C': 1.15,
            'replay_target_met': False}


def test_regression_is_shown_in_both_languages_in_same_units():
    summary = {'groups': {'fixture/repo': group(-0.07142857)}}
    english = report.table(summary, False)
    chinese = report.table(summary, True)
    for rendered in [english, chinese]:
        assert '| fixture/repo | 100.000 | 107.143 | -7.14% | 12.00% | 1.150 | no |' in rendered


def test_all_groups_are_reported_including_failure():
    summary = {'groups': {'failed/repo': group(-0.10), 'other/repo': group(0.05)}}
    for language in [False, True]:
        rendered = report.table(summary, language)
        assert '| failed/repo |' in rendered and '| other/repo |' in rendered
        assert '-10.00%' in rendered and '5.00%' in rendered
