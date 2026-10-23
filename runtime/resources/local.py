"""Rooted local resource provider; no application or encryption policy."""
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime
import os
import stat as stat_module
from .paths import resource_path
from .provider import ResourceCapabilities
from ..operations import check_cancelled
from ..streams import copy_stream
from ...persistence.publication import mutation_lock, rename_exclusive


class LocalFiles:
    """Rooted local provider; rejects links, special files and hard-linked files."""
    private = False
    capabilities = ResourceCapabilities(create=True, rename=True, delete=True, replace=True)

    def __init__(self, root):
        self.root = Path(root).absolute()
        if not self.root.is_dir():
            raise ValueError('Storage root must exist.')
        self.storage_id = str(self.root.resolve())
        self.storage_namespace = 'local'

    def relative(self, path):
        if isinstance(path, Path) and path.is_absolute():
            path = path.relative_to(self.root).as_posix()
        return resource_path(path)

    def _physical(self, path, directory=False):
        target = self.root / self.relative(path)
        from ...filesystem.local_access import check_local_path
        check_local_path(target)
        return target

    def _guard(self, path):
        path.relative_to(self.root)
        for part in (path, *path.parents):
            if part == self.root:
                break
            if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
                raise ValueError('Linked storage is not supported.')
        if path.exists():
            info = path.stat()
            if not stat_module.S_ISDIR(info.st_mode) and (not stat_module.S_ISREG(info.st_mode) or info.st_nlink != 1):
                raise ValueError('Choose an independent regular file or folder.')
        return path

    def _locate(self, path):
        file = self._guard(self._physical(path))
        folder = self._guard(self._physical(path, True))
        if file != folder and file.exists() and folder.exists():
            raise ValueError('Ambiguous file and folder names.')
        return file if file.exists() else folder

    def transfer_location(self, path, *, directory=False):
        """Physical item boundary for overlap checks, including encoded providers."""
        return self._guard(self._physical(path, directory)).resolve()

    def entry(self, path):
        path = self.relative(path)
        target = self._locate(path)
        info = target.stat()
        directory = target.is_dir()
        revision = (info.st_dev, info.st_ino) if directory else (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        hidden = (Path(path).name.startswith('.')
                  or bool(getattr(info, 'st_file_attributes', 0) & getattr(stat_module, 'FILE_ATTRIBUTE_HIDDEN', 0))
                  or bool(getattr(info, 'st_flags', 0) & getattr(stat_module, 'UF_HIDDEN', 0)))
        return dict(name=Path(path).name, path=path, directory=directory, size=info.st_size, hidden=hidden,
                    modified=datetime.fromtimestamp(info.st_mtime).astimezone().isoformat(sep=' ', timespec='seconds'), revision=revision)

    def list(self, path='', *, cancelled=lambda: False):
        path = self.relative(path)
        rows = []
        for child in self._locate(path).iterdir():
            check_cancelled(cancelled)
            rows.append(self.entry('/'.join(p for p in (path, child.name) if p)))
        return sorted(rows, key=lambda row: (not row['directory'], row['name'].casefold()))

    @contextmanager
    def open(self, path):
        with self._locate(path).open('rb') as stream:
            yield stream

    def mkdir(self, path):
        with mutation_lock:
            path = self.relative(path)
            if not path or self._locate(path).exists():
                raise FileExistsError('Destination already exists.')
            self._guard(self._physical(path, True)).mkdir(mode=0o700)

    def create_file(self, path, stream, *, cancelled=lambda: False):
        with mutation_lock:
            path = self.relative(path)
            if not path or self._locate(path).exists():
                raise FileExistsError('Destination already exists.')
            target = self._guard(self._physical(path))
            try:
                with target.open('xb') as output:
                    copy_stream(stream, output, cancelled=cancelled)
                    output.flush()
                    os.fsync(output.fileno())
            except Exception:
                # Only unlink after exclusive creation, never someone else's file.
                if 'output' in locals():
                    target.unlink(missing_ok=True)
                raise

    def rename(self, source, destination):
        with mutation_lock:
            source, destination = self.relative(source), self.relative(destination)
            if not source or not destination or destination.startswith(source + '/'):
                raise ValueError('Cannot move a storage root or a folder into itself.')
            from .mutations import inventory
            inventory(self, source)
            original = self._locate(source)
            if self._locate(destination).exists():
                raise FileExistsError('Destination already exists.')
            target = self._guard(self._physical(destination, original.is_dir()))
            rename_exclusive(original, target)

    def remove_empty(self, path, revision):
        with mutation_lock:
            if not self.relative(path):
                raise ValueError('Cannot delete a storage root.')
            row = self.entry(path)
            if row['revision'] != revision:
                raise ValueError('Source changed; refresh before deleting.')
            target = self._locate(path)
            target.rmdir() if row['directory'] else target.unlink()

    def replace_created(self, staged, path, expected_revision):
        with mutation_lock:
            row = self.entry(path)
            if row['directory'] or row['revision'] != expected_revision:
                raise ValueError('File changed; original preserved.')
            os.replace(self._locate(staged), self._locate(path))

