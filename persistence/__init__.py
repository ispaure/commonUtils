"""Atomic byte publication; format validation and overwrite policy stay with callers."""
import os
from pathlib import Path
import stat
from tempfile import NamedTemporaryFile
from uuid import uuid4


def promote_path(staged, destination):
    """Publish a staged file/tree, keeping the old path as a recovery copy.

    Stage on the destination filesystem. If promotion fails, restore the old
    path before raising. Return its recovery path, or None for a new install.
    Callers validate the staged contents before invoking this function.
    """
    staged, destination = Path(staged), Path(destination)
    source, target = staged.absolute(), destination.absolute()
    if source == target or source in target.parents or target in source.parents:
        raise ValueError('Staged and destination paths cannot overlap')
    if staged.is_symlink() or destination.is_symlink():
        raise ValueError('Refusing to replace a symbolic link')
    from ..filesystem.links import is_junction
    if is_junction(staged) or is_junction(destination):
        raise ValueError('Refusing to replace a junction')
    if not staged.exists():
        raise FileNotFoundError(staged)
    backup = None
    if destination.exists():
        backup = destination.with_name(f'{destination.name}.previous-{uuid4().hex}')
        destination.rename(backup)
    try:
        staged.rename(destination)
    except BaseException:
        if backup is not None:
            backup.rename(destination)
        raise
    return backup


def atomic_write_bytes(path, content, *, validate=None, overwrite=True):
    """Validate before staging and publication, preserve mode, clean failed staging.

    No path resolution, encoding, size limit, or symlink policy is imposed here.
    overwrite=False uses atomic no-replace publication to reject a racing file.
    """
    from .publication import save_transaction, rename_exclusive
    from ..filesystem.local_access import check_local_path
    requested_validate = validate
    def validate():
        check_local_path(path)
        if requested_validate:
            requested_validate()
    path = Path(path)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    staged = None
    def stage():
        nonlocal staged
        with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            staged = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None:
            staged.chmod(mode)
    def verify():
        if staged.read_bytes() != content:
            raise OSError('Staged content verification failed.')
    def publish():
        if overwrite:
            os.replace(staged, path)
        else:
            rename_exclusive(staged, path)
    def cleanup():
        if staged is not None:
            staged.unlink(missing_ok=True)
    save_transaction(stage=stage, verify=verify, validate=validate or (lambda: None),
                     publish=publish, cleanup=cleanup)
    return path


def atomic_write_json(path, payload, *, ensure_ascii=False, allow_nan=False,
                      max_bytes=None, durable_directory=False):
    """Serialize and publish JSON; schemas, bounds and directory policy are explicit."""
    import json
    content = json.dumps(payload, ensure_ascii=ensure_ascii, allow_nan=allow_nan).encode('utf-8')
    if max_bytes is not None and len(content) > max_bytes:
        raise ValueError(f'JSON payload exceeds {max_bytes} bytes.')
    path = atomic_write_bytes(path, content)
    if durable_directory and os.name != 'nt':
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    return path
