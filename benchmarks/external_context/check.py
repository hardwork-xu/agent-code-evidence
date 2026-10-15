"""Offline evidence consistency; not scholarly validation / 离线证据一致性，不是学术验收。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from .analyze import summarize
from .io import sha256
from .runner import PROTOCOL, ROOT
from .scoring import overlap

RUN = PROTOCOL.parent / 'results/pilot-20261014T081813Z'


def read(path):
    return json.loads(path.read_bytes())


def validate(run: Path = RUN) -> dict:
    protocol = read(PROTOCOL)
    manifest, seal, scores, summary, targets = [read(run / n) for n in (
        'manifest.json', 'prediction-seal.json', 'scores.json', 'summary.json', 'targets.json')]
    if manifest['provenance']['protocol_sha256'] != sha256(PROTOCOL.read_bytes()):
        raise ValueError('protocol hash changed')
    if manifest['provenance']['amendments_sha256'] != sha256(PROTOCOL.with_name('amendments.json').read_bytes()):
        raise ValueError('amendment hash changed')
    if manifest['source_manifest_sha256'] != sha256(PROTOCOL.with_name('sources.json').read_bytes()):
        raise ValueError('source manifest hash changed')
    if seal['manifest_sha256'] != sha256((run / 'manifest.json').read_bytes()):
        raise ValueError('manifest changed after prediction')
    if scores['prediction_seal_sha256'] != sha256((run / 'prediction-seal.json').read_bytes()):
        raise ValueError('prediction seal changed')
    if scores['dataset_sha256'] != targets['dataset_sha256'] or targets['dataset_sha256'] != protocol['dataset']['sha256']:
        raise ValueError('dataset identity mismatch')
    if scores['protocol_sha256'] != sha256(PROTOCOL.read_bytes()):
        raise ValueError('score protocol mismatch')
    expected = {t['instance_id']: t for t in protocol['selection']['tasks']}
    target_rows = {t['instance_id']: t for t in targets['tasks']}
    score_rows = {t['instance_id']: t for t in scores['tasks']}
    if (len(target_rows) != len(targets['tasks']) or len(score_rows) != len(scores['tasks'])
            or set(target_rows) != set(expected) or set(score_rows) != set(expected)
            or len(seal['files']) != len(expected)):
        raise ValueError('missing or duplicate frozen task')
    combinations = {(m, b) for m in protocol['methods'] for b in protocol['budgets']}
    seen = set()
    predictions = []
    for name, digest in sorted(seal['files'].items()):
        if Path(name).name != name or not name.startswith('prediction-') or not name.endswith('.json'):
            raise ValueError('unsafe prediction member')
        raw = (run / name).read_bytes()
        if sha256(raw) != digest:
            raise ValueError('prediction bytes changed')
        prediction = json.loads(raw)
        identity = prediction['instance_id']
        if identity in seen or identity not in expected:
            raise ValueError('invalid prediction identity')
        seen.add(identity)
        if any(prediction[k] != expected[identity][k] or target_rows[identity][k] != expected[identity][k]
               for k in ('repo', 'base_commit')):
            raise ValueError('frozen metadata changed')
        scored, target = score_rows[identity], target_rows[identity]
        if scored['patch_sha256'] != target['patch_sha256']:
            raise ValueError('patch identity mismatch')
        outputs = prediction.get('outputs', [])
        if prediction['status'] == 'predicted':
            if len(outputs) != len(combinations) or {(o['method'], o['budget']) for o in outputs} != combinations:
                raise ValueError('prediction method grid changed')
        elif outputs:
            raise ValueError('failed prediction supplied source')
        lookup = {(o['method'], o['budget']): o for o in outputs}
        if len(scored['scores']) != len(combinations) or {(s['method'], s['budget']) for s in scored['scores']} != combinations:
            raise ValueError('score method grid changed')
        py_lines = {(p, n) for p, n in target['removed_lines'] if p.endswith('.py')}
        py_files = {p for p in target['edited_base_files'] if p.endswith('.py')}
        for cell in scored['scores']:
            output = lookup.get((cell['method'], cell['budget']))
            blocks = output['blocks'] if output else []
            selected = {(b['path'], n) for b in blocks
                        for n in range(b['start_line'], b['end_line'] + 1)}
            if output:
                if (output['consumed'] > output['budget'] or output['consumed'] < 0
                        or len(selected) != output['delivered_lines']
                        or len(selected) != sum(b['end_line'] - b['start_line'] + 1 for b in blocks)):
                    raise ValueError('invalid delivered source/budget')
                lengths = prediction['source']['source_lengths']
                if any(type(n) is not int or not 1 <= n <= lengths.get(p, 0) for p, n in selected):
                    raise ValueError('source coordinates out of range')
            if cell['line'] != overlap(selected, py_lines) or cell['file'] != overlap({p for p, _ in selected}, py_files):
                raise ValueError('score differs from retained coordinates')
            if cell['consumed'] != (output['consumed'] if output else 0):
                raise ValueError('score byte count mismatch')
        predictions.append(prediction)
    if seen != set(expected):
        raise ValueError('missing predicted task')
    computed = summarize(scores, protocol)
    computed['scores_sha256'] = sha256((run / 'scores.json').read_bytes())
    computed['protocol_sha256'] = sha256(PROTOCOL.read_bytes())
    if computed != summary:
        raise ValueError('summary differs from all retained task scores')
    if summary['mature_research_established'] is not False:
        raise ValueError('unreviewed maturity promotion')
    return {'selected_tasks': len(predictions), 'score_cells': len(predictions) * len(combinations),
            'prediction_statuses': summary['prediction_statuses'],
            'advance_to_confirmatory': summary['advance_to_confirmatory'],
            'mature_research_established': False}


def check_measured_source():
    """Pin implementation bytes separately from documentation / 单独固定实现字节。"""
    manifest = read(RUN / 'manifest.json')
    commit = manifest['provenance']['git_commit']
    for name in ('protocol.json', 'amendments.json', 'runner.py', 'retrieval.py', 'io.py', 'scoring.py', 'analyze.py'):
        path = 'benchmarks/external_context/' + name
        expected = subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT)
        if expected != (ROOT / path).read_bytes():
            raise ValueError('measured implementation bytes changed: ' + name)


def main():
    parser = argparse.ArgumentParser(description='Check recorded pilot / 核对记录试验')
    parser.add_argument('--check-source', action='store_true', help='Require measured Git object / 核验实测Git对象')
    args = parser.parse_args()
    if args.check_source:
        check_measured_source()
    print(json.dumps(validate(), sort_keys=True))


if __name__ == '__main__':
    main()
