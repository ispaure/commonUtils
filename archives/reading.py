"""Validated ZIP/TAR readers, header inspection and integrity checks."""
from contextlib import contextmanager
from datetime import datetime
from pathlib import PurePosixPath
import tarfile
import zipfile
import unicodedata

from ..operations import check_cancelled
from ..streams import stream_signature
from ..zip_access import open_archive, validate_members, archive_manifest
from .models import Entry


@contextmanager
def reader(path, password=None):
    if zipfile.is_zipfile(path):
        with open_archive(path, password=password) as archive:
            validate_members(archive)
            yield archive, True
    else:
        with tarfile.open(path, 'r:*') as archive:
            validate_tar(archive)
            yield archive, False


def validate_tar(archive):
    seen, kinds = set(), {}
    for item in archive.getmembers():
        name = item.name.replace('\\', '/')
        path = PurePosixPath(name)
        if (not name or '\x00' in name or path.is_absolute() or '..' in path.parts
                or ':' in name or not path.parts or not (item.isfile() or item.isdir())):
            raise ValueError(f'Unsafe or unsupported TAR member: {item.name}')
        key = unicodedata.normalize('NFC', path.as_posix()).casefold()
        if key in seen:
            raise ValueError(f'Duplicate archive member: {item.name}')
        seen.add(key)
        kinds[key] = item.isdir()
    for name in kinds:
        for parent in PurePosixPath(name).parents:
            if parent.as_posix() in kinds and not kinds[parent.as_posix()]:
                raise ValueError(f'Archive file is also a directory: {parent}')


def entries(path, *, progress=lambda *args: None, cancelled=lambda: False):
    """Headers can be browsed without unlocking encrypted ZIP payloads."""
    result = []
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            validate_members(archive)
            for item in archive.infolist():
                check_cancelled(cancelled)
                result.append(Entry(item.filename.replace('\\', '/'), item.file_size,
                                    item.compress_size, item.is_dir(),
                                    '%04d-%02d-%02d %02d:%02d' % item.date_time[:5], bool(item.flag_bits & 1)))
    else:
        with tarfile.open(path, 'r:*') as archive:
            validate_tar(archive)
            for item in archive.getmembers():
                check_cancelled(cancelled)
                result.append(Entry(item.name.replace('\\', '/'), item.size, None, item.isdir(),
                                    datetime.fromtimestamp(item.mtime).strftime('%Y-%m-%d %H:%M')))
    return tuple(result)


def _members(archive, is_zip):
    return archive.infolist() if is_zip else archive.getmembers()


def _name(item, is_zip):
    return (item.filename if is_zip else item.name).replace('\\', '/')


def _directory(item, is_zip):
    return item.is_dir() if is_zip else item.isdir()


def _stream(archive, item, is_zip):
    return archive.open(item) if is_zip else archive.extractfile(item)


def test_archive(path, *, password=None, progress=lambda *args: None, cancelled=lambda: False):
    if zipfile.is_zipfile(path):
        return len(archive_manifest(path, password=password, progress=progress, cancelled=cancelled))
    count, done = 0, 0
    with reader(path) as (archive, is_zip):
        members = archive.getmembers()
        total = sum(item.size for item in members)
        for item in members:
            check_cancelled(cancelled)
            if item.isfile():
                def advanced(size):
                    nonlocal done
                    done += size
                    progress(done, total, f'Reading {item.name}')
                with archive.extractfile(item) as stream:
                    stream_signature(stream, cancelled=cancelled, progress=advanced)
            count += 1
    return count
