"""Reusable, cancellable directory metadata snapshots for discovery and analysis."""
from dataclasses import dataclass, replace
from collections import OrderedDict
from threading import RLock
from pathlib import Path
import os
from time import time
from .operations import check_cancelled
from .traversal import natural_path_key


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
    entries: tuple[Entry, ...]
    errors: tuple[tuple[Path, str], ...]
    scanned_at: float
    directories: tuple = ()
    reused: bool = False
    validated_at: float = 0

    def search(self, name):
        needle = name.casefold()
        return tuple(entry for entry in self.entries if needle in entry.path.name.casefold())


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
                        link = child.is_symlink()
                        directory = child.is_dir(follow_symlinks=False)
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


def storage_totals(snapshot):
    """Logical bytes by path; links excluded, directory totals calculated bottom-up."""
    totals = {snapshot.root: 0}
    for entry in snapshot.entries:
        totals[entry.path] = 0 if entry.directory or entry.symlink else entry.size
    for entry in sorted(snapshot.entries, key=lambda item: len(item.path.parts), reverse=True):
        totals[entry.path.parent] = totals.get(entry.path.parent, 0) + totals[entry.path]
    return totals


def fingerprint(info):
    return info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns


class DirectoryCache:
    """Bounded shared snapshots validated by stat, without enumerating unchanged folders.

    File identities catch in-place writes; directory identities catch membership
    changes. Partial/error snapshots are never cached. Explicit refresh bypasses reuse.
    """
    def __init__(self, max_snapshots=8, max_entries=200_000):
        self.max_snapshots = max_snapshots
        self.max_entries = max_entries
        self._snapshots = OrderedDict()
        self._lock = RLock()
        self._revision = 0

    def invalidate(self, root=None):
        root = Path(root).absolute() if root is not None else None
        with self._lock:
            self._revision += 1
            for key in list(self._snapshots):
                path, recursive = key
                if root is None or path == root or path in root.parents or root in path.parents:
                    del self._snapshots[key]

    def _valid(self, snapshot, cancelled, report):
        checks = list(snapshot.directories) + [(entry.path, entry.identity) for entry in snapshot.entries]
        for index, (path, expected) in enumerate(checks):
            check_cancelled(cancelled)
            try:
                if fingerprint(path.lstat()) != expected:
                    return False
            except OSError:
                return False
            report(index + 1, len(checks), 'Checking cached metadata…')
        return True

    def get(self, root, recursive=True, *, refresh=False, cancelled=lambda: False,
            report=lambda done, total, message: None):
        root = Path(root).absolute()
        key = (root, recursive)
        with self._lock:
            revision = self._revision
            cached = self._snapshots.get(key)
            if cached is None and not recursive:
                cached = self._snapshots.get((root, True))
        if not refresh and cached and self._valid(cached, cancelled, report):
            with self._lock:
                if revision == self._revision:
                    cached_key = (cached.root, cached.recursive)
                    if cached_key in self._snapshots:
                        self._snapshots.move_to_end(cached_key)
                    if not recursive and cached.recursive:
                        cached = replace(cached, recursive=False,
                                         entries=tuple(entry for entry in cached.entries if entry.path.parent == root))
                    return replace(cached, reused=True, validated_at=time())
        snapshot = scan_metadata(root, recursive, cancelled=cancelled, report=report)
        # Also catch changes made while scanning; such snapshots remain explicitly
        # timestamped but must not become reusable cached data.
        if not snapshot.errors and len(snapshot.entries) <= self.max_entries and self._valid(snapshot, cancelled, report):
            with self._lock:
                if revision == self._revision:
                    self._snapshots[key] = snapshot
                    self._snapshots.move_to_end(key)
                    while (len(self._snapshots) > self.max_snapshots or
                           sum(len(value.entries) for value in self._snapshots.values()) > self.max_entries):
                        self._snapshots.popitem(last=False)
        return snapshot


directory_cache = DirectoryCache()
