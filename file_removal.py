"""Explicitly confirmed removal plans, with no silent permanent-delete fallback.

UI confirmations belong to the caller. Plan identity is checked again immediately
before each operation. Links are removed themselves, never followed recursively.
Cancellation stops between items; completed items cannot be rolled back here.
"""
from dataclasses import dataclass
import os
from pathlib import Path
import shutil


@dataclass(frozen=True)
class RemovalItem:
    path: Path
    identity: tuple


@dataclass(frozen=True)
class RemovalResult:
    completed: tuple = ()
    failures: tuple = ()
    cancelled: bool = False


def _identity(path):
    info = path.lstat()
    return info.st_dev, info.st_ino, info.st_mode


def removal_plan(paths):
    """Snapshot and deduplicate selections; protect filesystem/mount roots."""
    sources = tuple(dict.fromkeys(Path(path).absolute() for path in paths))
    if any(path.name in ('.', '..') for path in sources):
        raise ValueError('Delete a named file or folder, not a relative path component.')
    sources = tuple(dict.fromkeys(path.parent.resolve() / path.name for path in sources))
    for path in sources:
        if path.parent == path or (not path.is_symlink() and os.path.ismount(path)):
            raise ValueError('A drive or filesystem root cannot be deleted from the browser.')
    sources = tuple(path for path in sources if not any(
        parent != path and parent in path.parents and parent.is_dir() and not parent.is_symlink()
        for parent in sources))
    return tuple(RemovalItem(path, _identity(path)) for path in sources)


def remove_items(plan, *, trash=None, permanent=False, cancelled=lambda: False,
                 report=lambda done, total, message: None):
    """Move to system trash or explicitly delete permanently (never both).

    trash(path) must return True only on success. Its failure leaves the item in
    place and records a failure; the caller may offer a separate confirmation.
    """
    if not permanent and trash is None:
        raise ValueError('A system trash handler is required.')
    completed, failures = [], []
    for count, item in enumerate(plan):
        if cancelled():
            return RemovalResult(tuple(completed), tuple(failures), True)
        path = item.path
        report(count, len(plan), f'{"Deleting permanently" if permanent else "Moving to Trash"} · {count + 1} of {len(plan)}')
        try:
            if path.parent.resolve() / path.name != path or _identity(path) != item.identity:
                raise OSError('This item changed since confirmation. It was left untouched.')
            if path.parent == path or (not path.is_symlink() and os.path.ismount(path)):
                raise OSError('A drive or filesystem root cannot be deleted.')
            if permanent:
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            elif not trash(path):
                raise OSError('The system could not move this item to Trash/Recycle Bin. '
                              'This location may not support it, or you may lack permission.')
            completed.append(path)
        except (OSError, ValueError) as error:
            failures.append((path, str(error)))
    report(len(plan), len(plan), 'Removal finished.')
    return RemovalResult(tuple(completed), tuple(failures), False)
