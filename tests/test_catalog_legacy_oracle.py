"""Frozen resolver worker boundaries / 固定解析器子进程边界。"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.catalog_reuse import legacy_oracle as legacy


def test_worker_runs_only_resolver_and_matches_current(tmp_path):
    from benchmarks.catalog_reuse.suite import Repository, fresh_graphs, digest
    texts = {'pkg/use.py': 'from pkg.worker import compute\ndef run():\n    return compute()\n',
             'pkg/worker.py': 'def compute():\n    return 1\n'}
    identity = 'pkg/use.py:run'
    repository = Repository('fixture', 'pin', {}, (), (),
                            ({'path': 'pkg/use.py', 'symbol': 'run',
                              'selection_sha256': digest(identity.encode())},))
    anchors = repository.anchors(texts)
    policy = {'max_depth': 4, 'max_nodes': 256}
    checkout = Path(legacy.ROOT)
    expected = [digest(graph) for graph in fresh_graphs(texts, 'fixture', anchors, policy)]
    assert legacy.reference_graph_digests(checkout, texts, 'fixture', anchors, policy) == expected


def test_worker_failure_does_not_emit_raw_stderr(tmp_path, monkeypatch):
    monkeypatch.setattr(legacy.subprocess, 'run', lambda *a, **k:
                        SimpleNamespace(returncode=1, stdout=b'', stderr=b'PRIVATE VALUE'))
    with pytest.raises(RuntimeError, match='reference reconstruction failed') as error:
        legacy.reference_graph_digests(tmp_path, {}, 's', [], {})
    assert 'PRIVATE VALUE' not in str(error.value)


def test_reference_output_shape_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(legacy.subprocess, 'run', lambda *a, **k:
                        SimpleNamespace(returncode=0, stdout=json.dumps(['wrong']).encode()))
    with pytest.raises(ValueError, match='shape'):
        legacy.reference_graph_digests(tmp_path, {}, 's', [], {})


def test_existing_output_is_never_overwritten(tmp_path):
    result = tmp_path / 'existing.json'
    result.write_text('historical')
    with pytest.raises(FileExistsError):
        legacy.compare(tmp_path/'inputs', tmp_path/'protocol', tmp_path, result)
    assert result.read_text() == 'historical'


def test_failure_retained_before_any_graph(tmp_path):
    protocol = tmp_path / 'protocol.json'
    protocol.write_text('{}')
    output = tmp_path / 'result.json'
    with pytest.raises(ValueError):
        legacy.compare(tmp_path/'inputs', protocol, tmp_path, output)
    data = json.loads(output.read_text())
    assert data['status'] == 'failed' and data['graph_count'] == 0
    assert data['error_type'] == 'ValueError'
    assert data['mismatch_graph_count'] == 0  # incomplete is not a passed gate


def test_reference_git_failure_does_not_print_local_path(tmp_path, capfd):
    import subprocess
    with pytest.raises(subprocess.CalledProcessError):
        legacy.reference_identity(tmp_path)
    captured = capfd.readouterr()
    assert not captured.out and not captured.err
