"""Generic filesystem information and browser contribution hooks without Qt."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable
import os
import sys


@dataclass(frozen=True)
class BrowserDetails:
    fields: tuple[tuple[str, object], ...] = ()
    thumbnail: bytes = b''
    message: str = ''
    payload: object = None


@dataclass(frozen=True)
class BrowserPanel:
    key: str
    title: str
    load: Callable[[], BrowserDetails]


@dataclass(frozen=True)
class BrowserAction:
    key: str
    title: str
    run: Callable
    source: str = 'Extensions'
    category: str = 'tools'
    order: int = 100


class FilesystemObject:
    """Common read-only information and optional browser behavior for files/folders."""
    browser_has_thumbnail = False

    @property
    def modified_time(self):
        try:
            return datetime.fromtimestamp(self.path.stat().st_mtime)
        except OSError:
            return None

    @property
    def created_time(self):
        try:
            stats = self.path.stat()
            timestamp = getattr(stats, 'st_birthtime', stats.st_ctime if sys.platform == 'win32' else None)
            return datetime.fromtimestamp(timestamp) if timestamp is not None else None
        except OSError:
            return None

    def filesystem_information(self):
        values = [('Name', getattr(self, 'file_name', self.path.name)), ('Path', str(self.path))]
        extension = getattr(self, 'ext', None)
        if extension:
            values.append(('Extension', extension))
        try:
            stats = self.path.stat()
            if hasattr(self, 'ext'):
                values.append(('Size', format_size(stats.st_size)))
            values.append(('Modified', format_datetime(datetime.fromtimestamp(stats.st_mtime))))
            created = self.created_time
            if created is not None:
                values.append(('Created', created.isoformat(sep=' ', timespec='seconds')))
            values.append(('Readable', 'Yes' if os.access(self.path, os.R_OK) else 'No'))
            if self.path.is_symlink():
                values.append(('Link target', str(self.path.resolve())))
        except OSError as error:
            values.append(('Status', str(error)))
        return tuple(values)

    def browser_panels(self):
        return ()

    def browser_actions(self, context):
        return ()

    def browser_thumbnail(self, size):
        return b''

    def browser_activate(self, context):
        return False


@dataclass
class FolderStats:
    size: int = 0
    files: int = 0
    folders: int = 0
    skipped: int = 0
    extension_counts: dict[str, int] = field(default_factory=dict)

    complete: bool = True
    scanned_at: float = 0
    stale: bool = False

    def include(self, other):
        self.size += other.size
        self.files += other.files
        self.folders += other.folders + 1
        self.skipped += other.skipped
        self.complete = self.complete and other.complete
        for extension, count in other.extension_counts.items():
            self.extension_counts[extension] = self.extension_counts.get(extension, 0) + count


def scan_folders(root, cancelled=lambda: False, *, report=lambda done, total, message: None, reuse_for=0,
                 visible_only=False):
    """Compatibility API: recursive totals from the shared persistent index."""
    from .directory_index import directory_cache
    from .operations import OperationCancelled
    try:
        snapshot = directory_cache.get(root, cancelled=cancelled, report=report, reuse_for=reuse_for)
        return snapshot.folder_stats(cancelled=cancelled, children_of=snapshot.root if visible_only else None)
    except OperationCancelled:
        return None


def format_size(size):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024 or unit == 'TB':
            return f'{size:,} B' if unit == 'B' else f'{size:.1f} {unit}'
        size /= 1024


def format_datetime(value):
    """Human-readable local date/time, independent of platform strftime flags."""
    if value is None:
        return '—'
    months = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
    return (f'{months[value.month - 1]} {value.day}, {value.year} at '
            f'{value.hour % 12 or 12}:{value.minute:02d} {"AM" if value.hour < 12 else "PM"}')
