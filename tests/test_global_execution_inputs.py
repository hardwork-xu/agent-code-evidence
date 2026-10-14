"""Offline independent checks of upstream execution records and runner boundaries."""
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import subprocess
import tarfile
from types import ModuleType, SimpleNamespace

import pytest

from scripts.prepare_global_execution_sources import (
    acquire, extract_archive, outside_git, safe_relative, validate_files, validate_inputs,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'benchmarks/global_bindings/upstream_execution'


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECK = load_module('global_upstream_record_checker', DATA / 'check.py')
WORKER = load_module('global_upstream_worker_contract', DATA / 'worker.py')


def retained():
    return (json.loads((DATA / 'inputs.json').read_text()),
            json.loads((DATA / 'results/upstream-preflight.json').read_text()),
            json.loads((DATA / 'results/global-whole-panel.json').read_text()))


def test_retained_independent_upstream_assertion_denominators():
    inputs, primary, panel = retained()
    result = CHECK.verify_all(inputs, primary, panel)
    assert result == {'status': 'verified', 'upstream_change_units': 4,
                      'fixed_cases_passed': 43, 'parent_cases_failed': 28,
                      'global_whole_panel_tests': 23, 'global_observations': 200,
                      'scientific_maturity_established': False}
    assert len(inputs['heads']) == 8
    assert sum(bool(head['explicit_global_functions']) for head in inputs['heads']) == 1
    failures = json.loads((DATA / 'results/preflight-failures.json').read_text())
    assert {x['status'] for x in failures['failed_attempts']} >= {'HTTP404', 'ambiguous_selector'}
    assert 'only assert inside except' in inputs['global_panel']['known_assertion_limit']


@pytest.mark.parametrize('mutation', ['omit_failure', 'invent_fixed_passes', 'wrong_role',
                                    'different_import', 'erase_global_transition', 'duplicate_run'])
def test_record_checker_rejects_favorable_or_identity_tampering(mutation):
    inputs, primary, panel = retained()
    primary, panel = deepcopy(primary), deepcopy(panel)
    if mutation == 'omit_failure':
        row = next(r for r in primary['runs'] if r['role'] == 'parent')
        row['reports'] = [r for r in row['reports'] if r['outcome'] != 'failed']
    elif mutation == 'invent_fixed_passes':
        primary['fixed_passed'] = 44
    elif mutation == 'wrong_role':
        row = primary['runs'][0]
        row['source_sha'] = inputs['cases'][0]['parent_sha']
    elif mutation == 'different_import':
        row = primary['runs'][0]
        next(iter(row['loaded_source_modules'].values()))['sha256'] = '0' * 64
    elif mutation == 'erase_global_transition':
        panel['global_observations'][0]['state']['_trim_arity_call_line']['type'] = 'FrameSummary'
    else:
        primary['runs'].append(deepcopy(primary['runs'][0]))
    with pytest.raises(ValueError):
        CHECK.verify_all(inputs, primary, panel)


@pytest.mark.parametrize('value', ['../x', '/x', 'a/../b', 'a//b', 'a\\b', 'C:/x', 'a\nb'])
def test_archive_and_metadata_paths_reject_escape(value):
    with pytest.raises(ValueError):
        safe_relative(value)


def write_tar(path, entries):
    with tarfile.open(path, 'w:gz') as stream:
        for name, content, kind in entries:
            info = tarfile.TarInfo(name)
            if kind == 'link':
                info.type = tarfile.SYMTYPE
                info.linkname = '../outside'
                stream.addfile(info)
            else:
                info.size = len(content)
                stream.addfile(info, io.BytesIO(content))


def test_extraction_never_follows_links_and_binds_regular_bytes(tmp_path):
    archive = tmp_path / 'source.tar.gz'
    data = b'def square(n):\n    return n*n\n'
    expected = {'pkg/mod.py': {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}}
    write_tar(archive, [('fixed/pkg/mod.py', data, 'file'), ('fixed/link', b'', 'link')])
    destination = tmp_path / 'source'
    destination.mkdir()
    assert extract_archive(archive, destination, expected) == ['link']
    assert not (destination / 'link').exists()
    validate_files(destination, expected)
    (destination / 'injected.py').write_text('raise RuntimeError()\n')
    with pytest.raises(ValueError, match='unexpected executable'):
        validate_files(destination, expected)


@pytest.mark.parametrize('attack', ['../escaped.py', 'fixed/../escaped.py', '/escaped.py'])
def test_tar_traversal_cannot_write_external_files(tmp_path, attack):
    archive = tmp_path / 'source.tar.gz'
    write_tar(archive, [(attack, b'x', 'file')])
    target = tmp_path / 'source'
    target.mkdir()
    with pytest.raises(ValueError):
        extract_archive(archive, target, {})
    assert not (tmp_path / 'escaped.py').exists()


def test_offline_cache_refuses_digest_mismatch_without_network(tmp_path, monkeypatch):
    cache = tmp_path / 'cache'
    cache.mkdir()
    (cache / 'asset').write_bytes(b'wrong')
    monkeypatch.setattr('scripts.prepare_global_execution_sources.subprocess.run',
                        lambda *a, **k: pytest.fail('unexpected network'))
    with pytest.raises(ValueError, match='cached archive hash mismatch'):
        acquire('https://files.pythonhosted.org/packages/asset', '0' * 64,
                tmp_path / 'out/asset', cache, True)


def test_private_preparation_rejects_git_ancestor_and_role_mismatch(tmp_path):
    (tmp_path / '.git').mkdir()
    with pytest.raises(ValueError, match='outside Git'):
        outside_git(tmp_path / 'cache')
    inputs, _, _ = retained()
    inputs['cases'][0]['parent_sha'] = '0' * 40
    with pytest.raises(ValueError, match='missing source role'):
        validate_inputs(inputs)


def test_actual_import_identity_cannot_be_substituted_with_same_named_module(tmp_path):
    package = tmp_path / 'pkg'
    package.mkdir()
    source = package / '__init__.py'
    source.write_text('def multiply(n):\n    return n*2\n')
    expected = {'pkg/__init__.py': {'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}}
    module = ModuleType('pkg')
    module.__file__ = str(source)
    module.__spec__ = SimpleNamespace(origin=str(source))
    assert WORKER.validate_imported_identity(tmp_path, 'pkg', {'pkg': module}, expected)
    unrelated = tmp_path / 'unrelated.py'
    unrelated.write_bytes(source.read_bytes())
    module.__file__ = str(unrelated)
    module.__spec__ = SimpleNamespace(origin=str(unrelated))
    with pytest.raises(ValueError, match='escaped selected role'):
        WORKER.validate_imported_identity(tmp_path, 'pkg', {'pkg': module}, expected)


def test_worker_executes_actual_offline_assertions_and_keeps_failure(tmp_path, monkeypatch):
    # This is a runner contract fixture, never one of the upstream research tasks.
    root = tmp_path / 'source'
    package = root / 'source_role_fixture'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('def double(n):\n    return n*2\n')
    tests = root / 'tests'
    tests.mkdir()
    (tests / 'test_contract.py').write_text(
        'from source_role_fixture import double\n'
        'def test_valid_assertion():\n    assert double(3) == 6\n'
        'def test_negative_assertion():\n    assert double(3) == 7\n')
    files = {p.relative_to(root).as_posix():
             {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size}
             for p in root.rglob('*.py')}
    dependency_root = tmp_path / 'dependencies'
    dependency_root.mkdir()
    config = {'execution_root': str(root), 'package': 'source_role_fixture',
              'package_path': 'source_role_fixture', 'dependency_root': str(dependency_root),
              'hybrid_files': files, 'dependency_files': {}, 'framework_versions': {},
              'production_files': {k: v for k, v in files.items() if k.startswith('source_role_fixture/')},
              'repository': 'offline/contract', 'source_sha': 'a' * 40,
              'label_source_sha': 'a' * 40, 'role': 'fixed',
              'tests': ['tests/test_contract.py::test_valid_assertion',
                        'tests/test_contract.py::test_negative_assertion']}
    monkeypatch.setenv('PYTEST_DISABLE_PLUGIN_AUTOLOAD', '1')
    monkeypatch.setattr(sys, 'path', sys.path[:])
    monkeypatch.delitem(sys.modules, 'source_role_fixture', raising=False)
    try:
        record = WORKER.execute(config, enforce_framework=False)
        calls = [r for r in record['reports'] if r['when'] == 'call']
        assert [r['outcome'] for r in calls] == ['passed', 'failed']
        assert record['exit_code'] == 1
        assert record['production_hashes_verified']
        assert record['execution_trace']['tests/test_contract.py::test_valid_assertion'][
            'source_role_fixture/__init__.py'] == [2]
        assert all('/Users/' not in r.get('failure_detail', '') for r in calls)
    finally:
        sys.modules.pop('source_role_fixture', None)


def test_public_reproduction_entrypoints_parse_without_running_inputs():
    for entry in [ROOT / 'scripts/prepare_global_execution_sources.py', DATA / 'run.py']:
        result = subprocess.run([sys.executable, str(entry), '--help'], capture_output=True,
                                text=True, timeout=20, check=False)
        assert result.returncode == 0, result.stderr
        assert '--source-root' in result.stdout


def test_valid_source_hashes_do_not_certify_unpinned_bytecode(tmp_path):
    import py_compile
    source = tmp_path / 'source.py'
    source.write_text('def value(n):\n    return n*2\n')
    py_compile.compile(str(source), doraise=True)
    with pytest.raises(ValueError, match='cached bytecode'):
        WORKER.reject_cached_bytecode(tmp_path)


def test_portable_real_replay_metadata_binds_exact_roles_code_and_failures():
    inputs, _, _ = retained()
    result = CHECK.verify_portable_replay(inputs, DATA / 'results/portable-replay-20261014')
    assert result['real_upstream_replay_processes'] == 9
    assert result['fixed_cases_passed'] == 43
    assert result['parent_cases_failed'] == 28
    assert result['metadata_only_validation']
    assert result['helper_fingerprints_recorded_after_execution']
    assert not result['new_independent_holdout']


@pytest.mark.parametrize('mutation', ['missing_index', 'missing_original_index', 'missing_result',
                                    'duplicate_card', 'false_failure_count', 'wrong_script_sha',
                                    'wrong_helper_sha', 'nonfinite_rss', 'nonfinite_elapsed',
                                    'nonfinite_phase', 'nonfinite_start', 'changed_loaded_hash',
                                    'missing_controller_run', 'new_measurement_amendment'])
def test_portable_replay_rejects_tampering_even_if_changed_raw_hash_is_recomputed(tmp_path, mutation):
    import shutil
    directory = tmp_path / 'replay'
    shutil.copytree(DATA / 'results/portable-replay-20261014', directory)
    index_path = directory / 'index.json'
    index = json.loads(index_path.read_text())
    result_name = next(name for name in index['files'] if name.endswith('-parent.json'))

    def update_raw(name, transform):
        path = directory / name
        value = json.loads(path.read_text())
        transform(value)
        path.write_text(json.dumps(value, indent=2) + '\n')
        index['files'][name] = hashlib.sha256(path.read_bytes()).hexdigest()
        # Keep the original-index audit consistent for semantic/number tampering tests:
        # this tests outcome/measurement validation rather than only immutable-hash checks.
        original_path = directory / 'index-original-v1.json'
        original = json.loads(original_path.read_text())
        original['files'][name] = index['files'][name]
        original_path.write_text(json.dumps(original, indent=2) + '\n')
        index['provenance_amendment']['original_index_sha256'] = hashlib.sha256(
            original_path.read_bytes()).hexdigest()

    if mutation == 'missing_index':
        index_path.unlink()
    elif mutation == 'missing_original_index':
        (directory / 'index-original-v1.json').unlink()
    elif mutation == 'missing_result':
        (directory / result_name).unlink()
    elif mutation == 'duplicate_card':
        index['records'].append(deepcopy(index['records'][0]))
    elif mutation == 'false_failure_count':
        next(card for card in index['records'] if card['role'] == 'parent')['counts']['failed'] = 0
    elif mutation == 'wrong_script_sha':
        index['worker_sha256'] = '0' * 64
    elif mutation == 'wrong_helper_sha':
        index['preparer_sha256'] = '0' * 64
    elif mutation in {'nonfinite_rss', 'nonfinite_elapsed', 'nonfinite_phase'}:
        def transform(value):
            if mutation == 'nonfinite_rss':
                value['peak_rss_mib'] = float('inf')
            elif mutation == 'nonfinite_elapsed':
                value['elapsed_seconds'] = float('nan')
            else:
                value['reports'][0]['duration'] = float('nan')
        update_raw(result_name, transform)
    elif mutation == 'nonfinite_start':
        update_raw('runs.json', lambda value: value['runs'][0].update(started_unix=float('nan')))
    elif mutation == 'changed_loaded_hash':
        update_raw(result_name, lambda value: next(iter(value['loaded_source_modules'].values())).update(
            sha256='0' * 64))
    elif mutation == 'missing_controller_run':
        update_raw('runs.json', lambda value: value['runs'].pop())
    elif mutation == 'new_measurement_amendment':
        index['provenance_amendment']['new_measurement'] = True
    if mutation != 'missing_index':
        index_path.write_text(json.dumps(index, indent=2) + '\n')
    inputs, _, _ = retained()
    with pytest.raises(ValueError):
        CHECK.verify_portable_replay(inputs, directory)
