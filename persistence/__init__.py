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
