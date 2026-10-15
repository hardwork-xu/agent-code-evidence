"""Signed-unit and input-substitution controls / 有符号单位与输入替换反例。"""
import json
import builtins
import shutil

import pytest

from benchmarks.known_task_execution import secondary_report as report


def test_frozen_analysis_executes_verified_bytes_after_source_swap(tmp_path, monkeypatch):
    source = report.Path(report.__file__).with_name('analyze_sensitivity.py')
    target = tmp_path / source.name
    target.write_bytes(source.read_bytes())

    def swap_before_compile(raw, filename, mode):
        target.write_text('SWAPPED = True\n')
        return builtins.compile(raw, filename, mode)

    monkeypatch.setattr(report, 'compile', swap_before_compile, raising=False)
    loaded = report.load_frozen_analysis(target)
    assert loaded.METHODS[0] == 'bm25_windows'
    assert not hasattr(loaded, 'SWAPPED')
    assert target.read_text() == 'SWAPPED = True\n'


@pytest.fixture(scope='module')
def observed():
    return report.verify()


def test_percentage_points_do_not_become_relative_percent():
    assert report.points(-0.1430078976034858) == '-14.300790'
    assert report.points(0.000456180671565) == '+0.045618'
    assert report.percent(0.00881158026916177) == '0.881158%'
    assert report.points(None) == 'undefined'


@pytest.mark.parametrize('language', ['en', 'zh'])
def test_bilingual_reports_retain_sign_flip_and_negative_recall(observed, language):
    text = report.render(observed, language)
    assert '| all39 | `bm25_declarations` | -0.259808 | -9.722716 |' in text
    assert '| qualified30 | `bm25_declarations` | +0.045618 | -14.300790 |' in text
    assert '| qualified30 | `bm25_windows` | +0.191104 | -13.650599 |' in text
    assert '24' in text and '30' in text
    assert sum(line.startswith('| `') and ' | 16000 |' in line for line in text.splitlines()) == 6


def test_substituted_scientific_result_rejected(tmp_path):
    for name in report.PINS:
        if name.endswith('.json'):
            shutil.copyfile(report.DATA / name, tmp_path / name)
    target = tmp_path / 'result.json'
    result = json.loads(target.read_text())
    result['qualified_subset_tasks'] = 39
    target.write_text(json.dumps(result))
    with pytest.raises(ValueError, match='SHA256 mismatch'):
        report.verify(data=tmp_path)
