"""End-to-end sealed prediction scoring with local fixtures / 本地封存评分集成测试。"""
import argparse
import csv
import json

import pytest

from benchmarks.external_context.io import sha256, write_new
from benchmarks.external_context import runner


def fixture(tmp_path, monkeypatch):
    patch = '--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n'
    dataset = tmp_path / 'dataset.csv'
    with dataset.open('w', newline='') as stream:
        out = csv.DictWriter(stream, ['instance_id', 'repo', 'base_commit', 'patch'])
        out.writeheader()
        out.writerow({'instance_id': 'r-1', 'repo': 'o/r', 'base_commit': 'a' * 40, 'patch': patch})
    protocol = {'study_id': 'test', 'methods': ['bm25_windows'], 'budgets': [8000], 'dataset': {'sha256': sha256(dataset.read_bytes())},
                'selection': {'selected_tasks': 1, 'tasks': [
                    {'instance_id': 'r-1', 'repo': 'o/r', 'base_commit': 'a' * 40}]}}
    p = tmp_path / 'protocol.json'
    write_new(p, protocol)
    monkeypatch.setattr(runner, 'PROTOCOL', p)
    run = tmp_path / 'run'
    run.mkdir()
    manifest = {'provenance': {'protocol_sha256': sha256(p.read_bytes())}}
    write_new(run / 'manifest.json', manifest)
    prediction = {'instance_id': 'r-1', 'repo': 'o/r', 'base_commit': 'a' * 40, 'status': 'predicted',
                  'source': {'source_lengths': {'x.py': 1}}, 'outputs': [
                      {'method': 'bm25_windows', 'budget': 8000, 'status': 'ok',
                       'consumed': 100, 'blocks': [{'path': 'x.py', 'start_line': 1, 'end_line': 1}]}]}
    write_new(run / 'prediction-000.json', prediction)
    write_new(run / 'prediction-seal.json', {'files': {
        'prediction-000.json': sha256((run / 'prediction-000.json').read_bytes())},
        'manifest_sha256': sha256((run / 'manifest.json').read_bytes())})
    return argparse.Namespace(dataset=dataset, run=run, output=tmp_path / 'scores.json')


def test_sealed_end_to_end_scoring_and_no_overwrite(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    runner.score(args)
    data = json.loads(args.output.read_text())
    assert data['tasks'][0]['scores'][0]['line']['f1'] == 1
    assert 'patch' not in data['tasks'][0]
    with pytest.raises(FileExistsError):
        runner.score(args)


@pytest.mark.parametrize('filename', ['prediction-000.json', 'manifest.json'])
def test_changed_prediction_bundle_rejected(tmp_path, monkeypatch, filename):
    args = fixture(tmp_path, monkeypatch)
    path = args.run / filename
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError, match='changed'):
        runner.score(args)
    assert not args.output.exists()


def test_protocol_change_rejected(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    runner.PROTOCOL.write_bytes(runner.PROTOCOL.read_bytes() + b' ')
    with pytest.raises(ValueError, match='protocol changed'):
        runner.score(args)


def test_wrong_dataset_rejected(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    args.dataset.write_bytes(args.dataset.read_bytes() + b' ')
    with pytest.raises(ValueError, match='dataset checksum'):
        runner.score(args)


def test_prediction_failure_kept_in_score_denominator(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    path = args.run / 'prediction-000.json'
    path.write_text(json.dumps({'instance_id': 'r-1', 'repo': 'o/r', 'base_commit': 'a' * 40, 'status': 'failed',
                               'failure_category': 'timeout'}))
    seal = json.loads((args.run / 'prediction-seal.json').read_text())
    seal['files'][path.name] = sha256(path.read_bytes())
    (args.run / 'prediction-seal.json').write_text(json.dumps(seal))
    runner.score(args)
    record = json.loads(args.output.read_text())['tasks'][0]
    assert record['prediction_status'] == 'failed'
    assert record['denominator_retained'] is True
    assert len(record['scores']) == 1
    assert record['scores'][0]['line']['f1'] == 0
    assert record['scores'][0]['intent_to_evaluate_zero'] is True


def test_worker_cli_runs_real_core_with_synthetic_source_only(tmp_path):
    import io
    import os
    import subprocess
    import sys
    import tarfile
    archive = tmp_path / 'source.tar'
    source = b'def helper(x):\n    return x + 1\n\ndef answer(x):\n    return helper(x)\n'
    with tarfile.open(archive, 'w') as tf:
        item = tarfile.TarInfo('root/a.py')
        item.size = len(source)
        tf.addfile(item, io.BytesIO(source))
    payload = {'issue': 'answer helper', 'archive': str(archive),
               'archive_sha256': sha256(archive.read_bytes()), 'budgets': [8000, 16000, 32000],
               'resources': {'max_address_space_bytes': 4 * 1024**3, 'max_python_files': 5000,
                             'max_python_bytes': 32 * 1024**2, 'max_single_python_bytes': 1024**2}}
    completed = subprocess.run([sys.executable, '-m', 'benchmarks.external_context.runner', 'worker'],
        input=json.dumps(payload), capture_output=True, text=True, timeout=30,
        cwd=runner.ROOT, env={**os.environ, 'PYTHONPATH': str(runner.ROOT / 'src')})
    assert completed.returncode == 0, completed.stderr
    output = json.loads(completed.stdout)
    assert output['status'] == 'predicted'
    assert len(output['outputs']) == 18
    assert all(row['consumed'] <= row['budget'] for row in output['outputs'])
    assert any(row['delivered_lines'] > 0 for row in output['outputs'])
    serialized = json.dumps(output)
    assert 'return helper' not in serialized
    assert 'answer helper' not in serialized
