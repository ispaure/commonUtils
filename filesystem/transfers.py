"""Reusable no-overwrite file/folder transfers for clipboard-style operations."""

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import shutil
from .rename import rename_path
from .snapshots import copy_content_state
from ..persistence.publication import save_transaction
from ..persistence.transfers import try_rename, verify_unchanged, cleanup_published


@dataclass(frozen=True)
class TransferResult:
    completed: tuple = ()  # (source, destination) pairs, including same-folder move no-ops
    failures: tuple = ()  # (source, error) pairs
    cancelled: bool = False


def validate_name(name):
    """Validate a single filename under the current platform's naming rules."""
    if not isinstance(name, str) or not name or name in ('.', '..'):
        raise ValueError('Enter a file or folder name.')
    if '\x00' in name or '/' in name or (os.name == 'nt' and '\\' in name):
        raise ValueError('A name cannot contain a path separator.')
    if os.name == 'nt':
        stem = name.split('.')[0].upper()
        reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
        if any(ord(char) < 32 or char in '<>:"|?*' for char in name) or name.endswith((' ', '.')) or stem in reserved:
            raise ValueError('This name is not supported by Windows.')


def _path(path):
    path = Path(path).absolute()
    return path.parent.resolve() / path.name  # Transfer the link itself, not its target.


def _exists(path):
    return path.exists() or path.is_symlink()


def _destination(source, directory):
    candidate = directory / source.name
    suffix = '' if source.is_dir() and not source.is_symlink() else source.suffix
    stem = source.name[:-len(suffix)] if suffix else source.name
    number = 1
    while _exists(candidate):
        label = ' copy' if number == 1 else f' copy {number}'
        candidate = directory / f'{stem}{label}{suffix}'
        number += 1
    return candidate


def _copy(source, target):
    if source.is_symlink():
        target.symlink_to(os.readlink(source), target_is_directory=source.is_dir())
    elif source.is_dir():
        shutil.copytree(source, target, symlinks=True)
    else:
        shutil.copy2(source, target, follow_symlinks=False)


def _snapshot(source):
    def stamp(path):
        info = path.lstat()
        return info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns
    def unreadable(error):
        raise error
    result = {'.': stamp(source)}
    if source.is_dir() and not source.is_symlink():
        for folder, directories, files in os.walk(source, followlinks=False, onerror=unreadable):
            for name in directories + files:
                path = Path(folder) / name
                result[str(path.relative_to(source))] = stamp(path)
    return result


def transfer_paths(paths, directory, *, move=False, cancelled=lambda: False, report=lambda done, total, message: None):
    """Copy/move a selection without overwriting; collisions get numbered copy names.

    Descendants of selected folders are included once. Cancellation stops between
    items. Each copy is staged before exclusive publication; cross-volume moves
    verify unchanged sources before publishing and removing the originals.
    """
    from .local_access import check_local_path
    check_local_path(directory)
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise NotADirectoryError(directory)
    sources = tuple(dict.fromkeys(_path(path) for path in paths))
    sources = tuple(source for source in sources if not any(
        parent != source and parent in source.parents and parent.is_dir() and not parent.is_symlink()
        for parent in sources))
    completed, failures = [], []
    for count, source in enumerate(sources):
        if cancelled():
            return TransferResult(tuple(completed), tuple(failures), True)
        report(count, len(sources), f'{"Moving" if move else "Copying"} {source.name}…')
        try:
            check_local_path(source, recursive=True)
            source.lstat()
            if source.is_dir() and not source.is_symlink() and (directory == source or source in directory.parents):
                raise ValueError('A folder cannot be pasted into itself or one of its subfolders.')
            if move and source.parent.samefile(directory):
                completed.append((source, source))
                continue
            target = _destination(source, directory)
            if move and try_rename(source, target, rename=rename_path):
                completed.append((source, target))
                continue
            before = _snapshot(source) if move else None
            expected = copy_content_state(source) if move else None
            with TemporaryDirectory(dir=directory, prefix='.file-transfer-') as temporary:
                staged = Path(temporary) / 'item'
                def validate():
                    if move:
                        verify_unchanged(before, lambda: _snapshot(source), error=RuntimeError,
                                         message='The source changed during copying; it has been kept in place.')
                def verify():
                    if move:
                        verify_unchanged(expected, lambda: copy_content_state(staged), error=RuntimeError,
                                         message='Copied content verification failed; source preserved.')
                save_transaction(stage=lambda: _copy(source, staged), verify=verify,
                                 validate=validate, publish=lambda: rename_path(staged, target),
                                 cleanup=lambda: None)
            if move:
                def remove():
                    validate()
                    if source.is_dir() and not source.is_symlink():
                        shutil.rmtree(source)
                    else:
                        source.unlink()
                cleanup_published(remove, source_state=lambda: 'unchanged' if _snapshot(source) == before else 'partial')
            completed.append((source, target))
        except Exception as error:
            failures.append((source, str(error)))
        report(count + 1, len(sources), f'Processed {source.name}')
    return TransferResult(tuple(completed), tuple(failures))
