"""Exclusive file publication with an explicitly non-atomic copy fallback."""

import os
import errno
import shutil
from pathlib import Path


def link_or_copy_exclusive(staged_path: Path, destination: Path):
    """Publish without overwriting, falling back when hard links are unavailable."""
    try:
        os.link(staged_path, destination)
        return
    except OSError as error:
        if error.errno not in {
            errno.EXDEV,
            errno.ENOSYS,
            errno.ENOTSUP,
            errno.EOPNOTSUPP,
            errno.EPERM,
        } and getattr(error, "winerror", None) not in (1, 50):
            raise

    owns_destination = False
    try:
        with staged_path.open("rb") as source, destination.open("xb") as output:
            owns_destination = True
            shutil.copyfileobj(source, output)
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        if owns_destination:
            destination.unlink()
        raise
