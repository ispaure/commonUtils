"""Host-declared storage boundaries for ordinary filesystem operations.

Virtual providers own access inside these roots. This is an application routing
safeguard, not an OS sandbox; arbitrary third-party filesystem calls are unaffected.
"""
from pathlib import Path
import threading

_roots = {}
_lock = threading.RLock()


def protect_local_root(owner, root, message):
    """Register/refresh a boundary; return a callback removing this registration."""
    value = (Path(root).absolute(), message)
    with _lock:
        _roots[owner] = value
    def release():
        with _lock:
            if _roots.get(owner) is value:
                _roots.pop(owner, None)
    return release


def check_local_path(path, *, recursive=False):
    """Reject raw access inside a boundary, and recursive operations containing it."""
    with _lock:
        roots = tuple(_roots.values())
    if not roots:
        return
    requested = Path(path)
    try:
        candidate = requested.resolve()
    except RuntimeError:
        if not requested.is_symlink():
            raise
        # A looping leaf has no reachable content; its parent still determines
        # whether ordinary unlink/rename would mutate a provider-owned path.
        candidate = requested.parent.resolve() / requested.name
    if not recursive and candidate in getattr(_local, 'records', ()):
        return
    for root, message in roots:
        root = root.resolve()
        if candidate == root or root in candidate.parents or (recursive and candidate in root.parents):
            raise PermissionError(message)


# Exact destinations granted by a backend for its own records, never by a picker.
from contextlib import contextmanager
_local = threading.local()


@contextmanager
def provider_record_access(path):
    """Allow an owning backend to publish one internal record on this thread."""
    previous = getattr(_local, 'records', ())
    _local.records = (*previous, Path(path).resolve())
    try:
        yield
    finally:
        _local.records = previous
