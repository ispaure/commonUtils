"""Atomic byte publication; format validation and overwrite policy stay with callers."""
import os
from pathlib import Path
import stat
from tempfile import NamedTemporaryFile


def atomic_write_bytes(path, content, *, validate=None, overwrite=True):
    """Validate before staging and publication, preserve mode, clean failed staging.

    No path resolution, encoding, size limit, or symlink policy is imposed here.
    overwrite=False uses an atomic hard link to avoid clobbering a racing file.
    """
    path = Path(path)
    if validate:
        validate()
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    staged = None
    try:
        with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            staged = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None:
            staged.chmod(mode)
        if validate:
            validate()
        if overwrite:
            os.replace(staged, path)
        else:
            os.link(staged, path)
        return path
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
