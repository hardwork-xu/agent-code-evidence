#!/usr/bin/env python3
"""Prepare fixed upstream inputs outside Git. / 在 Git 外准备固定上游输入。

Only verified regular archive/wheel files are materialized. No upstream imports,
package build hooks, setup.py, installers, or candidate graphs are executed.
仅解压经哈希核对的普通文件；不执行上游导入、构建钩子或候选图。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile
from urllib.parse import urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'benchmarks/global_bindings/upstream_execution'
MAX_ARCHIVE = 32 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
MAX_FILE = 4 * 1024 * 1024


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def safe_relative(value: str) -> str:
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise ValueError('invalid relative path / 相对路径无效')
    path = PurePosixPath(value)
    if (path.is_absolute() or path.as_posix() != value
            or any(x in {'', '.', '..'} for x in value.split('/'))
            or any(ord(x) < 32 for x in value)):
        raise ValueError('unsafe relative path / 相对路径越界')
    return value


def source_name(repository: str, sha: str) -> str:
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('invalid repository identity')
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('invalid commit identity')
    return repository.replace('/', '--') + '-' + sha[:12]


def outside_git(path: Path) -> Path:
    target = path.expanduser().resolve()
    for ancestor in [target, *target.parents]:
        if ((ancestor / '.git').exists()
                or all((ancestor / x).exists() for x in ['HEAD', 'objects', 'refs'])):
            raise ValueError('output/cache must be outside Git / 输出与缓存必须位于 Git 外')
    return target


def checked_path(root: Path, relative: str) -> Path:
    path = root / safe_relative(relative)
    for item in [path, *path.parents]:
        if item == root.parent:
            break
        if item.is_symlink():
            raise ValueError('symlink input/output is forbidden')
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('input/output escaped its root')
    return path


def validate_files(root: Path, expected: dict) -> None:
    """Verify every byte and reject added source files. / 核对字节并拒绝新增源码。"""
    for name, entry in expected.items():
        path = checked_path(root, name)
        if (not path.is_file() or path.stat().st_size != entry['bytes']
                or sha256(path.read_bytes()) != entry['sha256']):
            raise ValueError('pinned file identity mismatch: ' + name)
    extra = [p.relative_to(root).as_posix() for p in root.rglob('*')
             if p.is_file() and p.suffix in {'.py', '.pyi'}
             and '__pycache__' not in p.parts and p.relative_to(root).as_posix() not in expected]
    if extra:
        raise ValueError('unexpected executable source files')


def validate_inputs(data: dict) -> None:
    if data.get('schema_version') != 1 or data.get('status') != 'frozen_upstream_execution_inputs':
        raise ValueError('unsupported input schema/status')
    identities = set()
    for source in data['sources']:
        name = source_name(source['repository'], source['sha'])
        if source['directory'] != name or name in identities:
            raise ValueError('duplicate or inconsistent source identity')
        identities.add(name)
        expected_url = f"https://codeload.github.com/{source['repository']}/tar.gz/{source['sha']}"
        if source['archive_url'] != expected_url:
            raise ValueError('archive URL does not match its fixed commit')
        if not re.fullmatch(r'[0-9a-f]{64}', source['archive_sha256']):
            raise ValueError('invalid archive hash')
        total = 0
        for path, item in source['regular_files'].items():
            safe_relative(path)
            if (not re.fullmatch(r'[0-9a-f]{64}', item['sha256'])
                    or type(item['bytes']) is not int or not 0 <= item['bytes'] <= MAX_FILE):
                raise ValueError('invalid pinned file metadata')
            total += item['bytes']
        if total != source['source_bytes'] or total > MAX_TOTAL:
            raise ValueError('invalid source-byte total')
    for case in data['cases']:
        for sha in [case['fixed_sha'], case['parent_sha']]:
            if source_name(case['repository'], sha) not in identities:
                raise ValueError('missing source role')
        safe_relative(case['package_path'])
        for node in case['tests']:
            safe_relative(node.split('::')[0])
            if not node.startswith('tests/') or len(node.split('::')) < 2:
                raise ValueError('invalid selected upstream test node')


def acquire(url: str, digest: str, destination: Path, cache: Path | None,
            offline: bool) -> Path:
    """HTTPS + digest only; never disable TLS. / 仅 HTTPS 和哈希；不关闭 TLS。"""
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname not in
            {'codeload.github.com', 'files.pythonhosted.org'}
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError('unapproved download URL')
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.is_symlink() or sha256(destination.read_bytes()) != digest:
            raise ValueError('existing archive hash mismatch')
        return destination
    if cache is not None:
        cached = cache / destination.name
        if cached.exists():
            if cached.is_symlink() or sha256(cached.read_bytes()) != digest:
                raise ValueError('cached archive hash mismatch')
            destination.write_bytes(cached.read_bytes())
            return destination
    if offline:
        raise ValueError('pinned asset absent in offline cache')
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as f:
        part = Path(f.name)
    try:
        result = subprocess.run(['curl', '--fail', '--silent', '--show-error', '--location',
                                 '--proto', '=https', '--proto-redir', '=https',
                                 '--max-time', '120', '--max-filesize', str(MAX_ARCHIVE),
                                 '--output', str(part), url], capture_output=True, check=False)
        if result.returncode or sha256(part.read_bytes()) != digest:
            raise ValueError('download failed or pinned digest mismatch')
        os.replace(part, destination)
    finally:
        part.unlink(missing_ok=True)
    return destination


def extract_archive(archive: Path, destination: Path, expected: dict) -> list[str]:
    skipped = []
    seen = set()
    total = 0
    with tarfile.open(archive, 'r:gz') as stream:
        for member in stream:
            parts = PurePosixPath(member.name).parts
            if not parts or member.name.startswith('/') or '..' in parts:
                raise ValueError('unsafe archive member')
            if len(parts) == 1 and member.isdir():
                continue
            name = safe_relative('/'.join(parts[1:]))
            if member.isdir():
                continue
            if not member.isfile():
                skipped.append(name)
                continue
            if name in seen or name not in expected:
                raise ValueError('duplicate or unpinned archive member')
            seen.add(name)
            total += member.size
            if member.size > MAX_FILE or total > MAX_TOTAL:
                raise ValueError('archive resource cap exceeded')
            raw = stream.extractfile(member).read()
            if len(raw) != expected[name]['bytes'] or sha256(raw) != expected[name]['sha256']:
                raise ValueError('archive file digest mismatch')
            path = checked_path(destination, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    if seen != set(expected):
        raise ValueError('archive missing pinned regular files')
    validate_files(destination, expected)
    return skipped


def prepare_sources(data: dict, output: Path, cache: Path | None = None,
                    offline: bool = False) -> dict:
    validate_inputs(data)
    output = outside_git(output)
    cache = outside_git(cache) if cache else None
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for source in data['sources']:
        directory = checked_path(output, source['directory'])
        if directory.exists():
            validate_files(directory, source['regular_files'])
            records.append({'repository': source['repository'], 'sha': source['sha'],
                            'directory': source['directory'], 'status': 'verified_existing'})
            continue
        archive = acquire(source['archive_url'], source['archive_sha256'],
                          checked_path(output, '.archives/' + source['directory'] + '.tar.gz'),
                          cache, offline)
        with tempfile.TemporaryDirectory(dir=output, prefix='.prepare-') as temporary:
            stage = Path(temporary) / 'source'
            stage.mkdir()
            skipped = extract_archive(archive, stage, source['regular_files'])
            stage.rename(directory)
        records.append({'repository': source['repository'], 'sha': source['sha'],
                        'directory': source['directory'], 'status': 'verified_extracted',
                        'skipped_nonregular_members': skipped})
    result = {'schema_version': 1, 'sources': records, 'source_code_executed': False}
    (output / 'prepared.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def prepare_dependencies(data: dict, output: Path, cache: Path | None = None,
                         offline: bool = False) -> None:
    if data.get('schema_version') != 1:
        raise ValueError('invalid dependency schema')
    output = outside_git(output)
    cache = outside_git(cache) if cache else None
    runtime = checked_path(output, 'dependencies/python')
    runtime.mkdir(parents=True, exist_ok=True)
    all_files = {}
    for package in data['packages']:
        if not package['wheel'].endswith('py3-none-any.whl'):
            raise ValueError('only reviewed pure-Python wheels are allowed')
        wheel = acquire(package['url'], package['sha256'],
                        checked_path(output, 'dependencies/wheels/' + package['wheel']), cache, offline)
        expected = package['regular_files']
        total = 0
        seen = set()
        with zipfile.ZipFile(wheel) as stream:
            for info in stream.infolist():
                name = safe_relative(info.filename.rstrip('/'))
                if info.is_dir():
                    continue
                total += info.file_size
                if (info.file_size > MAX_FILE or total > MAX_TOTAL
                        or ((info.external_attr >> 16) & 0o170000) == 0o120000
                        or name in seen or name not in expected):
                    raise ValueError('unsafe or unpinned wheel member')
                seen.add(name)
                raw = stream.read(info)
                if len(raw) != expected[name]['bytes'] or sha256(raw) != expected[name]['sha256']:
                    raise ValueError('wheel member digest mismatch')
                path = checked_path(runtime, name)
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.exists() and path.read_bytes() != raw:
                    raise ValueError('conflicting dependency runtime file')
                path.write_bytes(raw)
        if seen != set(expected) or set(all_files).intersection(expected):
            raise ValueError('missing or conflicting pinned wheel files')
        all_files.update(expected)
    validate_files(runtime, all_files)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True,
                        help='external source directory / 仓库外源码目录')
    parser.add_argument('--cache', type=Path, help='verified archive cache / 已验证的缓存')
    parser.add_argument('--dependency-cache', type=Path)
    parser.add_argument('--offline', action='store_true', help='never download / 禁止联网')
    parser.add_argument('--with-dependencies', action='store_true')
    args = parser.parse_args()
    data = json.loads((DATA / 'inputs.json').read_text())
    result = prepare_sources(data, args.source_root, args.cache, args.offline)
    if args.with_dependencies:
        prepare_dependencies(json.loads((DATA / 'dependencies.json').read_text()), args.source_root,
                             args.dependency_cache, args.offline)
    print(json.dumps({'verified_sources': len(result['sources']),
                      'dependencies_prepared': args.with_dependencies,
                      'source_code_executed': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
