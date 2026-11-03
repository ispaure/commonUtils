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

    def list_names(self, path='', *, cancelled=lambda: False):
        """Unsorted child names/types/sizes, without timestamp or revision formatting.

        Adapted listings retain their filtering and logical namespace by using
        their existing list implementation. No document content is opened.
        """
        if (type(self).list is not LocalFiles.list or type(self)._physical is not LocalFiles._physical
                or type(self)._guard is not LocalFiles._guard or type(self).entry is not LocalFiles.entry
                or type(self)._locate is not LocalFiles._locate or type(self).relative is not LocalFiles.relative):
            return [dict(name=row['name'], path=row['path'], directory=row['directory'], size=row['size'])
                    for row in self.list(path, cancelled=cancelled)]
        path = self.relative(path)
        folder = self._locate(path)
        before = folder.stat(follow_symlinks=False)
        from ...filesystem.local_access import check_local_path
        rows = []
        with os.scandir(folder) as entries:
            for child in entries:
                check_cancelled(cancelled)
                if child.is_symlink() or (hasattr(Path, 'is_junction') and Path(child.path).is_junction()):
                    raise ValueError('Linked storage is not supported.')
                check_local_path(child.path)
                try:
                    # Windows DirEntry metadata leaves st_nlink/st_ino at zero.
                    # Query the file itself before enforcing independent-file
                    # policy; never mistake an unknown link count for a link.
                    info = (Path(child.path).stat(follow_symlinks=False) if os.name == 'nt'
                            else child.stat(follow_symlinks=False))
                except FileNotFoundError:
                    continue
                directory = stat_module.S_ISDIR(info.st_mode)
                if not directory and (not stat_module.S_ISREG(info.st_mode) or info.st_nlink != 1):
                    raise ValueError('Choose an independent regular file or folder.')
                rows.append(dict(name=child.name, path=self.relative('/'.join(p for p in (path, child.name) if p)),
                                 directory=directory, size=info.st_size))
        check_cancelled(cancelled)
        self._guard(folder)
        after = folder.stat(follow_symlinks=False)
        if (before.st_dev, before.st_ino, before.st_mode) != (after.st_dev, after.st_ino, after.st_mode):
            raise ValueError('Folder changed during listing. Try again.')
        return rows

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

    def local_move_path(self, path):
        """Opt ordinary, unmapped storage into cross-root exclusive rename.

        Providers with custom rename policy must explicitly implement this hook
        and enforce that policy when returning a guarded physical path.
        """
        if (self.private or self.storage_namespace != 'local'
                or type(self)._physical is not LocalFiles._physical
                or type(self).rename is not LocalFiles.rename):
            return None
        return self._locate(path)

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

