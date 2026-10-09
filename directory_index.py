"""Reusable, cancellable directory metadata snapshots for discovery and analysis."""
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Snapshot:
    root: Path
    recursive: bool
    entries: tuple[Entry, ...]
    errors: tuple[tuple[Path, str], ...]
    scanned_at: float

    def search(self, name):
        needle = name.casefold()
        return tuple(entry for entry in self.entries if needle in entry.path.name.casefold())


def scan_metadata(root, recursive=True, *, cancelled=lambda: False,
                  report=lambda done, total, message: None):
    root = Path(root).absolute()
    if not root.is_dir():
        raise NotADirectoryError(root)
    stack, entries, errors = [root], [], []
    while stack:
        check_cancelled(cancelled)
        folder = stack.pop()
        try:
            with os.scandir(folder) as children:
                for child in children:
                    check_cancelled(cancelled)
                    path = Path(child.path)
                    try:
                        info = child.stat(follow_symlinks=False)
                        link = child.is_symlink()
                        directory = child.is_dir(follow_symlinks=False)
                        entries.append(Entry(path, directory, 0 if directory or link else info.st_size,
                                             info.st_mtime_ns, link))
                        if directory and recursive:
                            stack.append(path)
                        report(len(entries), 0, f'Scanning {folder}')
                    except OSError as error:
                        errors.append((path, str(error)))
        except OSError as error:
            errors.append((folder, str(error)))
    return Snapshot(root, recursive, tuple(sorted(entries, key=lambda item: natural_path_key(item.path))),
                    tuple(errors), time())


def storage_totals(snapshot):
    """Logical bytes by path; links excluded, directory totals calculated bottom-up."""
    totals = {snapshot.root: 0}
    for entry in snapshot.entries:
        totals[entry.path] = 0 if entry.directory or entry.symlink else entry.size
    for entry in sorted(snapshot.entries, key=lambda item: len(item.path.parts), reverse=True):
        totals[entry.path.parent] = totals.get(entry.path.parent, 0) + totals[entry.path]
    return totals
