"""Verified non-overwriting directory relocation, including link target rebasing."""
import os
from pathlib import Path
import shutil
import stat
from tempfile import mkdtemp
from ..persistence.publication import rename_exclusive, serialize_mutation, save_transaction
from .snapshots import verified_file_snapshot
from ..persistence.transfers import try_rename, verify_unchanged, cleanup_published


def without_extended_prefix(value):
    if value.startswith('\\\\?\\UNC\\'):
        return '\\\\' + value[8:]
    if value.startswith('\\\\?\\') and len(value) > 5 and value[5] == ':':
        return value[4:]
    return value


def _resolved(path):
    path = Path(path).resolve(strict=False)
    return Path(without_extended_prefix(str(path))) if os.name == 'nt' else path


def _manifest(root, *, link_root=None):
    """Compare bytes and resolved link targets without following directory links."""
    result = {}
    link_root = _resolved(link_root or root)
    def visit(directory):
        for path in directory.iterdir():
            info = path.lstat()
            relative = path.relative_to(root)
            if path.is_symlink():
                target = Path(os.readlink(path))
                target = target if target.is_absolute() else path.parent / target
                target = _resolved(target)
                if target.is_relative_to(link_root):
                    result[relative] = ('internal-link', target.relative_to(link_root).as_posix())
                else:
                    result[relative] = ('link', str(target))
            elif stat.S_ISDIR(info.st_mode):
                result[relative] = ('directory',)
                visit(path)
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                result[relative] = ('file', info.st_size, verified_file_snapshot(path)[1])
            else:
                raise ValueError(f'Cannot relocate linked or special storage file: {path}')
    visit(root)
    return result


@serialize_mutation
def relocate_directory(source, destination):
    """Move once, preserving the source on conflicts or failed verification."""
    source, destination = Path(source), Path(destination)
    if source == destination or not os.path.lexists(source):
        return
    origin, target = _resolved(source), _resolved(destination)
    if origin in target.parents or target in origin.parents:
        raise ValueError('Source and destination cannot overlap.')
    if os.path.lexists(destination):
        # Never merge unknown storage trees or replace a destination copy.
        raise ValueError(f'Both storage locations exist. Preserve their contents and resolve the conflict: {source} and {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if source.is_symlink():
        target = _resolved(source)
        destination.symlink_to(target, target_is_directory=True)
        source.unlink()
        return
    if not source.is_dir():
        raise ValueError(f'Expected a storage directory: {source}')
    # Relative links would change meaning after a move. Copying rebases them to
    # their original absolute targets, including relocated crypt-copy roots.
    relative_links = any(path.is_symlink() and (not Path(os.readlink(path)).is_absolute()
                                               or _resolved(path).is_relative_to(_resolved(source)))
                         for folder, directories, files in os.walk(source, followlinks=False)
                         for path in (Path(folder) / name for name in (*directories, *files)))
    if not relative_links and try_rename(source, destination, rename=rename_exclusive):
        return
    expected = _manifest(source)
    stage = Path(mkdtemp(prefix='.directory-relocate-', dir=destination.parent))
    copied = stage / 'contents'
    try:
        def copy():
            shutil.copytree(source, copied, symlinks=True)
            for relative, description in expected.items():
                if description[0] in {'link', 'internal-link'}:
                    link = copied / relative
                    link.unlink()
                    target = _resolved(destination) / description[1] if description[0] == 'internal-link' else Path(description[1])
                    link.symlink_to(target, target_is_directory=(source / relative).is_dir())
        def validate():
            verify_unchanged(expected, lambda: _manifest(source),
                             message='Storage changed during relocation; the original was preserved.')
        def verify():
            verify_unchanged(expected, lambda: _manifest(copied, link_root=destination),
                             message='Storage changed during relocation; the original was preserved.')
        save_transaction(stage=copy, verify=verify, validate=validate,
                         publish=lambda: rename_exclusive(copied, destination), cleanup=lambda: None)
        cleanup_published(lambda: shutil.rmtree(source),
                          source_state=lambda: 'unchanged' if _manifest(source) == expected else 'partial')
    finally:
        shutil.rmtree(stage)
