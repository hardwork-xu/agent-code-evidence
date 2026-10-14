"""Run exact pinned upstream assertions. / 执行固定上游断言。

Run outside performance experiments. Output is exclusive and preserves failures.
请勿与性能实验并行运行；输出目录独占，保留全部失败。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
DATA = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from scripts.prepare_global_execution_sources import (  # noqa: E402
    outside_git, source_name, validate_files, validate_inputs,
)


def configs(inputs: dict, source_root: Path, output: Path, dependencies: dict) -> list[dict]:
    """Create both fixed/parent roles with identical tests. / 为两个版本保留相同测试。"""
    validate_inputs(inputs)
    sources = {(s['repository'], s['sha']): s for s in inputs['sources']}
    dependency_files = {}
    versions = {}
    for entry in dependencies['packages']:
        if set(dependency_files).intersection(entry['regular_files']):
            raise ValueError('dependency file collision')
        dependency_files.update(entry['regular_files'])
        versions[entry['name']] = entry['version']
    dependency_root = source_root / 'dependencies/python'
    validate_files(dependency_root, dependency_files)
    for source in inputs['sources']:
        validate_files(source_root / source['directory'], source['regular_files'])
    jobs = []
    for case in inputs['cases']:
        for role in ['fixed', 'parent']:
            source = sources[(case['repository'], case[role + '_sha'])]
            label = sources[(case['repository'], case['fixed_sha'])]
            name = source_name(case['repository'], source['sha']) + '-' + role
            execution = output / 'work' / name
            shutil.copytree(source_root / label['directory'], execution)
            package = execution / case['package_path']
            shutil.rmtree(package)
            shutil.copytree(source_root / source['directory'] / case['package_path'], package)
            prefix = case['package_path'] + '/'
            production = {k: v for k, v in source['regular_files'].items()
                          if k.startswith(prefix)}
            hybrid = {k: v for k, v in label['regular_files'].items() if not k.startswith(prefix)}
            hybrid.update(production)
            jobs.append({'repository': case['repository'], 'source_sha': source['sha'],
                         'role': role, 'label_source_sha': case['fixed_sha'],
                         'package': case['package'], 'package_path': case['package_path'],
                         'tests': case['tests'], 'expected_cases': case['expected_parameterized_cases'],
                         'execution_root': str(execution), 'hybrid_files': hybrid,
                         'production_files': production, 'output_path': str(output / (name + '.json')),
                         'dependency_root': str(dependency_root), 'dependency_files': dependency_files,
                         'framework_versions': versions})
    panel = inputs['global_panel']
    source = sources[(panel['repository'], panel['sha'])]
    execution = output / 'work' / (source['directory'] + '-global-whole-panel')
    shutil.copytree(source_root / source['directory'], execution)
    prefix = panel['package_path'] + '/'
    jobs.append({'repository': panel['repository'], 'source_sha': panel['sha'],
                 'role': 'current_head_global_writer_preflight', 'label_source_sha': panel['sha'],
                 'package': panel['package'], 'package_path': panel['package_path'],
                 'tests': panel['tests'], 'expected_cases': panel['expected_test_cases'],
                 'global_watch': panel['global_watch'], 'execution_root': str(execution),
                 'hybrid_files': source['regular_files'],
                 'production_files': {k: v for k, v in source['regular_files'].items()
                                      if k.startswith(prefix)},
                 'output_path': str(output / 'global-whole-panel.json'),
                 'dependency_root': str(dependency_root), 'dependency_files': dependency_files,
                 'framework_versions': versions})
    return jobs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True,
                        help='verified external inputs / 仓库外已验证输入')
    parser.add_argument('--output', type=Path, required=True,
                        help='new external result directory / 仓库外新结果目录')
    args = parser.parse_args()
    source_root = outside_git(args.source_root)
    output = outside_git(args.output)
    output.mkdir(parents=True, exist_ok=False)
    private_logs = output / '.private-logs'
    private_logs.mkdir(mode=0o700)
    inputs = json.loads((DATA / 'inputs.json').read_text())
    dependencies = json.loads((DATA / 'dependencies.json').read_text())
    jobs = configs(inputs, source_root, output, dependencies)
    records = []
    failed = False
    for index, job in enumerate(jobs):
        config_path = private_logs / f'worker-{index}.json'
        config_path.write_text(json.dumps(job, indent=2) + '\n')
        home = private_logs / f'home-{index}'
        home.mkdir()
        environment = {'PATH': str(Path(sys.executable).parent) + os.pathsep + '/usr/bin:/bin',
                       'HOME': str(home), 'TMPDIR': str(home),
                       'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'PYTHONDONTWRITEBYTECODE': '1',
                       'LC_ALL': 'C.UTF-8'}
        started = time.time()
        command = [sys.executable, '-I', '-B', str(DATA / 'worker.py'), str(config_path)]
        record = {'repository': job['repository'], 'role': job['role'],
                  'source_sha': job['source_sha'], 'started_unix': started,
                  'expected_cases': job['expected_cases'], 'status': 'started'}
        try:
            process = subprocess.run(command, cwd=job['execution_root'], env=environment,
                                     capture_output=True, text=True, timeout=120, check=False)
            (private_logs / f'worker-{index}.log').write_text(process.stdout + '\n' + process.stderr)
            record['process_exit_code'] = process.returncode
            if process.returncode != 0:
                record['status'] = 'worker_failed'
                failed = True
            else:
                result = json.loads(Path(job['output_path']).read_text())
                collected = len(result['collected_cases'])
                record.update(status='executed', collected_cases=collected,
                              upstream_pytest_exit_code=result['exit_code'])
                if collected != job['expected_cases'] or result['exit_code'] not in {0, 1}:
                    record['status'] = 'collection_or_runtime_failure'
                    failed = True
                if job['role'] != 'parent' and result['exit_code'] != 0:
                    failed = True
        except Exception as error:
            record.update(status='orchestration_failed', error_type=type(error).__name__)
            (private_logs / f'worker-{index}.log').write_text(str(error))
            failed = True
        records.append(record)
        summary = {'schema_version': 1, 'classification': 'development_execution_reproduction',
                   'input_sha256': hashlib.sha256((DATA / 'inputs.json').read_bytes()).hexdigest(),
                   'worker_sha256': hashlib.sha256((DATA / 'worker.py').read_bytes()).hexdigest(),
                   'runs': records, 'raw_logs_private_outside_git': True}
        (output / 'runs.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(record))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
