"""Fetch pinned public data without executing it / 下载固定公开数据，不执行内容。"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from .io import sha256
from .runner import PROTOCOL


def fetch(url: str, target: Path, digest: str, ceiling: int):
    """Reuse matching cache; refuse mismatches and concurrent overwrites.

    复用匹配缓存，拒绝错误缓存及并发覆盖。curl正常校验TLS证书。
    """
    if target.exists() or target.is_symlink():
        if target.is_symlink() or sha256(target.read_bytes()) != digest:
            raise ValueError('existing cache checksum mismatch')
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, pending_name = tempfile.mkstemp(prefix='.' + target.name + '.', dir=target.parent)
    os.close(fd)
    pending = Path(pending_name)
    try:
        subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error',
                        '--retry', '1', '--connect-timeout', '15', '--max-time', '600',
                        '--max-filesize', str(ceiling), '--output', str(pending), url], check=True)
        if sha256(pending.read_bytes()) != digest:
            raise ValueError('download checksum mismatch')
        os.link(pending, target)
    finally:
        pending.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description='Fetch frozen pilot inputs / 下载冻结试验输入')
    parser.add_argument('--cache', type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(PROTOCOL.read_text())
    sources_path = PROTOCOL.with_name('sources.json')
    sources = json.loads(sources_path.read_text())
    fetch(protocol['dataset']['url'], args.cache / 'test.csv',
          protocol['dataset']['sha256'], 32 * 1024**2)
    for task in sources['tasks']:
        fetch(task['source_url'], args.cache / task['archive'],
              task['archive_sha256'], 500 * 1024**2)
        license_url = f"https://raw.githubusercontent.com/{task['repo']}/{task['base_commit']}/LICENSE"
        fetch(license_url, args.cache / task['license'], task['license_sha256'], 1024**2)
        print(task['instance_id'] + ': verified / 已核验')
    manifest = args.cache / 'sources.json'
    raw = sources_path.read_bytes()
    if manifest.exists():
        if manifest.read_bytes() != raw:
            raise ValueError('cache manifest differs')
    else:
        with manifest.open('xb') as stream:
            stream.write(raw)


if __name__ == '__main__':
    main()
