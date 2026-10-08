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
            values.append(('Modified', datetime.fromtimestamp(stats.st_mtime).isoformat(sep=' ', timespec='seconds')))
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

    def include(self, other):
        self.size += other.size
        self.files += other.files
        self.folders += other.folders + 1
        self.skipped += other.skipped
        for extension, count in other.extension_counts.items():
            self.extension_counts[extension] = self.extension_counts.get(extension, 0) + count


def scan_folders(root, cancelled=lambda: False):
    """Recursive totals from stat calls; no file contents, link traversal or extraction."""
    totals = {}
    children = {}
    stack = [(Path(root), False)]
    while stack:
        if cancelled():
            return None
        folder, visited = stack.pop()
        if visited:
            for child in children[folder]:
                totals[folder].include(totals[child])
            continue
        stats = totals[folder] = FolderStats()
        children[folder] = []
        stack.append((folder, True))
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    if cancelled():
                        return None
                    try:
                        if entry.is_symlink():
                            stats.skipped += 1
                        elif entry.is_dir(follow_symlinks=False):
                            child = Path(entry.path)
                            children[folder].append(child)
                            stack.append((child, False))
                        elif entry.is_file(follow_symlinks=False):
                            stats.size += entry.stat(follow_symlinks=False).st_size
                            stats.files += 1
                            extension = Path(entry.name).suffix.lower().lstrip('.')
                            stats.extension_counts[extension] = stats.extension_counts.get(extension, 0) + 1
                    except OSError:
                        stats.skipped += 1
        except OSError:
            stats.skipped += 1
    return totals


def format_size(size):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024 or unit == 'TB':
            return f'{size:,} B' if unit == 'B' else f'{size:.1f} {unit}'
        size /= 1024
