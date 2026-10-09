"""Paged recursive name search from cached SQLite data; never scans on a query."""
from pathlib import Path
from .. import pyside as qt
from ..operations import Operation
from ...directory_index import directory_cache
from ...filesystem import format_size
from .search_columns import configure_search_columns, describe_search_row


class IndexSearch(qt.QWidget):
    idle = qt.Signal()
    page_size = 500

    def __init__(self, browser):
        super().__init__(browser)
        self.browser = browser
        self.busy = False
        self.closing = False
        self.pending = False
        self.operation = None
        self.offset = 0
        self.total = 0
        self.sort = 'path'
        self.descending = False
        self.scope = None
        self._revision = 0
        self._loading = False
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.summary = qt.QLabel('Search the cached index, including descendants.')
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(qt.Qt.TextFormat.PlainText)
        layout.addWidget(self.summary)
        self.results = qt.QTreeWidget()
        self.results.setHeaderLabels(['Name', 'Type', 'Size', 'Path'])
        self.results.setRootIsDecorated(False)
        self.results.setUniformRowHeights(True)
        self.results.setSelectionMode(qt.QAbstractItemView.SelectionMode.ExtendedSelection)
        configure_search_columns(self.results)
        self.results.header().setSectionsClickable(True)
        self.results.header().sectionClicked.connect(self._sort_changed)
        self.results.itemSelectionChanged.connect(self._selection_changed)
        self.results.itemActivated.connect(self._activate)
        self.results.setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)
        self.results.customContextMenuRequested.connect(self._context_menu)
        layout.addWidget(self.results, 1)
        controls = qt.QHBoxLayout()
        self.previous = qt.QPushButton('Previous')
        self.next = qt.QPushButton('Next')
        self.locate_button = qt.QPushButton('Show in browser')
        self.previous.setEnabled(False); self.next.setEnabled(False)
        self.previous.clicked.connect(lambda: self._page(-1))
        self.next.clicked.connect(lambda: self._page(1))
        self.locate_button.clicked.connect(self._locate_selected)
        for button in (self.previous, self.next, self.locate_button): controls.addWidget(button)
        controls.addStretch()
        layout.addLayout(controls)
        self.debounce = qt.QTimer(self)
        self.debounce.setSingleShot(True); self.debounce.setInterval(180)
        self.debounce.timeout.connect(self.refresh)
        self.progress_poll = qt.QTimer(self)
        self.progress_poll.setInterval(1200)
        self.progress_poll.timeout.connect(self._poll)
        self.progress_poll.start()
        self.browser.search_bar.textChanged.connect(self._query_changed)

    @property
    def active(self):
        return bool(self.browser.search_bar.text().strip())

    def selected_paths(self):
        return tuple(row.data(0, qt.Qt.ItemDataRole.UserRole) for row in self.results.selectedItems())

    def scope_changed(self, path):
        if path != self.scope:
            self.scope = path
            self.browser.search_bar.setPlaceholderText(f'Search {path.name or path} and its subfolders')
            if self.active:
                self._query_changed(self.browser.search_bar.text())

    def _query_changed(self, text):
        self._revision += 1
        self.offset = 0
        self.pending = self.active
        if self.busy: self.operation.requestInterruption()
        switched = (self.browser.list_stack.currentWidget() is self) != self.active
        self.browser.list_stack.setCurrentWidget(self if self.active else self.browser.views)
        if self.active:
            self.summary.setText('Searching cached names…')
            self.debounce.start()
            if switched:
                self.browser._selection_changed()
        else:
            self.debounce.stop()
            self.results.clear()
            self.browser._selection_changed()

    def _poll(self):
        if self.active and self.browser.folder_busy and not self.busy and not self.closing:
            self.refresh()

    def refresh(self):
        if not self.active or self.closing or self.browser.stopping:
            return
        if self.busy:
            self.pending = True
            return
        root = self.browser.navigation.directory
        if root is None: return
        query = self.browser.search_bar.text().strip()
        offset, sort, descending, revision = self.offset, self.sort, self.descending, self._revision
        self.busy = True; self.pending = False
        self.operation = Operation(lambda: self._query(root, query, offset, sort, descending), self)
        self.operation.completed.connect(lambda result, error: self._loaded(result, error, revision))
        self.operation.finished.connect(self._finished)
        self.operation.start()

    def _query(self, root, query, offset, sort, descending):
        cancelled = self.operation.isInterruptionRequested
        snapshot = directory_cache.peek(root, cancelled=cancelled)
        if snapshot is None: return (), 0, False, 0
        matches, total = snapshot.search_page(query, offset, self.page_size, sort=sort,
                                              descending=descending, cancelled=cancelled)
        return matches, total, snapshot.complete, snapshot.scanned_at

    def _loaded(self, result, error, revision):
        if self.closing or revision != self._revision or not self.active: return
        if error:
            self.summary.setText(f'Cached search unavailable: {error}'); return
        matches, self.total, complete, stamp = result
        selected = set(self.selected_paths())
        self._loading = True
        with qt.QSignalBlocker(self.results):
            self.results.clear()
            for entry in matches:
                row = qt.QTreeWidgetItem([entry.path.name, 'Link' if entry.symlink else 'Folder' if entry.directory else
                                         entry.path.suffix.lstrip('.') or 'File',
                                         '' if entry.directory else format_size(entry.size), str(entry.path)])
                row.setData(0, qt.Qt.ItemDataRole.UserRole, entry.path)
                describe_search_row(row, self.results)
                self.results.addTopLevelItem(row)
                if entry.path in selected: row.setSelected(True)
        self._loading = False
        begin = self.offset + 1 if matches else 0
        end = self.offset + len(matches)
        state = (' · indexing, results incomplete' if self.browser.folder_busy else
                 ' · cached results; background indexing paused' if not self.browser.calculate_folder_sizes else
                 ' · cached index incomplete; Refresh to retry' if not complete else ' · cached index')
        self.summary.setText(f'{begin:,}–{end:,} of {self.total:,} matching files and folders{state}')
        self.previous.setEnabled(self.offset > 0)
        self.next.setEnabled(end < self.total)
        if selected != set(self.selected_paths()): self.browser._selection_changed()

    def _finished(self):
        self.busy = False
        self.operation.deleteLater(); self.operation = None
        if self.closing:
            self.idle.emit()
        elif self.pending and not self.debounce.isActive():
            self.refresh()

    def _sort_changed(self, column):
        sort = ('name', 'type', 'size', 'path')[column]
        self.descending = not self.descending if self.sort == sort else False
        self.sort = sort; self.offset = 0; self._revision += 1
        self.results.header().setSortIndicator(column, qt.Qt.SortOrder.DescendingOrder if self.descending else qt.Qt.SortOrder.AscendingOrder)
        self.results.header().setSortIndicatorShown(True)
        if self.busy: self.operation.requestInterruption()
        self.refresh()

    def _page(self, direction):
        self.offset = max(0, self.offset + direction * self.page_size)
        self._revision += 1
        if self.busy: self.operation.requestInterruption()
        self.refresh()

    def _selection_changed(self):
        if not self._loading: self.browser._selection_changed()

    def show_in_browser(self, path):
        path = Path(path)
        if not path.exists():
            self.summary.setText('This cached result is currently unavailable. Refresh when its location is accessible.')
            return False
        directory = path if path.is_dir() else path.parent
        self.browser.close_search()
        self.browser.navigate(directory)
        if directory != path: self.browser.views.select_source(self.browser.model.index(str(path)))
        return True

    def _locate_selected(self):
        paths = self.selected_paths()
        if paths: self.show_in_browser(paths[0])

    def _activate(self, row, column):
        path = row.data(0, qt.Qt.ItemDataRole.UserRole)
        if path.is_dir(): self.browser.navigate(path)
        elif path.exists(): self.browser._activate(self.browser.model.index(str(path)))
        else: self.summary.setText('This cached result is currently unavailable.')

    def _context_menu(self, point):
        row = self.results.itemAt(point)
        if row is None: return
        path = row.data(0, qt.Qt.ItemDataRole.UserRole)
        menu = self.browser.context_menu_for(self.browser.model.index(str(path)))
        if menu is not None:
            menu.insertAction(menu.actions()[0] if menu.actions() else None,
                              qt.QAction('Show in browser', menu, triggered=lambda: self.show_in_browser(path)))
            menu.exec(self.results.viewport().mapToGlobal(point)); menu.deleteLater()

    def stop(self):
        self.closing = True; self.pending = False
        self.debounce.stop(); self.progress_poll.stop()
        if self.busy: self.operation.requestInterruption()
        return self.busy

    def wait(self):
        if self.operation is not None: self.operation.wait()
