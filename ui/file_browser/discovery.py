"""Search results using shared filesystem snapshots and the browser's navigation."""
from pathlib import Path
from .. import pyside as qt
from ..operation_progress import OperationProgress
from ...directory_index import directory_cache
from datetime import datetime
from ...filesystem import format_datetime
from ...filesystem import format_size


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
        self.layout.addWidget(self.task)

    @property
    def busy(self):
        return self.task.busy

    def scan(self, recursive, *, refresh=False):
        if self.busy or self.closing:
            return
        root = self.root
        self.summary.setText('Scanning…')
        self.freshness.setText('Scan in progress; any displayed results belong to the previous snapshot.')
        self.task.start(lambda report, cancelled: directory_cache.get(root, recursive, refresh=refresh, report=report, cancelled=cancelled))

    def _completed(self, result, error):
        if not self.closing:
            if error:
                self.summary.setText(f'Scan stopped: {error}')
                self.freshness.setText('Scan did not complete; any displayed results belong to the previous snapshot.')
            else:
                self.snapshot = result
                self.show_snapshot()
                stamp = format_datetime(datetime.fromtimestamp(result.scanned_at))
                self.freshness.setText(f'Snapshot scanned {stamp}.' +
                                     (' Cached metadata checked before reuse.' if result.reused else ' Fresh scan.'))
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
        self.rescan_button = qt.QPushButton('Rescan')
        self.rescan_button.clicked.connect(lambda: self.run_search(refresh=True))
        for widget in (self.query, self.recursive, self.search_button, self.rescan_button):
            controls.addWidget(widget)
        self.layout.insertLayout(1, controls)
        self.results = qt.QTreeWidget()
        self.results.setHeaderLabels(['Name', 'Type', 'Size', 'Path'])
        self.results.setRootIsDecorated(False)
        self.results.setUniformRowHeights(True)
        self.results.setSortingEnabled(True)
        self.results.setColumnWidth(0, 230)
        self.results.itemActivated.connect(lambda item, column: self.locate(item.data(0, qt.Qt.ItemDataRole.UserRole)))
        self.layout.insertWidget(2, self.results, 1)
        self.summary.setText('Enter a name and search. Double-click a result to show it in the browser.')

    def run_search(self, checked=False, *, refresh=False):
        if self.busy:
            return
        self.results.clear()
        self._query = self.query.text()
        self.search_button.setEnabled(False)
        self.query.setEnabled(False)
        self.recursive.setEnabled(False)
        self.scan(self.recursive.isChecked(), refresh=refresh)

    def _completed(self, result, error):
        self.search_button.setEnabled(True)
        self.query.setEnabled(True)
        self.recursive.setEnabled(True)
        super()._completed(result, error)

    def show_snapshot(self):
        matches = self.snapshot.search(self._query)
        for entry in matches:
            row = qt.QTreeWidgetItem([entry.path.name, 'Link' if entry.symlink else 'Folder' if entry.directory else 'File',
                                     '' if entry.directory else format_size(entry.size),
                                     str(entry.path.relative_to(self.root))])
            row.setData(0, qt.Qt.ItemDataRole.UserRole, entry.path)
            row.setToolTip(0, str(entry.path))
            self.results.addTopLevelItem(row)
        self.summary.setText(f'{len(matches)} matches · {len(self.snapshot.errors)} unreadable entries. '
                             'Double-click a result to show it in the browser.')
        if self.snapshot.errors:
            self.summary.setToolTip('\n'.join(f'{path}: {error}' for path, error in self.snapshot.errors))
