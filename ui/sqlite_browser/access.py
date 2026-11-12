"""Conservative local-file admission for the optional Qt SQLite browser.

This is host routing policy, not a security sandbox. No provider bytes are copied
out or written back. A provider must explicitly return a SQLite-safe local path.
"""
from contextlib import closing
from pathlib import Path
import os
import sqlite3
import stat


SQLITE_SUFFIXES = frozenset({'.db', '.db3', '.sqlite', '.sqlite3'})


def is_candidate(path):
    """Cheap menu hint; SQLite validates the actual file on a worker."""
    return Path(path).suffix.lower() in SQLITE_SUFFIXES


def _managed_schema(path):
    # Recognize copied/renamed index stores too, without changing their owner.
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.25)) as db:
        names = {row[0] for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        index = {'scans', 'roots', 'folder_totals', 'folder_checks'} <= names
        jobs = {'jobs', 'priorities'} <= names
        return index or jobs


def check_access(path, *, writable=False, write_allowed=None, readonly_paths=()):
    """Recheck an independent local file and optional host policy before I/O.

    ``write_allowed(path)`` must explicitly return True; absence means browse
    only. It must be worker-safe, and may raise an actionable access error.
    ``readonly_paths`` can be a worker-safe callback for current managed paths.
    """
    from ...filesystem.local_access import check_local_path
    from ...filesystem.network import is_network_location
    requested = Path(path).absolute()
    check_local_path(requested)
    if is_network_location(requested, refresh=True):
        raise PermissionError('SQLite inspection requires an ordinary local file; network storage is unsupported.')
    for part in (requested, *requested.parents):
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise PermissionError('SQLite inspection does not follow linked files or folders.')
    info = requested.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise PermissionError('Choose an independent regular SQLite file.')
    if not os.access(requested, os.R_OK):
        raise PermissionError('The database is not readable.')
    if writable:
        protected = readonly_paths() if callable(readonly_paths) else readonly_paths
        if requested.resolve() in {Path(item).resolve() for item in protected} or _managed_schema(requested):
            raise PermissionError('Managed index and job databases are browse-only; use their owning tools to change them.')
        if write_allowed is None or write_allowed(requested) is not True:
            raise PermissionError('This host permits SQLite inspection only.')
        if not info.st_mode & 0o222 or not os.access(requested, os.W_OK) or not os.access(requested.parent, os.W_OK):
            raise PermissionError('The database and its folder must be writable for SQLite journals and locking.')
    return requested


def provider_path(provider, path, *, writable=False):
    """Use only the explicit SQLite access hook, never replace/physical_root."""
    if getattr(provider, 'private', False):
        raise PermissionError('Private resources do not support direct SQLite access.')
    access = getattr(provider, 'sqlite_local_path', None)
    result = access(path, writable=writable) if callable(access) else None
    if result is None:
        raise PermissionError('This provider does not supply SQLite-safe local access.')
    return Path(result).absolute()
