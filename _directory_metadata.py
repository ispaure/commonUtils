"""Reusable, cancellable directory metadata snapshots for discovery and analysis."""
from dataclasses import dataclass
from collections.abc import Sequence
from pathlib import Path
import os
from time import time
from .operations import check_cancelled
from .traversal import natural_path_key
from ._directory_search import search_terms, matches_name


@dataclass(frozen=True)
class Entry:
    path: Path
    directory: bool
    size: int
    modified_ns: int
    symlink: bool = False
    identity: tuple = ()


@dataclass(frozen=True)
class Snapshot:
    root: Path
    recursive: bool
    entries: Sequence[Entry]
    errors: tuple[tuple[Path, str], ...]
    scanned_at: float
    directories: Sequence = ()
    reused: bool = False
    validated_at: float = 0
    resumed: bool = False
    complete: bool = True
    metadata_checked: bool = True

    def folder_stats(self, paths=None, *, cancelled=lambda: False, children_of=None):
        """Persisted aggregates; requested paths keep browser updates bounded."""
        if hasattr(self.entries, 'folder_stats'):
            options = {'children_of': children_of} if children_of is not None else {}
            return self.entries.folder_stats(paths, cancelled=cancelled, stale=not self.metadata_checked, **options)
        if children_of is not None and paths is not None:
            raise ValueError('Choose explicit paths or immediate child folders')
        # Standalone metadata snapshots retain their public API without a database.
        from .filesystem import FolderStats
        stats = {self.root: FolderStats(complete=self.complete, scanned_at=self.scanned_at)}
        ordered = sorted(self.entries, key=lambda entry: len(entry.path.parts), reverse=True)
        for entry in ordered:
            check_cancelled(cancelled)
            parent = stats.setdefault(entry.path.parent, FolderStats(complete=self.complete, scanned_at=self.scanned_at))
            if entry.symlink:
                parent.skipped += 1
            elif entry.directory:
                parent.include(stats.setdefault(entry.path, FolderStats(complete=self.complete, scanned_at=self.scanned_at)))
            else:
                parent.size += entry.size; parent.files += 1
                ext = entry.path.suffix.lower().lstrip('.')
                parent.extension_counts[ext] = parent.extension_counts.get(ext, 0) + 1
        if children_of is not None:
            return {path: value for path, value in stats.items()
                    if path == children_of or path.parent == children_of}
        return stats if paths is None else {path: stats[path] for path in paths if path in stats}

    def search(self, name, *, cancelled=lambda: False):
        if hasattr(self.entries, "search"):
            return self.entries.search(name, cancelled=cancelled)
        terms = search_terms(name)
        matches = []
        for entry in self.entries:
            check_cancelled(cancelled)
            if matches_name(entry.path.name, terms):
                matches.append(entry)
        return tuple(matches)

    def storage_children(self, path, limit, *, cancelled=lambda: False):
        if hasattr(self.entries, 'storage_children'):
            return self.entries.storage_children(path, limit, cancelled=cancelled)
        totals = self.folder_stats(cancelled=cancelled)
        items = [(entry.path, entry.directory, totals[entry.path].size if entry.directory and entry.path in totals else entry.size)
                 for entry in self.children(path) if not entry.symlink]
        check_cancelled(cancelled)
        return tuple(sorted(items, key=lambda item: (-item[2], item[0].name.casefold()))[:limit])

    def search_page(self, name, offset=0, limit=500, *, cancelled=lambda: False, sort='path', descending=False):
        if offset < 0 or limit < 1:
            raise ValueError('Search page requires a nonnegative offset and positive limit')
        if hasattr(self.entries, 'search_page'):
            return self.entries.search_page(name, offset, limit, cancelled=cancelled, sort=sort, descending=descending)
        matches = self.search(name, cancelled=cancelled)
        keys = {'path': lambda entry: natural_path_key(entry.path), 'name': lambda entry: entry.path.name.casefold(),
                'size': lambda entry: entry.size, 'type': lambda entry: 2 if entry.symlink else 1 if entry.directory else 0}
        if sort not in keys:
            raise ValueError(f'Unsupported search sort {sort}')
        matches = sorted(matches, key=keys[sort], reverse=descending)
        return tuple(matches[offset:offset + limit]), len(matches)

    def children(self, path, limit=None):
        if hasattr(self.entries, 'children'):
            return self.entries.children(path, limit=limit)
        return tuple(entry for entry in self.entries if entry.path.parent == path)[:limit]

    def entry(self, path):
        if hasattr(self.entries, 'get'):
            return self.entries.get(path)
        return next((entry for entry in self.entries if entry.path == path), None)


def scan_metadata(root, recursive=True, *, cancelled=lambda: False,
                  report=lambda done, total, message: None):
    root = Path(root).absolute()
    if not root.is_dir():
        raise NotADirectoryError(root)
    stack, entries, errors, directories = [root], [], [], []
    while stack:
        check_cancelled(cancelled)
        folder = stack.pop()
        try:
            before = folder.lstat()
            if folder != root and folder.is_symlink():
                raise OSError('Directory became a symbolic link during scanning')
            directories.append((folder, fingerprint(before)))
            with os.scandir(folder) as children:
                for child in children:
                    check_cancelled(cancelled)
                    path = Path(child.path)
                    try:
                        info = child.stat(follow_symlinks=False)
                        link = child.is_symlink() or path.is_junction()
                        directory = not link and child.is_dir(follow_symlinks=False)
                        entries.append(Entry(path, directory, 0 if directory or link else info.st_size,
                                             info.st_mtime_ns, link, fingerprint(info)))
                        if directory and recursive:
                            stack.append(path)
                        report(len(entries), 0, f'Scanning {folder}')
                    except OSError as error:
                        errors.append((path, str(error)))
        except OSError as error:
            errors.append((folder, str(error)))
    return Snapshot(root, recursive, tuple(sorted(entries, key=lambda item: natural_path_key(item.path))),
                    tuple(errors), time(), tuple(directories))


def storage_totals(snapshot, *, cancelled=lambda: False):
    """Logical bytes by path; links excluded, directory totals calculated bottom-up."""
    totals = {snapshot.root: 0}
    for entry in snapshot.entries:
        check_cancelled(cancelled)
        totals[entry.path] = 0 if entry.directory or entry.symlink else entry.size
    if hasattr(snapshot.entries, 'folder_stats'):
        aggregates = snapshot.folder_stats(cancelled=cancelled)
        if snapshot.root in aggregates:
            totals.update({path: value.size for path, value in aggregates.items()})
            return totals
    ordered = snapshot.entries.by_depth() if hasattr(snapshot.entries, 'by_depth') else sorted(
        snapshot.entries, key=lambda item: len(item.path.parts), reverse=True)
    for entry in ordered:
        check_cancelled(cancelled)
        totals[entry.path.parent] = totals.get(entry.path.parent, 0) + totals[entry.path]
    return totals


def fingerprint(info):
    return info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns
