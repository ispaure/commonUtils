"""Event sources for paths admitted by the browser index."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

import os
import select
import stat
import sys

from .. import pyside as qt


def create_macos_watcher(parent):
    if sys.platform == 'darwin':
        try:
            return _MacIndexWatcher(parent, select.kqueue())
        except OSError:
            pass
    return None


def create_index_watcher(parent):
    return create_macos_watcher(parent) or qt.QFileSystemWatcher(parent)


class _MacIndexWatcher(qt.QObject):
    """Watch open vnodes directly so FSEvents delivery cannot delay reconciliation."""

    directoryChanged = qt.Signal(str)
    fileChanged = qt.Signal(str)

    def __init__(self, parent, queue):
        super().__init__(parent)
        self._queue = queue
        self._entries = {}
        self._paths = {}
        self._notifier = qt.QSocketNotifier(queue.fileno(), qt.QSocketNotifier.Type.Read, self)
        self._notifier.activated.connect(self._deliver)
        self._fallback = qt.QFileSystemWatcher(self)
        self._fallback.directoryChanged.connect(self.directoryChanged)
        self._fallback.fileChanged.connect(self.fileChanged)
        # Capture only resource state. The QObject wrapper may already be invalid.
        entries = self._entries

        def close(*_):
            queue.close()
            for fd, _ in entries.values():
                os.close(fd)
            entries.clear()

        self.destroyed.connect(close)

    def directories(self):
        return [path for path, (_, is_directory) in self._entries.items() if is_directory] + self._fallback.directories()

    def files(self):
        return [path for path, (_, is_directory) in self._entries.items() if not is_directory] + self._fallback.files()

    def addPaths(self, paths):
        # The index already bounds this set. If the host cannot open another
        # descriptor, leave that path to Qt's ordinary watch admission.
        failed = []
        flags = (select.KQ_NOTE_DELETE | select.KQ_NOTE_EXTEND | select.KQ_NOTE_WRITE
                 | select.KQ_NOTE_ATTRIB | select.KQ_NOTE_LINK | select.KQ_NOTE_RENAME
                 | select.KQ_NOTE_REVOKE)
        for path in paths:
            fd = None
            try:
                fd = os.open(path, os.O_EVTONLY | os.O_NONBLOCK)
                is_directory = stat.S_ISDIR(os.fstat(fd).st_mode)
                event = select.kevent(fd, filter=select.KQ_FILTER_VNODE,
                                      flags=select.KQ_EV_ADD | select.KQ_EV_CLEAR, fflags=flags)
                self._queue.control([event], 0)
            except OSError:
                if fd is not None:
                    os.close(fd)
                failed.append(path)
            else:
                self._entries[path] = fd, is_directory
                self._paths[fd] = path
        return self._fallback.addPaths(failed) if failed else []

    def removePaths(self, paths):
        fallback_paths = []
        for path in paths:
            entry = self._entries.pop(path, None)
            if entry is None:
                fallback_paths.append(path)
                continue
            fd, _ = entry
            del self._paths[fd]
            os.close(fd)
        return self._fallback.removePaths(fallback_paths) if fallback_paths else []

    def _deliver(self):
        removed = select.KQ_NOTE_DELETE | select.KQ_NOTE_RENAME | select.KQ_NOTE_REVOKE
        for event in self._queue.control(None, max(1, len(self._entries)), 0):
            path = self._paths.get(event.ident)
            if path is None:
                continue
            _, is_directory = self._entries[path]
            if event.fflags & removed:
                self.removePaths([path])
            (self.directoryChanged if is_directory else self.fileChanged).emit(path)
