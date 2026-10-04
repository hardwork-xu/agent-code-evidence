#!/usr/bin/env python3
"""Offline checks of published research records; no source download or execution.

仅复核已保存的协议、记录和统计；不联网、不执行上游代码、不重新测量。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]

from scripts.check_attribution import safe_path  # noqa: E402
from scripts import prepare_incremental_holdout as sources  # noqa: E402
from scripts import run_incremental_holdout as holdout  # noqa: E402
from scripts import run_task_evidence as tasks  # noqa: E402


def check_holdout(root: Path) -> dict:
    directory = safe_path(root, 'benchmarks/incremental_holdout')
    protocol_bytes = (directory / 'protocol.json').read_bytes()
    protocol = json.loads(protocol_bytes)
    manifest = json.loads((directory / 'manifest.json').read_text())
    sources.validate_manifest(manifest, protocol, protocol_bytes=protocol_bytes, root=root)
    results = directory / 'results'
    if not results.exists():
        return {'status': 'prepared_without_results', 'passed': 0, 'retained_failures': 0}
    checked, failed, complete = 0, 0, 0
    previous = holdout.DATA
    holdout.DATA = directory
    try:
        for path in sorted(results.glob('*.json')):
            safe_path(root, path.relative_to(root).as_posix())
            result = json.loads(path.read_text())
            if result.get('status') == 'passed':
                summary = holdout.summarize(result, protocol, manifest)
                if result.get('summary') != summary:
                    raise ValueError('saved holdout summary differs from validated raw rows')
                checked += 1
                complete += result['suite'] == 'all'
            elif result.get('status') in {'failed', 'interrupted'}:
                if not result.get('error_type') or 'summary' in result:
                    raise ValueError('failed holdout attempt has missing failure identity or success summary')
                failed += 1
            else:
                raise ValueError('uncompleted or unclassified published holdout result')
    finally:
        holdout.DATA = previous
    if not complete:
        raise ValueError('published holdout results lack a complete passed all-suite run')
    return {'status': 'passed', 'passed': checked, 'complete_all_suite_runs': complete,
            'retained_failures': failed, 'scope': 'offline record integrity, not rerun measurements'}


def check_tasks(root: Path) -> dict:
    directory = safe_path(root, 'benchmarks/task_evidence')
    primary = directory / 'results/primary-20261004'
    initial = directory / 'results/initial'
    results = directory / 'results'
    if results.exists() and any(not path.is_dir() or path.name not in {'initial', 'primary-20261004'}
                                for path in results.iterdir()):
        raise ValueError('unreviewed task result directory or artifact')
    for path in results.rglob('*'):
        if path.is_file() or path.is_symlink():
            safe_path(root, path.relative_to(root).as_posix())
    if initial.exists():
        disclosure = (initial / 'STATUS.md').read_text()
        if not disclosure.startswith('# Invalid execution-semantics pilot; not research evidence'):
            raise ValueError('invalid pilot disclosure was removed or reclassified')
    if not primary.exists():
        return {'status': 'prepared_without_primary', 'invalid_pilot_retained': initial.exists()}
    previous = tasks.BENCH
    tasks.BENCH = directory
    try:
        report = tasks.validate_result_bundle(primary)
    finally:
        tasks.BENCH = previous
    return {'status': 'passed', 'invalid_pilot_retained': initial.exists(), **report,
            'scope': 'offline report integrity; upstream bytes and runtime behavior require the archived run'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-results', action='store_true',
                        help='require both completed primary studies for publication')
    args = parser.parse_args()
    try:
        report = {'holdout': check_holdout(ROOT), 'task_evidence': check_tasks(ROOT)}
        if args.require_results and any(value['status'] != 'passed' for value in report.values()):
            raise ValueError('primary research results are required for publication')
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(json.dumps({'status': 'failed', 'error': str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps({'status': 'passed', **report}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
