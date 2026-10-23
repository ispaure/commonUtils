"""Reusable ownership leases and worker-local cancellation scopes.

Providers retain credential validation, closure state and cleanup policy.
"""
from contextlib import contextmanager
from threading import RLock, local


def _never_cancelled():
    return False


class WorkerCancellation:
    """Compose nested cancellation without cancelling other reader threads."""

    def __init__(self):
        self._worker = local()

    @property
    def current(self):
        """Capture this worker's current predicate for downstream operations."""
        return getattr(self._worker, 'cancelled', _never_cancelled)

    @contextmanager
    def scope(self, cancelled):
        previous = self.current
        self._worker.cancelled = lambda: previous() or cancelled()
        try:
            yield
        finally:
            self._worker.cancelled = previous


class ResourceLeases:
    """Validate acquisitions and close a resource when its last owner releases.

    Release callbacks are thread-safe, idempotent and accept ignored UI event
    arguments. Validation and final release run under a reentrant lock. Explicit
    closure and whether a closed resource can be acquired remain provider policy.
    """

    def __init__(self, *, validate, close):
        self._validate = validate
        self._close = close
        self._lock = RLock()
        self._owners = 0

    def acquire(self):
        with self._lock:
            self._validate()
            self._owners += 1
        released = False

        def release(*_):
            nonlocal released
            with self._lock:
                if not released:
                    released = True
                    self._owners -= 1
                    if self._owners == 0:
                        self._close()

        return release
