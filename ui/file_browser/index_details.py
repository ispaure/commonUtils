"""On-demand, bounded diagnostics; paths appear only in this explicit dialog."""
from .. import pyside as qt
from ..operations import Operation


class IndexDetailsDialog(qt.QDialog):
    def __init__(self, browser):
        super().__init__(browser)
        from ...directory_index import directory_cache
        self.setWindowTitle('Index details')
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(900, 420)
        root = self.root = browser.navigation.directory
        layout = qt.QVBoxLayout(self)
        self.summary = qt.QLabel('Loading saved diagnostics…')
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(qt.Qt.TextFormat.PlainText)
        layout.addWidget(self.summary)
        scope = qt.QLabel(str(root))
        scope.setTextFormat(qt.Qt.TextFormat.PlainText)
        scope.setTextInteractionFlags(qt.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(scope)
        self.results = qt.QTreeWidget()
        self.results.setHeaderLabels(['State', 'Path within this folder', 'Reason'])
        self.results.setRootIsDecorated(False)
        self.results.setUniformRowHeights(True)
        self.results.setColumnWidth(0, 140)
        self.results.setColumnWidth(1, 340)
        layout.addWidget(self.results)
        hint = qt.QLabel('Saved entries remain searchable. Failed folders are skipped automatically; Refresh index retries them. '
                        'Permission errors may need access to the affected folder first.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        close = qt.QPushButton('Close')
        close.clicked.connect(self.close)
        layout.addWidget(close, alignment=qt.Qt.AlignmentFlag.AlignRight)
        self.operation = Operation(lambda: directory_cache.index_issues(
            root, cancelled=self.operation.isInterruptionRequested), self)
        self.operation.completed.connect(self._loaded)
        self.operation.start()

    def _loaded(self, report, error):
        if error:
            self.summary.setText('Saved diagnostics unavailable. Try opening Index details again.')
            return
        total = report['total']
        counts = ' · '.join(f'{count:,} {kind.lower()}' for kind, count in report['counts'].items())
        self.summary.setText(
            f'{total:,} recorded issues · {counts} · Showing {len(report["rows"]):,} of {total:,}' if total else
            'No recorded issues in this folder. The wider index may still have unfinished work.'
            if report['partial'] else 'No recorded issues in this folder.')
        for path, kind, reason in report['rows']:
            relative = path.relative_to(self.root)
            item = qt.QTreeWidgetItem([kind, 'This folder' if path == self.root else str(relative), reason])
            item.setData(1, qt.Qt.ItemDataRole.UserRole, path)
            item.setToolTip(1, str(path)); item.setToolTip(2, reason)
            self.results.addTopLevelItem(item)
        header = self.results.header()
        header.setSectionResizeMode(0, qt.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, qt.QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, qt.QHeaderView.ResizeMode.Stretch)
        self.results.setColumnWidth(1, 300)

    def closeEvent(self, event):
        self.operation.requestInterruption()
        self.operation.wait()
        super().closeEvent(event)
