#!/usr/bin/env python3
"""Exploratory unknown-preserving replay / 结果后的探索性消融，保留 unknown。"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_selective_reuse as base  # noqa: E402

METHODS = ['warm_ast_rebuild', 'whole_corpus_guard', 'read_set_any_status']
DATA = ROOT / 'benchmarks/selective_reuse'


def analyze(raw):
    """Use the same paired-grid checker; internal alias only, raw labels retained."""
    equivalent_schema = deepcopy(raw)
    for row in equivalent_schema['rows']:
        if row['method'] == 'read_set_any_status':
            row['method'] = 'read_set_certificate'
    summary = base.summarize(equivalent_schema)
    # The original threshold was not preregistered for this post-result method.
    summary.pop('utility_target_met')
    summary.pop('natural_repositories_meeting_target')
    for group_set in ['groups', 'source_changing_groups']:
        for methods in summary[group_set].values():
            methods['read_set_any_status'] = methods.pop('read_set_certificate')
    summary['interpretation'] = 'Exploratory same-data ablation; not a confirmatory target or holdout result.'
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', type=Path, default=ROOT / 'work/selective-reuse/archives')
    parser.add_argument('--output', type=Path, required=True, help='new raw file / 新原始文件，不覆盖')
    args = parser.parse_args()
    protocol_path = DATA / 'ablation-protocol.json'
    protocol = json.loads(protocol_path.read_text())
    manifest = json.loads((DATA / 'natural-manifest.json').read_text())
    base.validate_manifest(manifest, json.loads((DATA / 'protocol.json').read_text()))
    if base.digest((DATA / 'natural-manifest.json').read_bytes()) != protocol['natural_manifest_sha256']:
        raise ValueError('ablation input changed')
    raw = {'schema_version': 1, 'study': 'exploratory-completeness-gate-ablation',
           'run_id': datetime.now(timezone.utc).strftime('ablation-%Y%m%dT%H%M%SZ'),
           'started_at_utc': datetime.now(timezone.utc).isoformat(), 'status': 'running',
           'command': 'python scripts/run_selective_ablation.py --output NEW_RUN.json',
           'protocol_sha256': base.digest(protocol_path.read_bytes()),
           'natural_manifest_sha256': protocol['natural_manifest_sha256'],
           'environment': base.environment(), 'rows': [],
           'ablation_runner_sha256': base.digest(Path(__file__).read_bytes()),
           'repetitions': protocol['repetitions'],
           'expected_groups': ['natural:' + r['repository'] for r in manifest['repositories']]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as handle:
        handle.write(json.dumps(raw, indent=2) + '\n')
    def checkpoint():
        base.write(args.output, raw)
    def progress(location):
        raw['progress'] = location
        checkpoint()
    try:
        for offset, repo in enumerate(manifest['repositories']):
            loaders = [base.source_loader(args.cache_dir, repo, v) for v in repo['versions']]
            first = loaders[0]()
            anchors = base.anchors_for(first)
            if [{k: v for k, v in a.items() if k != 'text'} for a in anchors] != repo['anchors']:
                raise ValueError('frozen anchor selection drift')
            base.replay_group('natural:' + repo['repository'], loaders,
                              [v['commit'] for v in repo['versions']], anchors,
                              protocol['repetitions'], offset, rows=raw['rows'],
                              checkpoint=checkpoint, progress=progress, methods=METHODS)
        raw['status'] = 'passed'
        raw['summary'] = analyze(raw)
        raw.pop('progress', None)
    except (Exception, KeyboardInterrupt) as error:
        raw['status'] = 'interrupted' if isinstance(error, KeyboardInterrupt) else 'failed'
        raw['error_type'] = type(error).__name__
        raise
    finally:
        raw['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        checkpoint()


if __name__ == '__main__':
    main()
