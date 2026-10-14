"""Independent synthetic diff cases / 独立合成反例，未读取评测补丁。

Edited base coordinates are localization proxies, never necessary-context labels.
旧版本编辑位置只用于定位代理指标，不代表必要上下文。
"""

import pytest

from benchmarks.external_context.scoring import edit_targets, score_prediction


def test_review_context_lines_advance_old_coordinates_only():
    patch = (
        "diff --git a/pkg/source.py b/pkg/source.py\n"
        "--- a/pkg/source.py\n+++ b/pkg/source.py\n"
        "@@ -5,4 +5,5 @@ function\n"
        " before\n-old\n+new\n+inserted\n after\n final\n"
        "@@ -20,2 +21,0 @@\n-last\n-last_too\n"
    )
    assert edit_targets(patch) == {
        "removed_lines": {("pkg/source.py", 6), ("pkg/source.py", 20),
                          ("pkg/source.py", 21)},
        "edited_base_files": {"pkg/source.py"},
        "hunks": 2,
    }


def test_review_deletion_and_no_newline_marker_keep_old_line_target():
    patch = (
        "diff --git a/gone.py b/gone.py\n"
        "deleted file mode 100644\n--- a/gone.py\n+++ /dev/null\n"
        "@@ -1 +0,0 @@\n-old\n\\ No newline at end of file\n"
    )
    score = score_prediction({("gone.py", 1)}, patch, {"gone.py": 1})
    assert score["line"]["target"] == 1
    assert score["line"]["f1"] == 1.0
    assert score["file"]["f1"] == 1.0


def test_review_insertion_scores_existing_file_without_inventing_line():
    patch = "--- a/existing.py\n+++ b/existing.py\n@@ -0,0 +1 @@\n+first\n"
    score = score_prediction({("existing.py", 2)}, patch, {"existing.py": 3})
    assert score["line"] == {
        "predicted": 1, "target": 0, "intersection": 0,
        "precision": None, "recall": None, "f1": None, "status": "no_target",
    }
    assert score["file"]["target"] == 1
    assert score["file"]["recall"] == 1.0


def test_review_mixed_absent_nonpython_and_new_file_do_not_shrink_denominator():
    patch = (
        "--- a/present.py\n+++ b/present.py\n@@ -2 +2 @@\n-old\n+new\n"
        "--- a/missing.py\n+++ b/missing.py\n@@ -9 +9 @@\n-old\n+new\n"
        "--- a/notes.md\n+++ b/notes.md\n@@ -1 +1 @@\n-old\n+new\n"
        "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+new\n"
    )
    score = score_prediction({("present.py", 2), ("present.py", 3)}, patch,
                             {"present.py": 3})
    assert score["line"]["target"] == 2
    assert score["line"]["predicted"] == 2
    assert score["line"]["precision"] == 0.5
    assert score["line"]["recall"] == 0.5
    assert score["file"]["target"] == 2
    assert score["file"]["recall"] == 0.5
    assert score["out_of_corpus_target_lines"] == 1
    assert score["non_python_removed_lines"] == 1
    assert score["non_python_edited_files"] == 1


@pytest.mark.parametrize("bad_line", [True, False, 0, -1, 1.0, "1"])
def test_review_prediction_coordinates_require_exact_positive_integer(bad_line):
    with pytest.raises(ValueError):
        score_prediction({("x.py", bad_line)}, "unused", {"x.py": 2})


@pytest.mark.parametrize(
    "patch",
    [
        "@@ -1 +1 @@\n-old\n+new\n",
        "--- a/x.py\n@@ -1 +1 @@\n-old\n+new\n",
        "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n-extra\n",
        "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n+extra\n",
        "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n"
        "diff --git a/y.py b/y.py\n@@ -1 +1 @@\n-second\n+replacement\n",
        "--- /dev/null\n+++ b/new.py\n@@ -1 +1 @@\n-impossible_old\n+new\n",
        "--- a/x.py\n+++ b/x.py\n@@ -1 +0 @@\n-old\n+new\n",
        "--- a/x.py\n+++ b/x.py\n@@ -0,0 +0,0 @@\n",
    ],
    ids=["orphan-hunk", "missing-new-header", "extra-removed-line",
         "extra-added-line", "stale-path-across-file-boundary",
         "new-file-deletes-base", "invalid-new-coordinate", "empty-change"],
)
def test_review_incomplete_diff_never_silently_discards_targets(patch):
    with pytest.raises(ValueError):
        edit_targets(patch)
