#!/usr/bin/env python3
"""Download the six pinned task archives; never extract or execute their contents.

下载六个固定归档并核对 SHA-256；不解压、不执行、不使用账号认证。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

MANIFEST = Path(__file__).resolve().parents[1] / 'benchmarks/task_evidence/manifest.json'
MAX_ARCHIVE_BYTES = 10 * 1024 * 1024
CHUNK = 64 * 1024


def artifacts(manifest: dict) -> list[dict]:
    repositories = manifest.get('repositories', {})
    if set(repositories) != {'attrs', 'packaging', 'pluggy'}:
        raise ValueError('expected the three frozen projects / 必须是固定的三个项目')
    result = []
    for name, repository in sorted(repositories.items()):
        repo_url = repository['repository']
        if not re.fullmatch(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo_url):
            raise ValueError('invalid upstream repository URL / 上游地址无效')
        if set(repository['versions']) != {'before', 'after'}:
            raise ValueError('expected both fixed versions / 必须包含两个固定版本')
        for state, pin in sorted(repository['versions'].items()):
            commit, sha, size = pin['commit'], pin['archive_sha256'], pin['archive_bytes']
            expected = 'https://codeload.github.com/' + repo_url.removeprefix('https://github.com/') + '/tar.gz/' + commit
            if (not re.fullmatch(r'[0-9a-f]{40}', commit)
                    or not re.fullmatch(r'[0-9a-f]{64}', sha)
                    or type(size) is not int or not 0 < size <= MAX_ARCHIVE_BYTES
                    or pin['archive_url'] != expected):
                raise ValueError('invalid frozen archive identity / 固定归档身份无效')
            result.append({'name': f'{name}-{state}.tar.gz', 'url': expected,
                           'sha256': sha, 'bytes': size})
    return result


def verify(path: Path, record: dict) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError('cache entry must be a regular file / 缓存项必须是普通文件')
    if path.stat().st_size != record['bytes']:
        raise ValueError('cached/archive byte count mismatch / 缓存或归档大小不匹配')
    digest = hashlib.sha256()
    with path.open('rb') as source:
        while block := source.read(CHUNK):
            digest.update(block)
    if digest.hexdigest() != record['sha256']:
        raise ValueError('cached/archive SHA-256 mismatch / 缓存或归档哈希不匹配')


def copy_bounded(source, destination, limit: int) -> int:
    total = 0
    while block := source.read(min(CHUNK, limit - total + 1)):
        total += len(block)
        if total > limit:
            raise ValueError('download exceeds frozen byte limit / 下载超过固定大小上限')
        destination.write(block)
    return total


def download_curl(record: dict, destination: Path, timeout: int) -> None:
    curl = '/usr/bin/curl' if Path('/usr/bin/curl').is_file() else shutil.which('curl')
    if not curl:
        raise RuntimeError('curl is required / 需要 curl')
    # -q disables user curlrc; no cookies, credentials, netrc or insecure TLS flags.
    command = [curl, '-q', '--fail', '--silent', '--show-error', '--location',
               '--proto', '=https', '--proto-redir', '=https', '--max-redirs', '3',
               '--connect-timeout', '15', '--max-time', str(timeout),
               '--max-filesize', str(record['bytes']), record['url']]
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as child:
        try:
            with destination.open('wb') as target:
                copy_bounded(child.stdout, target, record['bytes'])
                target.flush()
                os.fsync(target.fileno())
            _, error = child.communicate(timeout=5)
            if child.returncode:
                message = error[:1024].decode('utf-8', errors='replace').strip()
                raise RuntimeError(f'HTTPS download failed / HTTPS 下载失败: {message}')
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)


def fetch_one(record: dict, cache: Path, timeout: int = 120, *, transport=None) -> str:
    target = cache / record['name']
    if target.exists() or target.is_symlink():
        verify(target, record)
        return 'reused / 复用'
    transport = download_curl if transport is None else transport
    with tempfile.NamedTemporaryFile(prefix='.' + record['name'] + '-', suffix='.part',
                                     dir=cache, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        transport(record, temporary, timeout)
        verify(temporary, record)
        try:
            # Atomic no-clobber publication; a concurrently created cache is verified.
            os.link(temporary, target)
        except FileExistsError:
            verify(target, record)
            return 'reused / 复用'
        return 'downloaded / 下载'
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True,
                        help='external archive directory / 仓库外的归档目录')
    parser.add_argument('--timeout', type=int, default=120,
                        help='seconds per archive, 1–300 / 每个归档的秒数，1–300')
    args = parser.parse_args()
    if not 1 <= args.timeout <= 300:
        parser.error('timeout must be 1–300 seconds / 超时必须为 1–300 秒')
    records = artifacts(json.loads(MANIFEST.read_text()))
    args.cache.mkdir(parents=True, exist_ok=True)
    for record in records:
        state = fetch_one(record, args.cache, args.timeout)
        print(f'{record["name"]}: {state}; SHA-256 verified / 哈希已核验')
    print('Six archives ready; nothing extracted or executed. / 六个归档已就绪；未解压或执行。')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'Fetch stopped / 下载已停止: {error}', file=sys.stderr)
        raise SystemExit(1)
