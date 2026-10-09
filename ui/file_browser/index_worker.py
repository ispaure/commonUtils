"""Worker snapshots keep database reads and aggregate loading off the GUI thread."""
from time import monotonic
from ..operations import Operation
from .. import pyside as qt
from ...directory_index import directory_cache


class FolderOperation(Operation):
    updated = qt.Signal(object, object)

    def __init__(self, root, scanner, parent):
        self.root = root
        self._last_update = 0
        super().__init__(lambda: self._collect(scanner), parent)

    def _collect(self, scanner):
        self._cached(force=True)
        return scanner(self.root, self.isInterruptionRequested, report=self._report)

    def _report(self, done, total, message):
        if message == 'Saved progressive folder totals':
            self._cached(force=True)

    def _cached(self, *, force=False):
        if self.isInterruptionRequested() or not force and monotonic() - self._last_update < 1:
            return
        snapshot = directory_cache.peek(self.root, cancelled=self.isInterruptionRequested)
        if snapshot is not None:
            totals = snapshot.folder_stats(cancelled=self.isInterruptionRequested)
            self.updated.emit(self.root, totals)
        self._last_update = monotonic()
