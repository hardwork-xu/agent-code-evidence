"""Runner/provenance regressions / 运行器与来源完整性回归。

Synthetic unit-test sources and altered copies stay in pytest temporary folders.
They are never added to retained study results or reported as measurements.
合成测试源码与篡改副本仅位于临时目录，不加入实验结果、不冒充实测。
"""
import ast
import builtins
from copy import deepcopy
from pathlib import Path
import shutil

import pytest

from benchmarks.global_bindings import report, study
from contextproof import graph as graph_module


RESULTS = study.ROOT / 'benchmarks/global_bindings/results/development-20261014'


@pytest.mark.parametrize('newline', ['\n', '\r\n', '\r'])
@pytest.mark.parametrize('embedded', ['\u2028', '\u2029', '\f', '\v'])
def test_anchor_selection_uses_python_physical_lines(newline, embedded):
    source = newline.join([f'LABEL = "one{embedded}two"', 'def getter():', '    return LABEL', ''])
    selected = study.select(source, 'app.py', 'getter')
    assert selected['text'] == newline.join(['def getter():', '    return LABEL', ''])
    assert (selected['start_line'], selected['end_line']) == (2, 3)
    assert selected['text_sha256'] == study.digest(selected['text'].encode())


@pytest.mark.parametrize('source', ['def other():\n    pass\n',
                                  'def getter():\n    pass\ndef getter():\n    pass\n'])
def test_anchor_selection_rejects_absent_or_ambiguous_identity(source):
    with pytest.raises(ValueError, match='absent or ambiguous'):
        study.select(source, 'app.py', 'getter')


@pytest.mark.parametrize('path', ['', '../file.py', '/file.py', 'x//file.py',
                                 'x\\file.py', 'x:file.py', 'bad\0.py'])
def test_provider_rejects_unsafe_names(tmp_path, path):
    with pytest.raises(ValueError):
        study.safe_asset(tmp_path, path)


def test_provider_rejects_file_and_directory_symlinks(tmp_path):
    ordinary = tmp_path / 'ordinary.py'
    ordinary.write_text('x = 1\n')
    (tmp_path / 'linked.py').symlink_to(ordinary)
    (tmp_path / 'linked-dir').symlink_to(tmp_path, target_is_directory=True)
    for name in ['linked.py', 'linked-dir/ordinary.py']:
        with pytest.raises(ValueError, match='symlink'):
            study.safe_asset(tmp_path, name)


def fake_runner_inputs(tmp_path, monkeypatch):
    """A deliberately executable sentinel in provider source must never run.

    提供者源码的顶层异常仅供 AST 阅读；运行它会使测试失败。
    """
    real = study.read(study.PIN)
    sentinel = 'raise RuntimeError("provider_source_was_executed")\nx = 0\ndef getter():\n    return x\n'
    raw = sentinel.encode()
    sources = []
    for index in range(15):
        directory = 'source-' + str(index)
        destination = tmp_path / directory
        destination.mkdir()
        (destination / 'app.py').write_bytes(raw)
        sources.append({'repository': 'synthetic/repo-' + str(index), 'sha': str(index).zfill(40),
                        'directory': directory, 'files': {'app.py': {'bytes': len(raw),
                        'sha256': study.digest(raw)}}, 'source_role': 'synthetic_unit_test'})
    inputs = {'schema_version': 1, 'head_panel': [{} for _ in range(8)], 'sources': sources,
              'own_fixtures': real['own_fixtures'],
              'anchors': [{'repository': row['repository'], 'sha': row['sha'], 'path': 'app.py',
                           'symbol': 'getter', 'role': 'synthetic_unit_test'} for row in sources[:10]]}
    pin = tmp_path / 'test-inputs.json'
    pin.write_bytes(study.canonical(inputs))
    protocol = deepcopy(study.read(study.PROTOCOL))
    protocol['inputs_sha256'] = study.digest(pin.read_bytes())
    protocol_path = tmp_path / 'test-protocol.json'
    protocol_path.write_bytes(study.canonical(protocol))
    monkeypatch.setattr(study, 'PIN', pin)
    monkeypatch.setattr(study, 'PROTOCOL', protocol_path)
    return inputs, tmp_path / 'test-result.json'


def test_runner_executes_only_fixed_own_fixtures_and_reads_provider_as_ast(tmp_path, monkeypatch):
    inputs, output = fake_runner_inputs(tmp_path, monkeypatch)
    seen = []
    original = builtins.exec

    def recording_exec(code, namespace, locals_=None):
        seen.append(getattr(code, 'co_filename', None))
        return original(code, namespace, locals_)

    monkeypatch.setattr(builtins, 'exec', recording_exec)
    result = study.run('candidate', tmp_path, output)
    assert seen.count('own_fixture.py') == len(inputs['own_fixtures']) == 32
    assert 'app.py' not in seen
    assert len(result['assets']) == 15 and len(result['natural']) == 10
    assert all(row['status'] == 'built' for row in result['natural'])
    assert result['upstream_source_executed_by_graph_runner'] is False
    assert result['performance_measured'] is False
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        study.run('candidate', tmp_path, output)
    assert output.read_bytes() == before


def test_runner_rejects_changed_source_bytes_without_result(tmp_path, monkeypatch):
    inputs, output = fake_runner_inputs(tmp_path, monkeypatch)
    path = tmp_path / inputs['sources'][0]['directory'] / 'app.py'
    path.write_text('x = 99\n')
    with pytest.raises(ValueError, match='source bytes differ'):
        study.run('candidate', tmp_path, output)
    assert not output.exists()


def test_runner_rejects_input_hash_change_before_own_execution(tmp_path, monkeypatch):
    _, output = fake_runner_inputs(tmp_path, monkeypatch)
    study.PIN.write_bytes(study.PIN.read_bytes() + b' ')

    def forbidden_exec(*_args, **_kwargs):
        pytest.fail('own execution preceded source/protocol hash validation')

    monkeypatch.setattr(builtins, 'exec', forbidden_exec)
    with pytest.raises(ValueError, match='fingerprint mismatch'):
        study.run('candidate', tmp_path, output)
    assert not output.exists()


def test_runner_keeps_failed_own_and_natural_rows(tmp_path, monkeypatch):
    _, output = fake_runner_inputs(tmp_path, monkeypatch)
    original = graph_module.build_graph

    def injected_failure(texts, snapshot, anchors, **policy):
        if snapshot == 'own-assign' or snapshot == '0000000000000000000000000000000000000000':
            raise RuntimeError('synthetic fault injection')
        return original(texts, snapshot, anchors, **policy)

    monkeypatch.setattr(graph_module, 'build_graph', injected_failure)
    result = study.run('candidate', tmp_path, output)
    assert len(result['own']) == 32 and len(result['natural']) == 10
    assert result['own'][0]['status'] == 'failed'
    assert result['own'][0]['error_type'] == 'RuntimeError'
    assert result['natural'][0]['status'] == 'failed'
    assert result['natural'][0]['error_type'] == 'RuntimeError'
    assert all(row['status'] == 'ok' for row in result['own'][1:])


@pytest.fixture
def copied_results(tmp_path):
    # Real retained files are copied; mutations never touch the original evidence.
    # 仅篡改复制品，原始实测文件不被修改。
    destination = tmp_path / 'copied-results'
    shutil.copytree(RESULTS, destination)
    return destination


def change_candidate(directory, mutate):
    path = directory / 'candidate.json'
    payload = report.read(path)
    mutate(payload)
    path.write_bytes(report.canonical(payload) + b'\n')


def test_retained_pair_and_generated_reports_have_exact_fixed_keys():
    summary = report.validate_results(RESULTS)
    assert summary == report.read(RESULTS / 'summary.json')
    assert len(summary['natural']) == 10
    assert set(summary['index']['files']) == {'baseline.json', 'candidate.json'}
    for language in ['en', 'zh']:
        assert (RESULTS / ('REPORT_' + language + '.md')).read_text() == report.render(summary, language)


def test_byte_tampering_fails_index_even_with_same_json_content(copied_results):
    path = copied_results / 'candidate.json'
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError, match='integrity index'):
        report.validate_results(copied_results)


@pytest.mark.parametrize('panel', ['own', 'natural', 'assets'])
@pytest.mark.parametrize('action', ['drop', 'duplicate'])
def test_missing_and_duplicated_rows_are_rejected_before_digest_check(copied_results, panel, action):
    def mutate(payload):
        if action == 'drop':
            payload[panel].pop()
        else:
            payload[panel].append(deepcopy(payload[panel][0]))
    change_candidate(copied_results, mutate)
    with pytest.raises(ValueError, match='denominator|duplicate'):
        report.validate_results(copied_results, require_index=False)


@pytest.mark.parametrize('mutate', [
    lambda p: p.update(role='baseline'),
    lambda p: p.update(run_id='globals-20261014T000000Z-baseline'),
    lambda p: p.update(upstream_source_executed_by_graph_runner=True),
    lambda p: p.update(performance_measured=True),
    lambda p: p['engine'].update(resolver_version=3),
    lambda p: p['own'][0].update(source_sha256='0' * 64),
    lambda p: p['own'][0].update(possible_global_write=False),
    lambda p: p['own'][0].update(expected_runtime_change=False),
    lambda p: p['own'][0].update(runtime_changed=False),
    lambda p: p['natural'][0].update(symbol='another_symbol'),
    lambda p: p['assets'][0].update(files=999),
])
def test_raw_record_cannot_redefine_fixed_expected_labels(copied_results, mutate):
    change_candidate(copied_results, mutate)
    with pytest.raises(ValueError):
        report.validate_results(copied_results, require_index=False)


def test_failure_rows_are_retained_as_results_not_filtered(copied_results):
    def mutate(payload):
        own = payload['own'][0]
        for field in ['graph', 'runtime_changed', 'before', 'after']:
            own.pop(field)
        own.update(status='failed', error_type='RuntimeError')
        natural = payload['natural'][0]
        natural.pop('graph')
        natural.pop('anchor_text_sha256')
        natural.update(status='failed', error_type='ValueError')
    change_candidate(copied_results, mutate)
    summary = report.validate_results(copied_results, require_index=False)
    assert summary['own']['candidate']['cases'] == 32
    assert summary['own']['candidate']['failed'] == 1
    assert summary['natural_statuses']['candidate']['failed'] == 1
    assert len(summary['natural']) == 10


def test_watched_edges_pair_actual_union_and_keep_distinct_source_nodes():
    def edge(source, expression, status):
        return {'source': source * 64, 'expression': expression, 'operation': 'read',
                'status': status, 'reason': 'source binding'}
    before = [edge('a', 'same', 'resolved'), edge('b', 'same', 'resolved')]
    after = [edge('b', 'same', 'unresolved'), edge('c', 'new', 'unresolved')]
    pairs = report.compare_edges(before, after)
    assert len(pairs) == 3
    assert pairs[0]['candidate'] is None
    assert pairs[1]['baseline']['source'] != pairs[0]['baseline']['source']
    assert pairs[2]['baseline'] is None
    assert all(pair['changed'] for pair in pairs)


def test_duplicate_watched_key_is_rejected(copied_results):
    def mutate(payload):
        graph = payload['own'][0]['graph']
        graph['watched_edges'].append(deepcopy(graph['watched_edges'][0]))
        graph['edges'] += 1
    change_candidate(copied_results, mutate)
    with pytest.raises(ValueError, match='duplicate watched edge'):
        report.validate_results(copied_results, require_index=False)


def test_dropped_amendments_are_rejected(copied_results):
    source = next((copied_results / 'amendments').iterdir())
    source.unlink()
    with pytest.raises(ValueError, match='integrity index'):
        report.validate_results(copied_results)


def test_generation_never_overwrites_retained_report(copied_results):
    before = (copied_results / 'summary.json').read_bytes()
    with pytest.raises(ValueError, match='never overwrite'):
        report.generate_report(copied_results)
    assert (copied_results / 'summary.json').read_bytes() == before


def test_graph_runner_has_no_dynamic_upstream_import_or_execution_path():
    tree = ast.parse(Path(study.__file__).read_text())
    executions = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                  and isinstance(node.func, ast.Name) and node.func.id == 'exec']
    assert len(executions) == 1
    rendered = ast.unparse(executions[0])
    assert "compile(text, 'own_fixture.py', 'exec')" in rendered
    assert 'importlib' not in Path(study.__file__).read_text()
