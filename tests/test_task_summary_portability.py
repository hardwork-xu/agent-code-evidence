"""Retained task summaries survive Python float-sum changes without tolerance."""
import json
import math
from pathlib import Path
import shutil

import pytest

from scripts.run_task_evidence import validate_result_bundle


ROOT = Path(__file__).resolve().parents[1]
STABLE = 0.33987077737077737
LEGACY = 0.3398707773707774


@pytest.fixture
def bundle(tmp_path):
    source = ROOT / 'benchmarks/task_evidence/results/primary-20261004'
    destination = tmp_path / 'result'
    shutil.copytree(source, destination)
    return destination


def change_summary(bundle, change):
    path = bundle / 'summary.json'
    summary = json.loads(path.read_text())
    change(summary)
    path.write_text(json.dumps(summary))


def set_macro(summary, value):
    summary['aggregate']['pluggy']['methods']['lexical_matched_lines']['macro_recall'] = value


def test_observed_ci_discrepancy_is_one_ulp_from_two_explicit_reductions():
    # Covered/witness counts from the three retained Pluggy cases, in case order.
    values = [1 / 48, 34 / 39, 16 / 126]
    sequential = 0.0
    for value in values:
        sequential += value
    assert math.fsum(values) / 3 == STABLE
    assert sequential / 3 == LEGACY
    assert LEGACY - STABLE == math.ulp(STABLE)


@pytest.mark.parametrize('value', [STABLE, LEGACY])
def test_primary_accepts_exact_historical_reduction_encodings(bundle, value):
    change_summary(bundle, lambda summary: set_macro(summary, value))
    assert validate_result_bundle(bundle)['children'] == 72


@pytest.mark.parametrize('value', [math.nextafter(STABLE, -math.inf),
                                  math.nextafter(LEGACY, math.inf),
                                  STABLE + 1e-12, True, math.nan, math.inf])
def test_no_adjacent_or_material_macro_tampering_is_accepted(bundle, value):
    change_summary(bundle, lambda summary: set_macro(summary, value))
    with pytest.raises(ValueError, match='exact stable/legacy'):
        validate_result_bundle(bundle)


@pytest.mark.parametrize('change', ['case-count', 'method-catalog', 'mean-lines', 'per-case-metric'])
def test_portability_does_not_relax_other_fields(bundle, change):
    if change == 'per-case-metric':
        path = bundle / 'cases.json'
        rows = json.loads(path.read_text())
        metric = rows[0]['metrics']['fresh_graph']
        metric['recall'] = math.nextafter(metric['recall'], math.inf)
        path.write_text(json.dumps(rows))
    else:
        def mutate(summary):
            if change == 'case-count':
                summary['cases'] += 1
            elif change == 'method-catalog':
                summary['aggregate']['pluggy']['methods']['extra'] = {}
            else:
                metric = summary['aggregate']['pluggy']['methods']['lexical_matched_lines']
                metric['mean_context_lines'] = math.nextafter(metric['mean_context_lines'], math.inf)
        change_summary(bundle, mutate)
    with pytest.raises(ValueError):
        validate_result_bundle(bundle)
