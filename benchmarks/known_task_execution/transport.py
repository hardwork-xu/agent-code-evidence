"""Proposed public transport format: transparent JSON metadata and gzip parts.

No SUT execution. Always preserves the source JSON and requires external hashes.
The accompanying public checker recomputes finite qualification from decoded data.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re

from .public_check import canonical, check, load_contract, require, scan_privacy

MAX_PART = 64 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def record_part(root, name, value):
    raw = canonical(value)
    require(len(raw) <= MAX_PART, 'uncompressed part exceeds cap')
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    path = root / name
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(compressed)
    return {'name': name, 'uncompressed_sha256': sha(raw),
            'uncompressed_bytes': len(raw), 'gzip_sha256': sha(compressed),
            'gzip_bytes': len(compressed)}


def pack(source, trusted_sha, destination):
    raw = Path(source).read_bytes()
    require(sha(raw) == trusted_sha, 'source evidence differs from trusted SHA')
    evidence = json.loads(raw)
    scan_privacy(evidence)
    root = Path(destination)
    require(not root.exists(), 'do not overwrite retained transport candidates')
    root.mkdir(mode=0o700)
    metadata = {k: v for k, v in evidence.items() if k != 'conditions'}
    index = {'schema_version': 1,
             'classification': 'private_review_candidate_gzip_transport_not_research_claim',
             'source_evidence_sha256': trusted_sha, 'source_evidence_bytes': len(raw),
             'canonical_reassembly': 'sort_keys;ensure_ascii=false;compact;UTF8;one_LF',
             'metadata': record_part(root, 'metadata.json.gz', metadata),
             'conditions': [], 'limits': [
                 'Private full-source/venv inventories and raw logs not distributed.',
                 'Public checker verifies exported arithmetic, not original execution authenticity.']}
    for condition in evidence['conditions']:
        key = condition['condition_key']
        require(re.fullmatch('[0-9a-f]{64}', key), 'invalid condition key')
        part = record_part(root, 'conditions/' + key + '.json.gz', condition)
        part.update({k: condition[k] for k in [
            'condition_key', 'instance_id', 'run_id', 'qualified']})
        index['conditions'].append(part)
    scan_privacy(index)
    (root / 'INDEX.json').write_bytes(canonical(index) + b'\n')
    return {'index_sha256': sha((root / 'INDEX.json').read_bytes()),
            'gzip_bytes': sum(p['gzip_bytes'] for p in [index['metadata'], *index['conditions']]),
            'uncompressed_source_bytes': len(raw), 'condition_parts': len(index['conditions'])}


def decode(root, part):
    name = part['name']
    path = PurePosixPath(name)
    require(not path.is_absolute() and '..' not in path.parts and '\\' not in name,
            'unsafe gzip part path')
    p = root / name
    require(not p.is_symlink() and p.is_file(), 'part must be ordinary file')
    require(p.stat().st_size <= MAX_PART, 'compressed part exceeds read cap')
    data = p.read_bytes()
    require(len(data) == part['gzip_bytes'] and sha(data) == part['gzip_sha256'],
            'gzip bytes/hash mismatch')
    require(0 <= part['uncompressed_bytes'] <= MAX_PART, 'declared part expansion cap')
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as f:
        raw = f.read(part['uncompressed_bytes'] + 1)
    require(len(raw) == part['uncompressed_bytes']
            and sha(raw) == part['uncompressed_sha256'], 'decoded bytes/hash mismatch')
    value = json.loads(raw)
    require(canonical(value) == raw, 'noncanonical JSON part')
    scan_privacy(value)
    return value


def verify(root, trusted_index_sha, contract, output=None):
    root = Path(root)
    index_bytes = (root / 'INDEX.json').read_bytes()
    require(sha(index_bytes) == trusted_index_sha, 'index differs from trusted external SHA')
    index = json.loads(index_bytes)
    scan_privacy(index)
    require(set(index) == {'schema_version', 'classification', 'source_evidence_sha256',
        'source_evidence_bytes', 'canonical_reassembly', 'metadata', 'conditions', 'limits'},
        'transport index schema differs')
    require(index['schema_version'] == 1 and len(index['conditions']) <= 200,
            'transport schema or condition count cap')
    parts = [index['metadata'], *index['conditions']]
    expected = {'name', 'uncompressed_sha256', 'uncompressed_bytes',
                'gzip_sha256', 'gzip_bytes'}
    require(set(index['metadata']) == expected and all(set(part) == expected | {
        'condition_key', 'instance_id', 'run_id', 'qualified'}
        for part in index['conditions']), 'part index schema differs')
    require(sum(p['uncompressed_bytes'] for p in parts) <= MAX_TOTAL,
            'total expansion exceeds cap')
    names = [p['name'] for p in parts]
    require(len(names) == len(set(names)), 'duplicate transport part')
    require(all(not p.is_symlink() for p in root.rglob('*')), 'symlink in transport candidate')
    require({str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
            == {'INDEX.json', *names}, 'unexpected or missing transport file')
    metadata = decode(root, index['metadata'])
    require('conditions' not in metadata, 'metadata must not hide condition records')
    conditions = []
    for part in index['conditions']:
        c = decode(root, part)
        require(all(c[k] == part[k] for k in [
            'condition_key', 'instance_id', 'run_id', 'qualified']), 'part identity mismatch')
        conditions.append(c)
    evidence = dict(metadata, conditions=conditions)
    raw = canonical(evidence) + b'\n'
    require(len(raw) == index['source_evidence_bytes']
            and sha(raw) == index['source_evidence_sha256'], 'source reassembly mismatch')
    result = check(evidence, contract)
    if output is not None:
        output = Path(output)
        require(not output.exists(), 'do not overwrite reassembled evidence')
        output.write_bytes(raw)
    return dict(result, transport_status='decoded_hashes_privacy_and_contract_checked',
                reconstructed_evidence_sha256=sha(raw), index_sha256=trusted_index_sha)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('pack')
    p.add_argument('--evidence', required=True)
    p.add_argument('--expected-evidence-sha256', required=True)
    p.add_argument('--destination', required=True)
    v = sub.add_parser('verify')
    v.add_argument('--bundle', required=True)
    v.add_argument('--expected-index-sha256', required=True)
    v.add_argument('--contract', required=True)
    v.add_argument('--output')
    a = parser.parse_args()
    if a.action == 'pack':
        result = pack(a.evidence, a.expected_evidence_sha256, a.destination)
    else:
        result = verify(a.bundle, a.expected_index_sha256, load_contract(a.contract), a.output)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
