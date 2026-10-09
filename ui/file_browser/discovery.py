"""Search results using shared filesystem snapshots and the browser's navigation."""
from pathlib import Path
from .. import pyside as qt
from ..operation_progress import OperationProgress
from ...directory_index import directory_cache
from ...operations import OperationCancelled
from dataclasses import dataclass
from datetime import datetime
from ...filesystem import format_datetime
from ...filesystem import format_size


@dataclass
class PausedScan:
    progress: dict | None
    cancelled: bool = True


@dataclass
class SearchScan:
    snapshot: object
    matches: tuple
    total: int
    offset: int = 0


class ScanDialog(qt.QDialog):
    idle = qt.Signal()

    def __init__(self, browser, title):
        super().__init__(browser)
        self.browser = browser
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

    @property
    def busy(self):
        return self.task.busy

    def scan(self, recursive, *, refresh=False):
        if self.busy or self.closing:
            return
        root = self.root
        self._clearing = False
        self.clear_button.setEnabled(False)
        self.summary.setText('Scanning…')
        self.freshness.setText('Scan in progress; any displayed results belong to the previous snapshot.')
        def work(report, cancelled):
            try:
                return self.collect(root, recursive, refresh, report, cancelled)
            except OperationCancelled:
                return PausedScan(directory_cache.status(root, recursive))
        self.task.start(work)

    def collect(self, root, recursive, refresh, report, cancelled):
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
        if self.closing:
            self.close()
        self.idle.emit()

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


class SearchDialog(ScanDialog):
    PAGE_SIZE = 500
    def __init__(self, browser):
        super().__init__(browser, 'Search files and folders')
        controls = qt.QHBoxLayout()
        self.query = qt.QLineEdit()
        self.query.setPlaceholderText('Partial file or folder name')
        self.query.setAccessibleName('Search by name')
        self.recursive = qt.QCheckBox('Include subfolders')
        self.recursive.setChecked(True)
        self.search_button = qt.QPushButton('Search')
        self.search_button.clicked.connect(self.run_search)
        self.query.returnPressed.connect(self.run_search)
        self.rescan_button = qt.QPushButton('Rebuild index')
        self.rescan_button.setToolTip('Start over instead of resuming saved partial work')
        self.rescan_button.clicked.connect(lambda: self.run_search(refresh=True))
        for widget in (self.query, self.recursive, self.search_button, self.rescan_button):
            controls.addWidget(widget)
        self.layout.insertLayout(1, controls)
        self.results = qt.QTreeWidget()
        self.results.setHeaderLabels(['Name', 'Type', 'Size', 'Path'])
        self.results.setRootIsDecorated(False)
        self.results.setUniformRowHeights(True)
        # Sort the full match set in SQL before paging, rather than only visible rows.
        self._sort_key = 'name'
        self._descending = False
        self.results.header().setSectionsClickable(True)
        self.results.header().setSortIndicatorShown(True)
        self.results.header().setSortIndicator(0, qt.Qt.SortOrder.AscendingOrder)
        self.results.header().sortIndicatorChanged.connect(self._sort_changed)
        self.results.setColumnWidth(0, 230)
        self.results.itemActivated.connect(lambda item, column: self.locate(item.data(0, qt.Qt.ItemDataRole.UserRole)))
        self.layout.insertWidget(2, self.results, 1)
        paging = qt.QHBoxLayout()
        self.previous_button = qt.QPushButton('Previous results')
        self.next_button = qt.QPushButton('Next results')
        self.previous_button.setEnabled(False)
        self.next_button.setEnabled(False)
        self.previous_button.clicked.connect(lambda: self.change_page(-1))
        self.next_button.clicked.connect(lambda: self.change_page(1))
        paging.addStretch()
        paging.addWidget(self.previous_button)
        paging.addWidget(self.next_button)
        self.layout.insertLayout(3, paging)
        self.summary.setText('Enter a name and search. Double-click a result to show it in the browser.')

    def run_search(self, checked=False, *, refresh=False):
        if self.busy:
            return
        self.results.clear()
        self._query = self.query.text()
        self.search_button.setEnabled(False)
        self.query.setEnabled(False)
        self.recursive.setEnabled(False)
        self.previous_button.setEnabled(False)
        self.next_button.setEnabled(False)
        self.results.header().setEnabled(False)
        self.scan(self.recursive.isChecked(), refresh=refresh)

    def _completed(self, result, error):
        if isinstance(result, SearchScan):
            self._matches = result.matches
            self._match_count = result.total
            self._page_offset = result.offset
            result = result.snapshot
        self.search_button.setEnabled(True)
        self.query.setEnabled(True)
        self.recursive.setEnabled(True)
        self.results.header().setEnabled(True)
        super()._completed(result, error)
        has_page = self.snapshot is not None and self.results.topLevelItemCount() > 0
        self.previous_button.setEnabled(has_page and self._page_offset > 0)
        self.next_button.setEnabled(has_page and self._page_offset + len(self._matches) < self._match_count)

    def collect(self, root, recursive, refresh, report, cancelled):
        snapshot = directory_cache.get(root, recursive, refresh=refresh, report=report,
                                       cancelled=cancelled, validate_files=False)
        report(0, 0, 'Searching saved index…')
        matches, total = snapshot.search_page(self._query, limit=self.PAGE_SIZE, cancelled=cancelled,
                                             sort=self._sort_key, descending=self._descending)
        return SearchScan(snapshot, matches, total)

    def _sort_changed(self, column, order):
        if self.busy:
            return
        self._sort_key = ('name', 'type', 'size', 'path')[column]
        self._descending = order == qt.Qt.SortOrder.DescendingOrder
        if self.snapshot is not None and self.results.topLevelItemCount() > 0:
            self.change_page(0, reset=True)

    def change_page(self, direction, *, reset=False):
        if self.busy or self.closing or self.snapshot is None:
            return
        snapshot, query = self.snapshot, self._query
        offset = 0 if reset else max(0, self._page_offset + direction * self.PAGE_SIZE)
        sort, descending = self._sort_key, self._descending
        self._clearing = False
        for widget in (self.search_button, self.query, self.recursive, self.clear_button,
                       self.previous_button, self.next_button, self.results.header()):
            widget.setEnabled(False)
        def work(report, cancelled):
            try:
                matches, total = snapshot.search_page(query, offset, self.PAGE_SIZE, cancelled=cancelled,
                                                     sort=sort, descending=descending)
                return SearchScan(snapshot, matches, total, offset)
            except OperationCancelled:
                return PausedScan(None)
        self.task.start(work, message='Loading search results…')

    def show_snapshot(self):
        matches = self._matches
        self.results.clear()
        for entry in matches:
            row = qt.QTreeWidgetItem([entry.path.name, 'Link' if entry.symlink else 'Folder' if entry.directory else 'File',
                                     '' if entry.directory else format_size(entry.size),
                                     str(entry.path.relative_to(self.root))])
            row.setData(0, qt.Qt.ItemDataRole.UserRole, entry.path)
            row.setToolTip(0, str(entry.path))
            self.results.addTopLevelItem(row)
        shown = (f'Results {self._page_offset + 1:,}–{self._page_offset + len(matches):,} of '
                 f'{self._match_count:,} matches' if matches else '0 matches')
        self.summary.setText(f'{shown} · {len(self.snapshot.errors)} unreadable entries. '
                             'Double-click a result to show it in the browser.')
        self.summary.setToolTip('\n'.join(f'{path}: {error}' for path, error in self.snapshot.errors))
