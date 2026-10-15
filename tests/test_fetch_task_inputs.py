"""Downloader integrity tests use local fake transports; they perform no network I/O."""
import hashlib
import io
import json

import pytest

from scripts.fetch_task_inputs import MANIFEST, artifacts, copy_bounded, fetch_one


def record(data=b'archive data'):
    return {'name': 'example-before.tar.gz', 'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest(), 'url': 'https://example.invalid/pin'}


def test_fixed_manifest_exposes_only_six_pinned_https_archives():
    rows = artifacts(json.loads(MANIFEST.read_text()))
    assert len(rows) == len({r['name'] for r in rows}) == 6
    assert {r['name'] for r in rows} == {
        f'{project}-{state}.tar.gz' for project in ['attrs', 'packaging', 'pluggy']
        for state in ['before', 'after']}
    manifest = json.loads(MANIFEST.read_text())
    manifest['repositories']['attrs']['versions']['before']['archive_url'] = 'http://example.invalid'
    with pytest.raises(ValueError, match='identity'):
        artifacts(manifest)


def test_checksum_failure_never_publishes_and_cleans_temporary_download(tmp_path):
    def corrupt(_record, path, _timeout):
        path.write_bytes(b'bad archive!')  # Same length as the expected data.
    with pytest.raises(ValueError, match='SHA-256'):
        fetch_one(record(), tmp_path, transport=corrupt)
    assert list(tmp_path.iterdir()) == []


def test_verified_cache_reuses_without_network_and_mismatch_is_not_overwritten(tmp_path):
    item = record()
    target = tmp_path / item['name']
    target.write_bytes(b'archive data')
    def forbidden(*args):
        raise AssertionError('network should not be called')
    assert fetch_one(item, tmp_path, transport=forbidden).startswith('reused')
    target.write_bytes(b'bad archive!')
    with pytest.raises(ValueError, match='SHA-256'):
        fetch_one(item, tmp_path, transport=forbidden)
    assert target.read_bytes() == b'bad archive!'


def test_verified_download_is_published_without_extracting(tmp_path):
    content = b'not a real tar file; download-only tool must not parse or execute this'
    item = record(content)
    def transport(_record, path, _timeout):
        path.write_bytes(content)
    assert fetch_one(item, tmp_path, transport=transport).startswith('downloaded')
    assert {p.name for p in tmp_path.iterdir()} == {item['name']}
    assert (tmp_path / item['name']).read_bytes() == content


def test_stream_limit_rejects_extra_bytes():
    output = io.BytesIO()
    with pytest.raises(ValueError, match='byte limit'):
        copy_bounded(io.BytesIO(b'123456'), output, 5)
    assert len(output.getvalue()) <= 5


def test_failed_transport_cleans_partial_without_final_cache(tmp_path):
    def failure(_record, path, _timeout):
        path.write_bytes(b'partial')
        raise OSError('simulated download interruption')
    with pytest.raises(OSError, match='interruption'):
        fetch_one(record(), tmp_path, transport=failure)
    assert list(tmp_path.iterdir()) == []


def test_concurrent_mismatched_cache_is_preserved_and_rejected(tmp_path):
    item = record()
    target = tmp_path / item['name']
    def raced(_record, path, _timeout):
        path.write_bytes(b'archive data')
        target.write_bytes(b'bad archive!')
    with pytest.raises(ValueError, match='SHA-256'):
        fetch_one(item, tmp_path, transport=raced)
    assert target.read_bytes() == b'bad archive!'
    assert list(tmp_path.iterdir()) == [target]


def test_symlink_cache_rejected_without_touching_target(tmp_path):
    destination = tmp_path / 'original'
    destination.write_bytes(b'archive data')
    link = tmp_path / record()['name']
    link.symlink_to(destination)
    with pytest.raises(ValueError, match='regular file'):
        fetch_one(record(), tmp_path)
    assert destination.read_bytes() == b'archive data'
