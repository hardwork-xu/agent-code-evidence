"""Source ingestion must never execute repository code / 源码读取不可执行代码。"""
import io
import tarfile

import pytest

from benchmarks.external_context.io import archive_texts, sha256, write_new


def archive(tmp_path, members):
    path = tmp_path / 'source.tar'
    with tarfile.open(path, 'w') as tf:
        for name, content in members:
            item = tarfile.TarInfo(name)
            item.size = len(content)
            tf.addfile(item, io.BytesIO(content))
    return path, sha256(path.read_bytes())


def test_read_only_python_source_and_encoding(tmp_path):
    path, digest = archive(tmp_path, [('root/a.py', b'raise RuntimeError("never execute")\n'),
                                    ('root/b.py', b'# coding: latin-1\n# \xe9\n'),
                                    ('root/LICENSE', b'license')])
    texts, metadata = archive_texts(path, digest)
    assert len(texts) == metadata['decoded_files'] == 2
    assert 'é' in texts['b.py']


def test_invalid_encoding_counted(tmp_path):
    path, digest = archive(tmp_path, [('root/a.py', b'\xff\xfe')])
    texts, metadata = archive_texts(path, digest)
    assert texts == {}
    assert metadata['skipped']['undecodable_python'] == 1


def test_checksum_and_budget_rejected(tmp_path):
    path, digest = archive(tmp_path, [('root/a.py', b'pass\n')])
    with pytest.raises(ValueError, match='checksum'):
        archive_texts(path, '0' * 64)
    with pytest.raises(ValueError, match='resource'):
        archive_texts(path, digest, max_bytes=2)


@pytest.mark.parametrize('name', ['root/../x.py', '/root/x.py'])
def test_archive_paths_rejected(tmp_path, name):
    path, digest = archive(tmp_path, [(name, b'pass')])
    with pytest.raises(ValueError):
        archive_texts(path, digest)


def test_duplicate_archive_entries_rejected(tmp_path):
    path, digest = archive(tmp_path, [('root/a.py', b'pass'), ('root/a.py', b'pass')])
    with pytest.raises(ValueError, match='duplicate'):
        archive_texts(path, digest)


def test_new_result_does_not_follow_symlink_or_clobber(tmp_path):
    original = tmp_path / 'original'
    original.write_bytes(b'unchanged')
    link = tmp_path / 'result'
    link.symlink_to(original)
    with pytest.raises(FileExistsError):
        write_new(link, {})
    with pytest.raises(FileExistsError):
        write_new(original, {})
    assert original.read_bytes() == b'unchanged'
