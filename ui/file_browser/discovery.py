"""Shared scan-dialog lifecycle for storage snapshots."""
from pathlib import Path
from .. import pyside as qt
from ..operation_progress import OperationProgress
from ...directory_index import directory_cache, Snapshot
from time import time
from ...operations import OperationCancelled
from dataclasses import dataclass
from datetime import datetime
from ...filesystem import format_datetime


@dataclass
class PausedScan:
    progress: dict | None
    cancelled: bool = True


class ScanDialog(qt.QDialog):
    idle = qt.Signal()

    def __init__(self, browser, title):
        super().__init__(browser)
        self.browser = browser
        self.shared_index = hasattr(browser, 'index_updated')
        self._reload_pending = False
        self.root = browser.navigation.directory
        self.setWindowTitle(title)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(850, 600)
        self.closing = False
        self.snapshot = None
        self._clearing = False
        self.layout = qt.QVBoxLayout(self)
        self.location = qt.QLabel(str(self.root))
        self.location.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.location.setWordWrap(True)
        self.layout.addWidget(self.location)
        self.task = OperationProgress(self)
        self.task.completed.connect(self._completed)
        self.summary = qt.QLabel()
        self.summary.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        self.layout.addWidget(self.summary)
        self.freshness = qt.QLabel('No snapshot collected yet.')
        self.freshness.setWordWrap(True)
        self.freshness.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.layout.addWidget(self.freshness)
        self.freshness.setToolTip(f'Persistent index: {directory_cache.database}')
        self.clear_button = qt.QPushButton('Clear saved index…')
        self.clear_button.clicked.connect(self.clear_index)
        self.layout.addWidget(self.clear_button)
        self.layout.addWidget(self.task)
        if self.shared_index:
            self.clear_button.hide()
            self.index_status = qt.QLabel(browser.index_status.text())
            self.index_status.setWordWrap(True)
            self.index_status.setTextFormat(qt.Qt.TextFormat.PlainText)
            self.layout.insertWidget(1, self.index_status)
            browser.index_progress.connect(self._index_progress_changed)
            browser.index_updated.connect(self._index_changed)

    def _index_progress_changed(self, message):
        self.index_status.setText(message if self.browser.navigation.directory == self.root else
                                  'Cached view of this folder. The browser is indexing another location.')

    def _index_changed(self, root):
        if self.closing or root != self.root: return
        if self.busy:
            self._reload_pending = True
        elif hasattr(self, 'query'):
            if self.query.text(): self.run_search()
        else:
            self.scan(True)

    @property
    def busy(self):
        return self.task.busy

    def scan(self, recursive, *, refresh=False):
        if self.busy or self.closing:
            return
        root = self.root
        self._clearing = False
        self.clear_button.setEnabled(False)
        self.summary.setText('Loading cached index…' if self.shared_index and not refresh else 'Scanning…')
        self.freshness.setText('Scan in progress; any displayed results belong to the previous snapshot.')
        def work(report, cancelled):
            try:
                return self.collect(root, recursive, refresh, report, cancelled)
            except OperationCancelled:
                return PausedScan(directory_cache.status(root, recursive))
        self.task.start(work, show_progress=not self.shared_index)

    def collect(self, root, recursive, refresh, report, cancelled):
        if self.shared_index and not refresh:
            return directory_cache.peek(root, recursive, cancelled=cancelled) or Snapshot(
                root, recursive, (), (), time(), complete=False, metadata_checked=False)
        return directory_cache.get(root, recursive, refresh=refresh, report=report, cancelled=cancelled)

    def clear_index(self):
        if self.busy or self.closing:
            return
        answer = qt.QMessageBox.question(self, 'Clear saved index',
            'Remove completed and partial indices for this folder? Your files are unchanged. '
            'The next search or analysis starts a new scan.')
        if answer != qt.QMessageBox.StandardButton.Yes:
            return
        self._clearing = True
        self.clear_button.setEnabled(False)
        def work(report, cancelled):
            try:
                directory_cache.clear(self.root, cancelled=cancelled)
            except OperationCancelled:
                return PausedScan(None)
        self.task.start(work, message='Clearing saved index…')

    def _completed(self, result, error):
        self.clear_button.setEnabled(True)
        if not self.closing:
            if isinstance(result, PausedScan):
                saved = result.progress
                if saved:
                    self.summary.setText(f'Scan paused. {saved["entries"]:,} entries saved; '
                                         f'{saved["folders_done"]:,} folders completed. Run again to resume.')
                    self.freshness.setText('Partial index saved on disk. It will be checked for changes before resuming.')
                else:
                    self.summary.setText('Cancelled. Any previously completed index is still available.')
                    self.freshness.setText('No partial scan to resume.')
            elif error:
                self.summary.setText(f'Scan stopped: {error}')
                self.freshness.setText('Scan did not complete; any displayed results belong to the previous snapshot.')
            elif self._clearing:
                self.snapshot = None
                self.results.clear()
                if hasattr(self, 'map'):
                    self.map.set_items([])
                    self.totals = {}
                self.summary.setText('Saved index cleared. Run again to start a new scan.')
                self.freshness.setText('No saved index for this folder.')
            else:
                self.snapshot = result
                self.show_snapshot()
                stamp = format_datetime(datetime.fromtimestamp(result.scanned_at))
                state = (' Saved names checked against folders; sizes are from the scan timestamp.'
                         if result.reused and not result.metadata_checked else
                         ' Saved index checked before reuse.' if result.reused else
                         ' Resumed index completed.' if result.resumed and result.complete else
                         ' Index saved on disk.' if result.complete else
                         ' Partial index: unreadable or changing folders remain. Run again to retry.')
                self.freshness.setText(f'Snapshot scanned {stamp}.' + state)
                if self.shared_index:
                    self.freshness.setText(f'Cached snapshot from {stamp}. Updates follow the browser’s shared index.')
        if self.closing:
            self.close()
        self.idle.emit()
        if self._reload_pending and not self.closing:
            self._reload_pending = False
            qt.QTimer.singleShot(0, lambda: self._index_changed(self.root))

    def show_snapshot(self):
        raise NotImplementedError

    def locate(self, path):
        path = Path(path)
        if not path.exists():
            self.summary.setText('This result no longer exists. Refresh the scan.')
            return
        self.browser.navigate(path if path.is_dir() else path.parent)
        if not path.is_dir():
            index = self.browser.model.index(str(path))
            self.browser.views.select_source(index)
        self.browser.window().raise_()

    def prepare_close(self):
        self.closing = True
        self.task.request_cancel()
        return not self.busy

    def closeEvent(self, event):
        if self.prepare_close():
            event.accept()
        else:
            event.ignore()

    def reject(self):
        self.close()
