"""Read-only verified source archives and immutable results / 只读源码与不可覆盖结果。"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile
import tokenize

from .scoring import safe_path


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def write_new(path: Path, value) -> None:
    """Reject replacement, including symlinks / 拒绝覆盖，包括符号链接。"""
    with path.open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def archive_texts(path: Path, expected_sha256: str, *, max_bytes=32 * 1024**2,
                  max_files=5000, max_file_bytes=1024**2) -> tuple[dict, dict]:
    """Parse source bytes only; never extract/import/execute upstream content.

    Whole-task failure on resource overflow prevents silent truncation. Links
    and undecodable source are counted; their target labels stay in denominator.
    不运行上游代码；超过资源阈值使整项失败，不静默截断。不可读文件显式计数。
    """
    if path.is_symlink():
        raise ValueError('source archive cannot be a symlink')
    raw = path.read_bytes()
    if sha256(raw) != expected_sha256:
        raise ValueError('source archive checksum mismatch')
    texts, hashes = {}, {}
    skipped = {'nonregular_python': 0, 'undecodable_python': 0}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:*') as archive:
        members = archive.getmembers()
        roots = {PurePosixPath(m.name).parts[0] for m in members if m.name}
        if len(roots) != 1:
            raise ValueError('archive must have one root')
        for member in sorted(members, key=lambda m: m.name):
            safe_path(member.name.rstrip('/'))
            parts = PurePosixPath(member.name).parts
            if len(parts) < 2 or not member.name.endswith('.py'):
                continue
            name = safe_path(PurePosixPath(*parts[1:]).as_posix())
            if not member.isfile():
                skipped['nonregular_python'] += 1
                continue
            if name in hashes:
                raise ValueError('duplicate source member')
            total += member.size
            if (member.size > max_file_bytes or total > max_bytes
                    or len(hashes) >= max_files):
                raise ValueError('source resource limit exceeded')
            with archive.extractfile(member) as stream:
                content = stream.read(max_file_bytes + 1)
            hashes[name] = sha256(content)
            try:
                encoding, _ = tokenize.detect_encoding(io.BytesIO(content).readline)
                texts[name] = content.decode(encoding)
            except (SyntaxError, UnicodeError, LookupError):
                skipped['undecodable_python'] += 1
    return texts, {'source_files': len(hashes), 'decoded_files': len(texts),
                   'python_bytes': total, 'source_manifest_sha256': sha256(canonical(hashes)),
                   'skipped': skipped}
