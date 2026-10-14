#!/usr/bin/env python3
"""Acquire pinned catalog inputs outside Git, verify hashes, and filter source paths.

Upstream code has independent licenses. Only metadata ships in this repository;
this command saves exact root license texts beside downloaded sources. It never
imports upstream modules, executes hooks, installs packages, or builds a graph.
Require an explicit external --output directory; --cache can reuse pinned archives.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.fetch_task_inputs import fetch_one, verify  # noqa: E402

INPUTS = Path(__file__).resolve().parents[1] / 'benchmarks/catalog_reuse/inputs.json'
MAX_ARCHIVE = 32 * 1024 * 1024
MAX_SOURCE = 16 * 1024 * 1024
MAX_FILE = 2 * 1024 * 1024
EXCLUDED = {'tests', 'test', 'testing', '__pycache__'}


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def relative(value: str) -> str:
    if (not isinstance(value, str) or not value or '\\' in value or ':' in value
            or any(ord(c) < 32 for c in value)):
        raise ValueError('invalid relative path')
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in {'.', '..'} for p in value.split('/')):
        raise ValueError('unsafe relative path')
    if path.as_posix() != value:
        raise ValueError('relative path must use canonical POSIX spelling')
    return value


def outside_git(path: Path) -> Path:
    """Resolve aliases and reject ordinary, worktree, nested, and bare Git trees."""
    target = path.expanduser().resolve()
    parent = target
    while not parent.exists():
        parent = parent.parent
    if not parent.is_dir():
        raise ValueError('output/cache ancestor must be a directory')
    if any((ancestor / '.git').exists() for ancestor in [parent, *parent.parents]):
        raise ValueError('output/cache must be outside every Git tree')
    env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    probe = subprocess.run(['git', '-C', str(parent), 'rev-parse', '--is-inside-work-tree',
                            '--is-inside-git-dir'], capture_output=True, env=env, check=False)
    if probe.returncode == 0 and b'true' in probe.stdout.splitlines():
        raise ValueError('output/cache must be outside every Git tree')
    return target


def target_path(root: Path, name: str) -> Path:
    path = root / relative(name)
    for component in [path, *path.parents]:
        if component == root.parent:
            break
        if component.is_symlink():
            raise ValueError('symlink output path is forbidden')
        if (component / '.git').exists() or all((component / marker).exists()
                                                for marker in ['HEAD', 'objects', 'refs']):
            raise ValueError('output path is inside a nested Git tree')
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('output path escaped its external directory')
    return path


def publish_bytes(root: Path, name: str, raw: bytes, *, replace: bool = False) -> None:
    path = target_path(root, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not replace:
        if path.is_symlink() or not path.is_file() or path.read_bytes() != raw:
            raise ValueError('existing output does not match the pinned asset')
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name + '-',
                                     suffix='.part', delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(raw)
    try:
        if replace:
            os.replace(temporary, path)
        else:
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.is_symlink() or not path.is_file() or path.read_bytes() != raw:
                    raise ValueError('concurrent output does not match the pinned asset')
    finally:
        temporary.unlink(missing_ok=True)


def production(path: str, prefix: str) -> bool:
    return (path.startswith(prefix) and path.endswith(('.py', '.pyi'))
            and not EXCLUDED.intersection(path.split('/')))


def validate_inputs(data: dict) -> None:
    if data.get('schema_version') != 1 or data.get('status') != 'pinned_input_definitions':
        raise ValueError('unsupported pinned input schema/status')
    offsets = data['selection']['primary_ancestor_offsets']
    required = data['selection']['fixed_anchors_per_repository']
    if not offsets or offsets[-1] != 0 or offsets != sorted(set(offsets), reverse=True):
        raise ValueError('primary offsets must be unique, descending, and end at HEAD')
    if type(required) is not int or required <= 0:
        raise ValueError('invalid fixed anchor count')
    seen_repos = set()
    totals = {'repositories': 0, 'primary_snapshots': 0, 'primary_source_batches': 0,
              'secondary_event_pairs': 0, 'unique_snapshots': 0}
    if digest(json_bytes(data['input_rule'])) != data['input_rule_sha256']:
        raise ValueError('input rule SHA-256 mismatch')
    relative(data['input_rule_path'])
    for repo in data['repositories']:
        name = repo['repo']
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', name) or name in seen_repos:
            raise ValueError('invalid or duplicate upstream repository')
        seen_repos.add(name)
        prefix = repo['source_prefix']
        if not prefix.endswith('/'):
            raise ValueError('fixed source prefix must end with a slash')
        relative(prefix[:-1])
        chain = repo['first_parent_chain']
        if len(chain) <= offsets[0] or any(not re.fullmatch(r'[0-9a-f]{40}', c) for c in chain):
            raise ValueError('incomplete fixed commit chain')
        if chain[0] != repo['fixed_head']:
            raise ValueError('fixed HEAD mismatch')
        primary = repo['primary_snapshots']
        if len(primary) != len(offsets):
            raise ValueError('primary snapshot count mismatch')
        for order, (entry, offset) in enumerate(zip(primary, offsets, strict=True)):
            if entry != {'order': order, 'ancestor_offset': offset, 'commit': chain[offset]}:
                raise ValueError('primary snapshot ordering/identity mismatch')
        anchors = repo['anchors']
        if digest(json_bytes(anchors)) != repo['anchors_sha256']:
            raise ValueError('anchors SHA-256 mismatch')
        relative(repo['anchors_path'])
        if (anchors['initial_commit'] != primary[0]['commit']
                or len(anchors['anchors']) != required):
            raise ValueError('fixed initial anchor count/commit mismatch')
        identities = set()
        for anchor in anchors['anchors']:
            path = relative(anchor['path'])
            identity = path + ':' + anchor['symbol']
            if (not production(path, prefix) or identity != anchor['identity']
                    or identity in identities or digest(identity.encode()) != anchor['selection_sha256']):
                raise ValueError('fixed anchor identity/hash mismatch')
            identities.add(identity)
        if [a['selection_sha256'] for a in anchors['anchors']] != sorted(a['selection_sha256'] for a in anchors['anchors']):
            raise ValueError('fixed anchors are not in deterministic hash order')
        snapshots = {}
        for ref in repo['snapshots']:
            commit = ref['commit']
            if commit not in chain or commit in snapshots:
                raise ValueError('invalid or duplicate snapshot commit')
            metadata = ref['metadata']
            snapshots[commit] = metadata
            for field in ['metadata_path', 'archive_path']:
                relative(ref[field])
            if digest(json_bytes(metadata)) != ref['metadata_sha256']:
                raise ValueError('snapshot metadata SHA-256 mismatch')
            if (metadata['repo'] != name or metadata['commit'] != commit
                    or metadata['source_prefix'] != prefix):
                raise ValueError('snapshot repository/commit/scope mismatch')
            for field in ['archive_path', 'archive_sha256', 'source_tree_sha256',
                          'source_files', 'source_bytes']:
                if ref[field] != metadata[field]:
                    raise ValueError('snapshot reference disagrees with metadata')
            url = f'https://codeload.github.com/{name}/tar.gz/{commit}'
            if (metadata['archive_url'] != url or type(metadata['archive_bytes']) is not int
                    or not 0 < metadata['archive_bytes'] <= MAX_ARCHIVE
                    or not re.fullmatch(r'[0-9a-f]{64}', metadata['archive_sha256'])):
                raise ValueError('archive fixed HTTPS identity/size/hash mismatch')
            relative(metadata['source_directory'])
            folder = PurePosixPath(metadata['source_directory']).parent.as_posix()
            if (not metadata['source_directory'].endswith('/source')
                    or ref['metadata_path'] != folder + '/snapshot.json'):
                raise ValueError('snapshot output directory/metadata path mismatch')
            files = metadata['files']
            paths = []
            for asset in files + metadata['root_licenses']:
                relative(asset['path'])
                relative(asset['local_path'])
                if (type(asset['bytes']) is not int or not 0 <= asset['bytes'] <= MAX_FILE
                        or not re.fullmatch(r'[0-9a-f]{64}', asset['sha256'])
                        or not re.fullmatch(r'[0-9a-f]{40}', asset['git_blob_oid'])):
                    raise ValueError('declared source/license size or hash mismatch')
            for file in files:
                if not production(file['path'], prefix):
                    raise ValueError('declared file is outside the fixed production scope')
                if file['local_path'] != metadata['source_directory'] + '/' + file['path']:
                    raise ValueError('declared source output path mismatch')
                paths.append(file['path'])
            if paths != sorted(set(paths)) or len(paths) != metadata['source_files'] or len(paths) > 1500:
                raise ValueError('source catalog ordering/count mismatch')
            if sum(f['bytes'] for f in files) != metadata['source_bytes'] or metadata['source_bytes'] > MAX_SOURCE:
                raise ValueError('source byte count/cap mismatch')
            canonical = [[f['path'], f['bytes'], f['sha256']] for f in files]
            if digest(json.dumps(canonical, separators=(',', ':'), ensure_ascii=False).encode()) != metadata['source_tree_sha256']:
                raise ValueError('source tree SHA-256 mismatch')
            licenses = metadata['root_licenses']
            if not licenses or len({a['path'] for a in licenses}) != len(licenses):
                raise ValueError('exact root license text must be declared')
            if any('/' in a['path'] or not a['path'].upper().startswith(('LICENSE', 'COPYING', 'COPYRIGHT')) for a in licenses):
                raise ValueError('root license path mismatch')
            if any(a['local_path'] != folder + '/root-licenses/' + a['path'] for a in licenses):
                raise ValueError('root license output path mismatch')
        if any(a['path'] not in {f['path'] for f in snapshots[primary[0]['commit']]['files']}
               for a in anchors['anchors']):
            raise ValueError('initial fixed anchor source file is missing')
        required_commits = {entry['commit'] for entry in primary}
        events = repo['all_secondary_event_pairs']
        for order, event in enumerate(events):
            distance = event['first_parent_distance']
            if (event['order'] != order or type(distance) is not int or not 0 <= distance < len(chain) - 1
                    or event['commit'] != chain[distance] or event['parent'] != chain[distance + 1]):
                raise ValueError('catalog event first-parent pairing mismatch')
            if event['parent'] not in snapshots or event['commit'] not in snapshots:
                raise ValueError('catalog event snapshot is missing')
            required_commits.update([event['commit'], event['parent']])
            before = {f['path'] for f in snapshots[event['parent']]['files']}
            after = {f['path'] for f in snapshots[event['commit']]['files']}
            actual = sorted([{'status': 'A', 'path': p} for p in after - before]
                            + [{'status': 'D', 'path': p} for p in before - after],
                            key=lambda item: (item['status'], item['path']))
            if actual != sorted(event['catalog_changes'], key=lambda item: (item['status'], item['path'])):
                raise ValueError('catalog event path changes mismatch')
        if set(snapshots) != required_commits or len(snapshots) != repo['unique_snapshot_count']:
            raise ValueError('required snapshot set mismatch')
        totals['repositories'] += 1
        totals['primary_snapshots'] += len(primary)
        totals['primary_source_batches'] += len(primary) - 1
        totals['secondary_event_pairs'] += len(events)
        totals['unique_snapshots'] += len(snapshots)
    if any(data['counts'].get(key) != value for key, value in totals.items()):
        raise ValueError('input denominator counts mismatch')


def extract_declared(archive: Path, metadata: dict, output: Path) -> None:
    """Read only declared regular files, validate scope completeness, never extractall."""
    selected = {asset['path']: asset for asset in metadata['files'] + metadata['root_licenses']}
    seen = set()
    filtered = set()
    root_name = None
    with tarfile.open(archive, 'r:gz') as source:
        for member in source:
            name = relative(member.name.rstrip('/'))
            parts = PurePosixPath(name).parts
            if root_name is None:
                root_name = parts[0]
            if parts[0] != root_name:
                raise ValueError('archive must contain one root directory')
            if len(parts) == 1:
                if not member.isdir():
                    raise ValueError('archive root must be a directory')
                continue
            path = PurePosixPath(*parts[1:]).as_posix()
            if path in seen:
                raise ValueError('duplicate archive path')
            seen.add(path)
            if production(path, metadata['source_prefix']):
                filtered.add(path)
            if path not in selected:
                continue
            asset = selected[path]
            if not member.isfile() or member.size != asset['bytes']:
                raise ValueError('declared archive member must be a regular file with exact size')
            with source.extractfile(member) as stream:
                raw = stream.read(asset['bytes'] + 1)
            blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            if len(raw) != asset['bytes'] or digest(raw) != asset['sha256'] or blob != asset['git_blob_oid']:
                raise ValueError('declared source/license SHA-256 or Git blob mismatch')
            publish_bytes(output, asset['local_path'], raw)
    if filtered != {file['path'] for file in metadata['files']} or not set(selected) <= seen:
        raise ValueError('archive does not contain the exact declared production catalog/licenses')
    source_dir = target_path(output, metadata['source_directory'])
    actual = set()
    for path in source_dir.rglob('*'):
        if path.is_symlink():
            raise ValueError('symlink in extracted source directory')
        if path.is_file():
            actual.add(path.relative_to(source_dir).as_posix())
    if actual != {file['path'] for file in metadata['files']}:
        raise ValueError('existing extracted source directory has undeclared files')


def prepare(data: dict, output: Path, *, cache: Path | None = None,
            timeout: int = 120, transport=None, sources_pin_sha256: str | None = None) -> dict:
    output = outside_git(output)
    cache = outside_git(cache if cache is not None else output / 'archives')
    output.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    publish_bytes(output, 'ready-manifest.json', json_bytes({'status': 'input_preparation_in_progress'}), replace=True)
    try:
        validate_inputs(data)
        source_pin = digest(json_bytes(data)) if sources_pin_sha256 is None else sources_pin_sha256
        if not re.fullmatch(r'[0-9a-f]{64}', source_pin):
            raise ValueError('sources pin SHA-256 is invalid')
        publish_bytes(output, data['input_rule_path'], json_bytes(data['input_rule']))
        result = {key: deepcopy(data[key]) for key in ['schema_version', 'input_rule_path', 'input_rule_sha256']}
        result.update(status='input_assets_ready', sources_pin_sha256=source_pin,
                      primary_total_snapshots_with_roles=data['counts']['primary_snapshots'],
                      primary_total_source_batches=data['counts']['primary_source_batches'],
                      secondary_total_event_pairs=data['counts']['secondary_event_pairs'],
                      total_unique_snapshots=data['counts']['unique_snapshots'], repositories=[],
                      archive_acquisition={'downloaded': 0, 'cache_reused': 0},
                      preparation_script_path='scripts/prepare_catalog_sources.py',
                      preparation_script_sha256=digest(Path(__file__).read_bytes()),
                      no_upstream_code_executed=True, no_resolver_graph_or_performance_executed=True,
                      not_protocol_freeze_or_research_result=True, failures=[])
        for repo in data['repositories']:
            row = {key: deepcopy(value) for key, value in repo.items() if key not in {'anchors', 'snapshots'}}
            publish_bytes(output, repo['anchors_path'], json_bytes(repo['anchors']))
            row['snapshots'] = []
            for ref in repo['snapshots']:
                metadata = ref['metadata']
                record = {'name': PurePosixPath(ref['archive_path']).name,
                          'url': metadata['archive_url'], 'bytes': metadata['archive_bytes'],
                          'sha256': metadata['archive_sha256']}
                state = fetch_one(record, cache, timeout, transport=transport)
                result['archive_acquisition']['cache_reused' if state.startswith('reused') else 'downloaded'] += 1
                archived = target_path(output, ref['archive_path'])
                if archived != cache / record['name']:
                    archived.parent.mkdir(parents=True, exist_ok=True)
                    if archived.exists():
                        verify(archived, record)
                    else:
                        try:
                            os.link(cache / record['name'], archived)
                        except FileExistsError:
                            verify(archived, record)
                        except OSError:
                            publish_bytes(output, ref['archive_path'], (cache / record['name']).read_bytes())
                            verify(archived, record)
                verify(archived, record)
                extract_declared(archived, metadata, output)
                verify(archived, record)
                publish_bytes(output, ref['metadata_path'], json_bytes(metadata))
                row['snapshots'].append({key: deepcopy(value) for key, value in ref.items() if key != 'metadata'})
            result['repositories'].append(row)
        publish_bytes(output, 'ready-manifest.json', json_bytes(result), replace=True)
        return result
    except Exception as error:
        publish_bytes(output, 'ready-manifest.json', json_bytes({'status': 'input_preparation_failed',
                       'error_type': type(error).__name__, 'completed_assets_retained': True}), replace=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='explicit directory outside every Git tree')
    parser.add_argument('--archive-cache', '--cache', dest='cache', type=Path,
                        help='optional external archive cache; default is OUTPUT/archives')
    parser.add_argument('--inputs', type=Path, default=INPUTS, help='pinned public metadata file')
    parser.add_argument('--timeout', type=int, default=120, help='HTTPS timeout per archive, 1–300 seconds')
    args = parser.parse_args()
    if not 1 <= args.timeout <= 300:
        parser.error('timeout must be 1–300 seconds')
    raw = args.inputs.read_bytes()
    result = prepare(json.loads(raw), args.output, cache=args.cache, timeout=args.timeout,
                     sources_pin_sha256=digest(raw))
    print(f"Verified {result['total_unique_snapshots']} pinned snapshots; no upstream code executed.")
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, tarfile.TarError) as error:
        print(f'Catalog input preparation stopped: {error}', file=sys.stderr)
        raise SystemExit(1)
