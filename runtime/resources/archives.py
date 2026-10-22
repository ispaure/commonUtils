"""Revision-checked local ZIP sources with bounded member reads and no extraction."""
from contextlib import contextmanager
from pathlib import Path
from zipfile import ZipFile
from ...archives.zip_access import validate_members


class BoundedArchive:
    def __init__(self, archive, source):
        self.archive, self.source = archive, source

    def infolist(self):
        return self.archive.infolist()

    def namelist(self):
        return self.archive.namelist()

    def getinfo(self, name):
        return self.archive.getinfo(name)

    def read(self, member):
        self.source.check()
        info = member if hasattr(member, 'file_size') else self.getinfo(member)
        if info.file_size > self.source.max_read:
            raise ValueError('Archive member exceeds its read buffer limit.')
        with self.archive.open(info) as stream:
            data = stream.read(self.source.max_read + 1)
        self.source.check()
        if len(data) > self.source.max_read:
            raise ValueError('Archive member exceeds its read buffer limit.')
        return data

    @contextmanager
    def open(self, member):
        self.source.check()
        with self.archive.open(member) as stream:
            yield stream
        self.source.check()


class LocalArchiveSource:
    """Seek ZIP headers on disk and allocate only explicitly requested members."""
    private = False

    def __init__(self, path, *, max_read=16 * 1024 * 1024, max_members=10000):
        if max_read <= 0 or max_members <= 0:
            raise ValueError('Invalid archive limits.')
        self.path = Path(path).absolute()
        self.max_read, self.max_members = max_read, max_members
        self.expected = self.version(self.path)

    def version(self, path):
        if Path(path).absolute() != self.path:
            raise ValueError('This source owns a different archive.')
        if self.path.is_symlink():
            raise ValueError('Linked archives are not supported.')
        info = self.path.stat()
        if not self.path.is_file() or info.st_nlink != 1:
            raise ValueError('Choose an independent regular archive.')
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns

    def check(self):
        if self.version(self.path) != self.expected:
            raise ValueError('The archive changed; reopen it.')

    def archive_password(self, path):
        return None

    @contextmanager
    def open(self, path):
        self.version(path)
        self.check()
        with self.path.open('rb') as stream:
            yield stream
        self.check()

    @contextmanager
    def open_archive(self, path, password=None):
        with self.open(path) as stream, ZipFile(stream) as archive:
            if len(archive.infolist()) > self.max_members:
                raise ValueError('Archive contains too many entries.')
            validate_members(archive)
            if any(info.flag_bits & 1 for info in archive.infolist()):
                raise ValueError('This source requires an unencrypted ZIP archive.')
            yield BoundedArchive(archive, self)
