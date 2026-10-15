"""Owned bounded-read/source binding controls / 自编限量读取及源码SHA绑定反例。"""
import csv
import io
from pathlib import Path
import tarfile

import pytest

from benchmarks.known_task_execution import prepare as p


def csv_bytes(value):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=['instance_id', 'F2P', 'P2P', 'patch'])
    writer.writeheader()
    writer.writerow({'instance_id': 'owned__source-1', 'F2P': '[]', 'P2P': '[]', 'patch': value})
    return stream.getvalue().encode()


def tar_bytes(value):
    target = io.BytesIO()
    with tarfile.open(fileobj=target, mode='w:gz') as out:
        item = tarfile.TarInfo('root/module.py')
        item.size = len(value)
        out.addfile(item, io.BytesIO(value))
    return target.getvalue()


def instrument_read(monkeypatch, target, replacement=None):
    open_path = Path.open
    requests = []

    class Reader:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def read(self, size=-1):
            requests.append(size)
            raw = self.stream.read(size)
            if replacement is not None:
                target.write_bytes(replacement)
            return raw

    def wrapped_open(path, mode='r', *args, **kwargs):
        stream = open_path(path, mode, *args, **kwargs)
        return Reader(stream) if path == target and mode == 'rb' else stream

    monkeypatch.setattr(Path, 'open', wrapped_open)
    return requests


def test_csv_parses_single_bounded_verified_read_after_owned_disk_replacement(tmp_path, monkeypatch):
    target = tmp_path / 'owned.csv'
    original, replacement = csv_bytes('original'), csv_bytes('replacement')
    target.write_bytes(original)
    requests = instrument_read(monkeypatch, target, replacement)
    result = p.task_row(target, 'owned__source-1', p.digest(original))
    assert result['patch'] == 'original'
    assert requests == [p.MAX_CSV_BYTES + 1]


def test_tar_parses_single_bounded_verified_read_after_owned_disk_replacement(tmp_path, monkeypatch):
    target = tmp_path / 'owned.tar.gz'
    original, replacement = tar_bytes(b'original\n'), tar_bytes(b'replacement\n')
    target.write_bytes(original)
    requests = instrument_read(monkeypatch, target, replacement)
    files, _ = p.archive_files(target, p.digest(original), {
        'repo': 'owned/source', 'instance_id': 'owned__source-1', 'patch': '', 'test_patch': ''})
    assert files['module.py'] == b'original\n'
    assert requests == [p.MAX_ARCHIVE_BYTES + 1]


@pytest.mark.parametrize('kind', ['csv', 'archive'])
def test_oversize_rejected_after_limit_plus_one_read_before_parsing(tmp_path, monkeypatch, kind):
    target = tmp_path / ('owned.csv' if kind == 'csv' else 'owned.tar.gz')
    raw = csv_bytes('owned') if kind == 'csv' else tar_bytes(b'owned\n')
    target.write_bytes(raw)
    requests = instrument_read(monkeypatch, target)
    if kind == 'csv':
        monkeypatch.setattr(p, 'MAX_CSV_BYTES', 8)
        with pytest.raises(ValueError, match='byte cap'):
            p.task_row(target, 'owned__source-1', p.digest(raw))
    else:
        monkeypatch.setattr(p, 'MAX_ARCHIVE_BYTES', 8)
        with pytest.raises(ValueError, match='byte cap'):
            p.archive_files(target, p.digest(raw), {
                'repo': 'owned/source', 'instance_id': 'owned__source-1', 'patch': '', 'test_patch': ''})
    assert requests == [9]
