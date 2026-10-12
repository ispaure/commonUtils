"""Shared file-change detection and subscriptions, independent of Qt/host policy."""
import logging
from inspect import ismethod
from pathlib import Path
from threading import RLock
from weakref import WeakMethod


def _stamp(path):
    try:
        value = path.stat()
        return value.st_mtime_ns, value.st_ctime_ns, value.st_size, value.st_ino
    except OSError as error:
        return 'unavailable', error.errno


class SettingsMonitor:
    def __init__(self):
        self._lock = RLock()
        self._subscriptions = {}
        self._stamps = {}

    def subscribe(self, paths, callback):
        """Return an idempotent unsubscribe function; bound methods are weak."""
        if isinstance(paths, (str, Path)):
            paths = (paths,)
        paths = frozenset(Path(path).resolve() for path in paths)
        weak = WeakMethod(callback) if ismethod(callback) else None
        identity = object()
        with self._lock:
            self._subscriptions[identity] = paths, weak or callback, weak is not None
            for path in paths:
                self._stamps.setdefault(path, _stamp(path))
        def unsubscribe():
            with self._lock:
                self._subscriptions.pop(identity, None)
                active = set().union(*(entry[0] for entry in self._subscriptions.values())) if self._subscriptions else set()
                self._stamps = {path: stamp for path, stamp in self._stamps.items() if path in active}
        return unsubscribe

    def _deliver(self, paths):
        with self._lock:
            entries = list(self._subscriptions.items())
        for identity, (watched, stored, weak) in entries:
            with self._lock:
                if identity not in self._subscriptions:
                    continue
            callback = stored() if weak else stored
            if callback is None:
                with self._lock:
                    self._subscriptions.pop(identity, None)
                continue
            if paths & watched:
                try:
                    callback()
                except Exception:
                    logging.exception('Settings subscriber could not refresh')
        with self._lock:
            active = set().union(*(entry[0] for entry in self._subscriptions.values())) if self._subscriptions else set()
            self._stamps = {path: stamp for path, stamp in self._stamps.items() if path in active}

    def poll(self):
        """Detect external creation, edits, atomic replacement and deletion."""
        with self._lock:
            changed = {path for path, previous in self._stamps.items() if _stamp(path) != previous}
            for path in changed:
                self._stamps[path] = _stamp(path)
        self._deliver(changed)
        return changed

    def notify(self, paths=None):
        """Publish a completed in-app write/reset; callbacks run on this thread."""
        with self._lock:
            paths = set(self._stamps) if paths is None else {Path(path).resolve() for path in paths}
            for path in paths & self._stamps.keys():
                self._stamps[path] = _stamp(path)
        self._deliver(paths)


_monitor = SettingsMonitor()


def settings_monitor():
    return _monitor
