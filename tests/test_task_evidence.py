"""Harness integrity tests; these synthetic unit fixtures are not study cases."""
import io
import json
from pathlib import Path
import tarfile

import pytest

from benchmarks.task_evidence.suite import (
    aggregate, anchors_for, digest, lexical_lines, safe_extract, score,
    stale_current_lines, verified_texts,
)
from benchmarks.task_evidence.worker import compile_function, find_function

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_protocol_and_nine_upstream_cases_are_bound():
    base = ROOT / 'benchmarks/task_evidence'
    manifest = json.loads((base / 'manifest.json').read_text())
    assert digest((base / 'PROTOCOL.md').read_bytes()) == manifest['protocol_sha256']
    assert len(manifest['cases']) == 9
    assert len({case['id'] for case in manifest['cases']}) == 9
    assert {case['repository'] for case in manifest['cases']} == {'packaging', 'attrs', 'pluggy'}
    for repository in manifest['repositories'].values():
        for state, pin in repository['versions'].items():
            assert len(pin['commit']) == 40
            assert pin['source_files']
            for license_file in pin['license_files']:
                local = base / 'licenses' / repository['repository'].split('/')[-1] / state / Path(license_file['path']).name
                if not license_file['path'].startswith(('docs/', 'tasks/')):
                    assert digest(local.read_bytes()) == license_file['sha256']


def test_source_validation_rejects_extra_files_and_modified_bytes(tmp_path):
    source = tmp_path / 'src' / 'package'
    source.mkdir(parents=True)
    f = source / '__init__.py'
    f.write_text('value = 1\n')
    pin = {'source_files': {'src/package/__init__.py': digest(f.read_bytes())}}
    assert verified_texts(tmp_path, pin) == {'src/package/__init__.py': 'value = 1\n'}
    f.write_text('value = 2\n')
    with pytest.raises(ValueError, match='bytes changed'):
        verified_texts(tmp_path, pin)
    f.write_text('value = 1\n')
    (source / 'extra.py').write_text('')
    with pytest.raises(ValueError, match='catalog'):
        verified_texts(tmp_path, pin)


def test_extraction_refuses_traversal_before_writing(tmp_path):
    archive = tmp_path / 'bad.tar.gz'
    with tarfile.open(archive, 'w:gz') as tf:
        info = tarfile.TarInfo('root/../escape.py')
        info.size = 1
        tf.addfile(info, io.BytesIO(b'x'))
    destination = tmp_path / 'out'
    with pytest.raises(ValueError, match='unsafe'):
        safe_extract(archive, destination, digest(archive.read_bytes()))
    assert not destination.exists()
    assert not (tmp_path / 'escape.py').exists()


def test_stale_span_credit_requires_exact_unique_current_bytes():
    old = [{'path': 'x.py', 'text': 'return 1\n'}]
    assert stale_current_lines(old, {'x.py': '# moved\nreturn 1\n'})[0] == {('x.py', 2)}
    assert not stale_current_lines(old, {'x.py': 'return 2\n'})[0]
    lines, states = stale_current_lines(old, {'x.py': 'return 1\nreturn 1\n'})
    assert not lines
    assert states['ambiguous_spans'] == 1


def test_lexical_retrieval_has_exact_graph_line_budget():
    texts = {'a.py': 'irrelevant\n' * 23, 'b.py': 'wanted_name\n' * 23}
    selected = lexical_lines(texts, 'wanted_name', 7)
    assert len(selected) == 7
    assert {path for path, line in selected} == {'b.py'}
    assert lexical_lines(texts, 'wanted_name', 0) == set()


def test_macro_recall_is_per_task_not_pooled_lines_and_excludes_failed_case():
    rows = [
        {'repository': 'one', 'eligible': True,
         'metrics': {'graph': score({('a', 1)}, {('a', 1)})}},
        {'repository': 'one', 'eligible': True,
         'metrics': {'graph': score(set(), {('b', i) for i in range(100)})}},
        {'repository': 'two', 'eligible': False,
         'metrics': {'graph': score(set(), {('c', 1)})}},
    ]
    result = aggregate(rows)
    assert result['all']['cases'] == 2
    assert result['all']['methods']['graph']['macro_recall'] == .5
    assert result['two']['cases'] == 0
    assert score(set(), set())['recall'] is None


def test_property_duplicates_remain_ambiguous_and_exact_test_is_selected():
    source = 'class C:\n @property\n def f(self): return 1\n @f.setter\n def f(self, value): pass\n'
    records, missing = anchors_for({'x.py': source}, [{'path': 'x.py', 'symbol': 'C.f'}])
    assert len(records) == 2
    assert not missing
    with pytest.raises(ValueError, match='nonunique'):
        find_function(source, 'C.f')


@pytest.mark.parametrize('future, expected', [('', ['called']), ('from __future__ import annotations\n', [])])
def test_extracted_function_preserves_original_annotation_execution(future, expected):
    # The worker itself enables postponed annotations. Neither its future flags
    # nor a caller's compilation flags may leak into the original test function.
    source = future + (
        'class Tests:\n'
        ' def test_annotation(self):\n'
        '  class Nested:\n'
        '   x: observe()\n'
        '  return Nested.__annotations__["x"]\n'
    )
    seen = []
    def observe():
        seen.append('called')
        return int
    namespace = {'observe': observe}
    code, name = compile_function(source, 'Tests.test_annotation', 'original.py')
    exec(code, namespace)
    result = namespace[name](None)
    assert seen == expected
    assert result == ('observe()' if future else int)


def test_partial_execution_checkpoints_each_completed_child(tmp_path, monkeypatch):
    from scripts import run_task_evidence as runner
    test_root = tmp_path / 'sources' / 'demo' / 'after'
    test_root.mkdir(parents=True)
    test_file = test_root / 'test_example.py'
    test_file.write_text('def test_example(): pass\n')
    scratch = tmp_path / 'scratch'
    scratch.mkdir()
    case = {'id': 'one', 'repository': 'demo', 'test_path': test_file.name,
            'test_sha256': digest(test_file.read_bytes())}
    calls = []
    def isolated(*args):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError('simulated interruption')
        return {'case_id': 'one', 'passed': True, 'invocations': []}
    monkeypatch.setattr(runner, 'isolated', isolated)
    progress = tmp_path / 'progress.json'
    with pytest.raises(RuntimeError, match='interruption'):
        runner.execute({'cases': [case]}, tmp_path / 'sources', scratch, progress)
    checkpoint = json.loads(progress.read_text())
    assert checkpoint['completed_children'] == 1
    assert checkpoint['expected_children'] == 8
    assert len(checkpoint['runs'][0]['runs']['before']) == 1


def test_traced_untraced_outcomes_ignore_trace_content_but_not_assertions():
    from scripts.run_task_evidence import outcomes_match
    good = {'invocations': [{'invocation': {}, 'passed': True, 'failure': None, 'lines': [['x.py', 1]]}]}
    control = {'invocations': [{'invocation': {}, 'passed': True, 'failure': None, 'lines': []}]}
    assert outcomes_match(good, control)
    control['invocations'][0].update(passed=False, failure={'type': 'AssertionError', 'message': ''})
    assert not outcomes_match(good, control)
    assert not outcomes_match({'harness_error': 'failure'}, control)


def test_final_integrity_rejects_changed_benchmark_code_before_source_read(tmp_path, monkeypatch):
    from scripts import run_task_evidence as runner
    tracked = tmp_path / 'worker.py'
    tracked.write_text('before\n')
    provenance = {'implementation_sha256': {'worker.py': digest(tracked.read_bytes())}}
    tracked.write_text('after\n')
    monkeypatch.setattr(runner, 'REPO', tmp_path)
    with pytest.raises(ValueError, match='implementation changed'):
        runner.verify_inputs_unchanged(provenance, {}, tmp_path)
