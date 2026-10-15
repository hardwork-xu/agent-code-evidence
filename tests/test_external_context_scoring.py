"""Independent proxy-label edge cases / 独立代理标签边界测试。"""
import pytest
from benchmarks.external_context.scoring import edit_targets, overlap, safe_path, score_prediction


def test_multiple_edits_and_insertion_have_base_coordinates():
    patch = '--- a/x.py\n+++ b/x.py\n@@ -3,3 +3,4 @@\n c\n-old\n+new\n+added\n c\n@@ -9,0 +11 @@\n+extra\n'
    assert edit_targets(patch) == {'removed_lines': {('x.py', 4)},
                                  'edited_base_files': {'x.py'}, 'hunks': 2}


def test_header_like_content_in_hunk_is_not_a_new_path():
    patch = '--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n--- value\n+++ other\n'
    assert edit_targets(patch)['removed_lines'] == {('x.py', 1)}


def test_pure_insert_has_no_invented_line_targets():
    patch = '--- a/x.py\n+++ b/x.py\n@@ -2,0 +3 @@\n+new\n'
    assert edit_targets(patch)['removed_lines'] == set()
    assert score_prediction(set(), patch, {'x.py': 3})['line']['status'] == 'no_target'


def test_new_file_is_not_misrepresented_as_base_source():
    patch = '--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+new\n'
    assert edit_targets(patch)['edited_base_files'] == set()


def test_unavailable_python_labels_stay_in_denominator():
    patch = '--- a/x.py\n+++ b/x.py\n@@ -2 +2 @@\n-old\n+new\n'
    score = score_prediction(set(), patch, {})
    assert score['line']['target'] == 1
    assert score['line']['recall'] == 0
    assert score['out_of_corpus_target_lines'] == 1


def test_counts_do_not_double_count_and_empty_prediction_is_zero():
    assert overlap({1, 2}, {2, 3})['f1'] == .5
    assert overlap(set(), {2})['f1'] == 0
    assert overlap({2}, set())['f1'] is None


@pytest.mark.parametrize('patch', ['', '--- a/x.py\n+++ b/x.py\n@@ -1,2 +1 @@\n-a\n+b\n',
                                  '--- a/../x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n'])
def test_invalid_patch_rejected(patch):
    with pytest.raises(ValueError):
        edit_targets(patch)


@pytest.mark.parametrize('path', ['../x', '/x', 'x//y', './x', 'x\\y', '', '.'])
def test_paths_rejected(path):
    with pytest.raises(ValueError):
        safe_path(path)


def test_out_of_corpus_prediction_rejected():
    with pytest.raises(ValueError):
        score_prediction({('x.py', 4)}, 'irrelevant', {'x.py': 3})
