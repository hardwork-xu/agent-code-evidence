"""Exact frozen denominator checks using synthetic scores only / 仅合成分数核对分母。"""

import copy
import json
from pathlib import Path

import pytest

from benchmarks.external_context.analyze import summarize
from benchmarks.external_context.scoring import overlap


def synthetic_frozen_scores(*, no_target=False):
    # Metadata only: no query, dataset CSV, patch or measured result is read.
    # 仅读协议元数据；不读取问题、CSV、补丁或实测结果。
    path = Path(__file__).parents[1] / "benchmarks/external_context/protocol.json"
    protocol = json.loads(path.read_text())
    tasks = []
    for selected in protocol["selection"]["tasks"]:
        tasks.append({
            "instance_id": selected["instance_id"], "repo": selected["repo"],
            "prediction_status": "failed", "failure_category": "synthetic_timeout",
            "scores": [
                {"method": method, "budget": budget,
                 "line": overlap(set(), set() if no_target else {1}),
                 "file": overlap(set(), {1})}
                for method in protocol["methods"] for budget in protocol["budgets"]
            ],
        })
    return {"tasks": tasks}, protocol


@pytest.mark.parametrize("no_target", [False, True])
def test_review_all_39_failed_tasks_keep_18_combinations_and_six_repositories(no_target):
    data, protocol = synthetic_frozen_scores(no_target=no_target)
    assert len(data["tasks"]) == 39
    assert len(protocol["methods"]) * len(protocol["budgets"]) == 18
    assert sum(len(t["scores"]) for t in data["tasks"]) == 702
    summary = summarize(data, protocol)
    assert summary["selected_tasks"] == 39
    assert summary["repositories"] == 6
    assert summary["prediction_statuses"] == {"failed": 39}
    assert summary["failure_categories"] == {"synthetic_timeout": 39}
    for method in protocol["methods"]:
        for budget in protocol["budgets"]:
            cells = [c for c in summary["per_repo"]
                     if c["method"] == method and c["budget"] == budget]
            assert len(cells) == 6
            assert sum(c["selected"] for c in cells) == 39
            assert sum(c["prediction_failures"] for c in cells) == 39
            assert sum(c["line"]["no_target"] for c in cells) == (39 if no_target else 0)
            assert sum(c["line"]["scorable"] for c in cells) == (0 if no_target else 39)
    for row in summary["macro"]:
        assert row["line"]["f1"] == (None if no_target else 0.0)
        assert row["line"]["scorable_repositories"] == (0 if no_target else 6)
        assert row["file"]["f1"] == 0.0
        assert row["file"]["scorable_repositories"] == 6
    assert summary["advance_to_confirmatory"] is False
    assert summary["mature_research_established"] is False


@pytest.mark.parametrize("mutation", ["missing_task", "duplicate_task", "wrong_repo",
                                      "missing_method", "duplicate_method"])
def test_review_summary_refuses_to_change_frozen_denominator(mutation):
    data, protocol = synthetic_frozen_scores()
    if mutation == "missing_task":
        data["tasks"].pop()
    elif mutation == "duplicate_task":
        data["tasks"][-1] = copy.deepcopy(data["tasks"][0])
    elif mutation == "wrong_repo":
        data["tasks"][0]["repo"] = "synthetic/wrong"
    elif mutation == "missing_method":
        data["tasks"][0]["scores"].pop()
    else:
        data["tasks"][0]["scores"].append(copy.deepcopy(data["tasks"][0]["scores"][0]))
    with pytest.raises(ValueError):
        summarize(data, protocol)
