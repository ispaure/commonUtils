"""Live provider-backed directory browsing, without filesystem indexing or caches."""
from collections import deque
from contextlib import nullcontext
from types import SimpleNamespace
from ...runtime.resources.provider import DirectoryProvider, capabilities
from pathlib import Path
from .. import pyside as qt
from .lifecycle import ResourceOperations
from ..tasks.operation_progress import OperationProgress
from ..file_browser.navigation import BreadcrumbBar
from ..file_browser.controls import navigation_button, ViewModeSelector, FolderSizeControl, create_search_toggle, create_search_panel
from ..file_browser.entry_model import ProviderEntryModel, ProviderTree
from ..file_browser.model import ByteSortModel, _BrowserSelection
from ..file_browser.views import BrowserViews
from ..file_browser.thumbnails import image_thumbnail
from ...runtime.browsing import BrowseRole
from ...runtime.operations import check_cancelled
from ...filesystem import format_size
from ...runtime.resources.mutations import delete_resource, create_resource_folder, rename_resource


class ResourceBreadcrumbBar(BreadcrumbBar):
    """Use regular browser breadcrumbs without probing virtual paths on disk."""
    def _configure(self, button, path):
        button.setText(path.name or path.as_posix())
        button.setToolTip(str(path))
        button.setAccessibleName(f'Go to folder {path.name or path}')
        button.setIcon(self.style().standardIcon(qt.QStyle.StandardPixmap.SP_DirIcon))
        button.setIconSize(qt.QSize(18, 18))


class ResourceBrowser(qt.QWidget):
    activated = qt.Signal(object)
    directory_changed = qt.Signal(object)
    idle = qt.Signal()
    persistent_index = False

    def __init__(self, provider: DirectoryProvider, parent=None, *, directory=None, actions=(), thumbnail=None, details=None, preview=True):
        super().__init__(parent)
        self.provider = provider
        self.operations = ResourceOperations()
        self.operations.bind(provider)
        self.actions = tuple(actions)
        self.thumbnail = thumbnail
        self._queued_listings = deque()
        self._restoring = False
        self.navigation = SimpleNamespace(library=provider.root, directory=provider.root)
        self.history = []
        self.history_index = -1
        self.closing = False
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        self.setObjectName('resourceBrowser')
        self.setStyleSheet("""
            QWidget#resourceBrowser QTreeView::item,
            QWidget#resourceBrowser QTreeView::item:hover,
            QWidget#resourceBrowser QTreeView::item:selected { padding: 2px 4px; }
            QWidget#resourceBrowser QHeaderView::section { padding: 2px 4px; }
        """)
        row = self._build_navigation_controls(layout, provider)
        self._build_search_controls(row)
        self._build_provider_views(layout, provider)
        self._build_preview(row, details, preview)
        self._build_operation_controls(layout)
        self.back.clicked.connect(lambda: self._history(-1))
        self.forward.clicked.connect(lambda: self._history(1))
        self.up.clicked.connect(lambda: self.navigate(self.navigation.directory.parent))
        self.refresh_button.clicked.connect(self.refresh)
        from ..file_browser.keyboard import BrowserKeyboard
        self.keyboard = BrowserKeyboard(self, execute=self._view_command)
        self.operations.own(self.operation)
        self.operations.own(self.search_operation)
        self.operations.own(self.views, busy=lambda: self.views.cover_busy, cancel=self.views.stop)
        if self.preview:
            self.operations.own(self.preview, cancel=self.preview.stop)
        self.operations.own(self._queued_listings, busy=lambda: bool(self._queued_listings) or self.search_pending,
                            cancel=lambda: None)
        self.navigate(directory or provider.root)

    def _build_navigation_controls(self, layout, provider):
        self.workspace_controls = row = qt.QHBoxLayout()
        row.setSpacing(5)
        self.back = navigation_button(self, 'Back', qt.QStyle.StandardPixmap.SP_ArrowBack)
        self.forward = navigation_button(self, 'Forward', qt.QStyle.StandardPixmap.SP_ArrowForward)
        self.up = navigation_button(self, 'Up one folder', qt.QStyle.StandardPixmap.SP_ArrowUp)
        self.location = qt.QLabel(self)
        self.location.hide()  # Retain the relative-path label for existing consumers.
        self.breadcrumbs = ResourceBreadcrumbBar(self)
        self.breadcrumbs.requested.connect(self.navigate)
        self.refresh_button = navigation_button(self, 'Refresh folder', qt.QStyle.StandardPixmap.SP_BrowserReload)
        self.new_folder = navigation_button(self, 'New folder…', qt.QStyle.StandardPixmap.SP_FileDialogNewFolder)
        self.new_folder.setVisible(capabilities(provider).create)
        self.new_folder.clicked.connect(self._mkdir)
        for button in (self.back, self.forward, self.up):
            row.addWidget(button)
        row.addWidget(self.breadcrumbs, 1)
        row.addWidget(self.refresh_button)
        row.addWidget(self.new_folder)
        self.folder_size_button = FolderSizeControl(self)
        self.view_selector = ViewModeSelector(self, modes=(0, 1, 2))
        row.addWidget(self.folder_size_button)
        row.addWidget(self.view_selector)
        layout.addLayout(row)
        return row

    def _build_search_controls(self, row):
        self.filter = qt.QLineEdit()
        self.filter.setPlaceholderText('Search this folder and its subfolders')
        self.filter.setClearButtonEnabled(False)
        self.filter.setAccessibleName('Filter this folder')
        self.filter.textChanged.connect(self._filter)
        self.search_bar = self.filter
        self.search_button = create_search_toggle(self, self._search_toggled)
        row.insertWidget(4, self.search_button)
        self.search_panel, self.close_search_button = create_search_panel(self, self.search_bar, self.close_search)
        self.find_shortcut = qt.QShortcut(qt.QKeySequence(qt.QKeySequence.StandardKey.Find), self)
        self.find_shortcut.setContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.find_shortcut.activated.connect(self.open_search)
        self.clear_search = qt.QShortcut(qt.QKeySequence(qt.Qt.Key.Key_Escape), self)
        self.clear_search.setContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.clear_search.setEnabled(False)
        self.clear_search.activated.connect(self.close_search)

    def _build_provider_views(self, layout, provider):
        self.model = ProviderEntryModel(provider, self, thumbnail=self._thumbnail)
        self.sort_model = ByteSortModel(self.model, self)
        self.tree = ProviderTree()
        self.tree.setModel(self.sort_model)
        self.tree.setSelectionModel(_BrowserSelection(self.sort_model, self.tree))
        self.tree.selectionModel().selectionChanged.connect(self.tree.itemSelectionChanged)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, qt.Qt.SortOrder.AscendingOrder)
        self.tree.header().setSectionResizeMode(0, qt.QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, qt.QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, qt.QHeaderView.ResizeMode.ResizeToContents)
        self.views = BrowserViews(self.model, self.tree, self)
        self.views.navigation_root = provider.root
        self.view_selector.currentIndexChanged.connect(self.views.set_mode)
        self.folder_size_button.slider.valueChanged.connect(self.views.set_icon_scale)
        self.model.children_requested.connect(self._request_children)
        self.views.activated.connect(self._activate)
        self.views.context_requested.connect(self._context_menu)
        self.views.directory_changed.connect(self._view_directory_changed)
        self.views.selection_changed.connect(self.tree.itemSelectionChanged)
        self.views.idle.connect(self._maybe_idle)
        self.splitter = qt.QSplitter(qt.Qt.Orientation.Horizontal)
        self.files_panel = qt.QWidget(self.splitter)
        files_layout = qt.QVBoxLayout(self.files_panel)
        files_layout.setContentsMargins(0, 0, 0, 0)
        files_layout.addWidget(self.search_panel)
        files_layout.addWidget(self.views, 1)
        self.splitter.addWidget(self.files_panel)
        layout.addWidget(self.splitter, 1)

    def _build_preview(self, row, details, preview):
        self.preview = None
        if preview:
            from ..file_browser.controls import ViewIcon
            from ..appearance.icons import set_painted_icon
            self.preview_toggle = qt.QToolButton(self)
            set_painted_icon(self.preview_toggle, ViewIcon, 4)
            self.preview_toggle.setCheckable(True)
            self.preview_toggle.setChecked(True)
            self.preview_toggle.setToolTip('Show file and folder information')
            self.preview_toggle.setAccessibleName('Show file and folder preview')
            row.addWidget(self.preview_toggle)
            from ..file_browser.resource_preview import ResourcePreview
            self.preview = ResourcePreview(self, details)

    def _build_operation_controls(self, layout):
        self.notice = qt.QLabel('Session-only browsing · Thumbnails stay in memory')
        self.notice.setToolTip('Folder contents stay in memory. Persistent indexing and disk caches are disabled.')
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.operation = OperationProgress(self)
        self.operation.completed.connect(self._loaded)
        layout.addWidget(self.operation)
        self.search_operation = OperationProgress(self)
        self.search_operation.completed.connect(self._search_loaded)
        layout.addWidget(self.search_operation)
        self.search_timer = qt.QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(400)
        self.search_timer.timeout.connect(self._start_search)
        self.search_pending = False
        self._normal_tree = None

    def _controls(self, enabled=True):
        self.views.setEnabled(enabled)
        self.breadcrumbs.setEnabled(enabled)
        self.refresh_button.setEnabled(enabled)
        self.new_folder.setEnabled(enabled)
        self.back.setEnabled(enabled and self.history_index > 0)
        self.forward.setEnabled(enabled and self.history_index < len(self.history) - 1)
        self.up.setEnabled(enabled and self.navigation.directory != self.provider.root)

    @property
    def busy(self):
        return self.operations.busy

    def _thumbnail(self, path, size, cancelled):
        provider = getattr(self.provider, 'provider', self.provider)
        loader = self.thumbnail or getattr(provider, 'thumbnail', None)
        scope = getattr(provider, 'operation', None)
        with scope(cancelled) if scope else nullcontext():
            check_cancelled(cancelled)
            if loader:
                return loader(path, size, cancelled)
            if Path(path).suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'} or not hasattr(provider, 'open'):
                return b''
            with provider.open(path) as stream:
                data = stream.read(16 * 1024 * 1024 + 1)
            check_cancelled(cancelled)
            return image_thumbnail(data, size) if len(data) <= 16 * 1024 * 1024 else b''

    def _set_directory(self, directory, *, remember=True):
        if remember and (self.history_index < 0 or self.history[self.history_index] != directory):
            del self.history[self.history_index + 1:]
            self.history.append(directory)
            self.history_index = len(self.history) - 1
        self.navigation.directory = directory
        relative = self.provider.relative(directory)
        self.location.setText(relative or '/')
        paths = [self.provider.root]
        for part in Path(relative).parts:
            paths.append(paths[-1] / part)
        self.breadcrumbs.set_paths(paths)
        self._controls(not self.operation.busy)

    def navigate(self, directory, *, remember=True):
        if self.operation.busy or self.closing:
            return False
        directory = Path(directory)
        self.provider.relative(directory)
        self.model.ensure_directory(directory)
        self._remember_listing = remember
        self._start_listing(directory, display=True)
        return True

    def _start_listing(self, directory, *, display=False):
        if self.filter.text() or self._normal_tree is not None:
            self.close_search()
        self._listing_target, self._display_listing = directory, display
        self.model.pending.add(directory)
        relative = self.provider.relative(directory)
        self._controls(False)
        self._listing_identity = self.operations.capture()
        provider = self.provider
        self.operation.start(lambda report, cancelled: provider.list(relative, cancelled=cancelled), message='Reading folder…')

    def _request_children(self, directory):
        if self.closing:
            return
        if self.operation.busy or self._restoring:
            if directory != self._listing_target and directory not in self._queued_listings:
                self._queued_listings.append(directory)
        else:
            self._start_listing(directory)

    def refresh(self):
        return self.navigate(self.navigation.directory, remember=False)

    def _history(self, offset):
        target = self.history_index + offset
        if 0 <= target < len(self.history) and self.navigate(self.history[target], remember=False):
            self.history_index = target

    def _view_directory_changed(self, directory):
        if not self._restoring and directory is not None and directory != self.navigation.directory:
            self._set_directory(directory)
            self.directory_changed.emit(directory)

    def _loaded(self, rows, error):
        if not self.operations.accepts(self._listing_identity):
            self._maybe_idle()
            return
        target = self._listing_target
        if not error and rows is not None:
            selected = [index.data(BrowseRole.Identity) for index in self.views.selected_rows()]
            if self._display_listing and target != self.navigation.directory:
                selected = []
            root = target if self._display_listing or self.views.root is None else self.views.root
            self._restoring = True
            try:
                self.model.set_children(target, self.model.entries(rows))
                self.model.set_filter(self.filter.text(), target)
                if self._display_listing or self.views.root is None:
                    self.views.set_root(root)
                for identity in selected:
                    index = self.model.browse_index(identity)
                    if index.isValid():
                        self.views.select_source(index)
            except Exception as failure:
                self.operation.message.setText(str(failure))
                error = str(failure)
            finally:
                self._restoring = False
            if not error:
                if self._display_listing:
                    self._set_directory(target, remember=getattr(self, '_remember_listing', True))
                self.operation.hide()
                self.directory_changed.emit(self.navigation.directory)
        self._controls()
        if self.search_pending:
            self.search_timer.start()
        if self._queued_listings:
            self._start_listing(self._queued_listings.popleft())
        else:
            self._maybe_idle()

    def open_search(self):
        if self.closing:
            return
        self.search_button.setChecked(True)
        self.search_bar.setFocus()
        self.search_bar.selectAll()

    def close_search(self):
        if self.search_button.isChecked():
            self.search_button.setChecked(False)
        else:
            self._search_toggled(False)

    def _search_toggled(self, enabled):
        self.search_panel.setVisible(enabled)
        self.clear_search.setEnabled(enabled)
        if enabled:
            self.search_bar.setFocus()
        else:
            self.search_bar.clear()
            self.views.currentWidget().setFocus()

    def _show_tree(self, tree, *, flat=False):
        self._restoring = True
        try:
            self.model.beginResetModel()
            self.model.tree = tree
            self.model.flat_root = self.navigation.directory if flat else None
            self.model.pending.clear()
            self.model.filter_text = ''
            self.model.endResetModel()
            self.views.set_root(self.navigation.directory)
        finally:
            self._restoring = False

    def _filter(self, *_):
        self.search_timer.stop()
        self.search_operation.request_cancel()
        query = self.filter.text().strip()
        self.search_pending = bool(query) and not self.closing
        if self._normal_tree is not None:
            self._show_tree(self._normal_tree)
        if not query:
            self._normal_tree = None
            self.search_operation.hide()
            return
        if self._normal_tree is None:
            self._normal_tree = self.model.tree
        self.search_timer.start()

    def _start_search(self):
        if self.closing or not self.search_pending or self.operation.busy or self.search_operation.busy:
            return
        from ...search.providers import search_resources
        query, directory = self.filter.text().strip(), self.navigation.directory
        self._active_search = query, directory
        self.search_pending = False
        self.search_operation.bar.show()
        self.search_operation.cancel_button.show()
        self._search_identity = self.operations.capture()
        provider = self.provider
        relative = provider.relative(directory)
        self.search_operation.start(lambda report, cancelled: search_resources(provider,
            relative, query, cancelled=cancelled), message='Searching this folder and its subfolders…')

    def _search_loaded(self, result, error):
        query, directory = self._active_search
        if self.operations.accepts(self._search_identity) and query == self.filter.text().strip() and directory == self.navigation.directory:
            if error:
                self.search_operation.message.setText('Search failed: ' + error)
            elif result is not None:
                from ...runtime.browsing import BrowseEntry, BrowseTree
                parts = Path(self.provider.relative(directory)).parts
                tree = BrowseTree(BrowseEntry(self.provider.root, self.provider.root.name, True),
                                  max_entries=len(result.rows) + len(parts) + 1)
                current = tree.root
                for part in parts:
                    child = current / part
                    tree.ensure(BrowseEntry(child, part, True), current)
                    current = child
                tree.set_children(directory, self.model.entries(result.rows))
                self._show_tree(tree, flat=True)
                self.search_operation.message.setText(f'{len(result.rows)} matches' + ('' if result.complete else ' · Partial results'))
                self.search_operation.bar.hide()
                self.search_operation.cancel_button.hide()
        if self.search_pending:
            self.search_timer.start()
        self._maybe_idle()

    def selected_rows(self):
        return [row for index in self.views.selected_rows()
                if (row := index.data(qt.Qt.ItemDataRole.UserRole)) is not None]

    def _view_command(self, action):
        if action in {'back', 'forward', 'up'}:
            getattr(self, action).click()
            return
        rows = self.views.selected_rows()
        if len(rows) != 1:
            return
        if action == 'open':
            self._activate(rows[0])
        elif action == 'rename' and capabilities(self.provider).rename:
            row = rows[0].data(qt.Qt.ItemDataRole.UserRole)
            if row is not None:
                self._rename(row)

    def _activate(self, index, column=0):
        row = index.data(qt.Qt.ItemDataRole.UserRole)
        if not row:
            return
        if row['directory']:
            self.navigate(self.provider.root / row['path'])
        else:
            self.activated.emit(self.provider.root / row['path'])

    def _context_menu(self, index):
        row = index.data(qt.Qt.ItemDataRole.UserRole) if index.isValid() else None
        if row is None:
            return
        menu = qt.QMenu(self)
        menu.addAction('Open', lambda: self._activate(index))
        if capabilities(self.provider).rename:
            menu.addAction('Rename…', lambda: self._rename(row))
        if capabilities(self.provider).delete:
            menu.addAction('Delete…', lambda: self._delete(row))
        for label, available, callback in self.actions:
            if available(row):
                menu.addAction(label, lambda checked=False, callback=callback: callback(self.provider.root / row['path']))
        menu.exec(self.views.context_position)

    def mutate(self, work):
        if self.busy or self.closing:
            return False
        if self.filter.text() or self._normal_tree is not None:
            self.close_search()
        directory = self.provider.relative(self.navigation.directory)
        self._controls(False)
        self._listing_target = self.navigation.directory
        self._display_listing = False
        def perform(report, cancelled):
            work(cancelled)
            return self.provider.list(directory, cancelled=cancelled)
        self.operation.start(perform, message='Updating files…')
        return True

    def _mkdir(self):
        name, accepted = qt.QInputDialog.getText(self, 'New folder', 'Folder name:')
        if accepted and name:
            from ...runtime.resources.paths import resource_path
            try:
                name = resource_path(name)
                if '/' in name:
                    raise ValueError('Enter one folder name.')
            except ValueError as error:
                qt.QMessageBox.warning(self, 'New folder', str(error))
                return
            path = '/'.join(p for p in (self.provider.relative(self.navigation.directory), name) if p)
            self.mutate(lambda cancelled: create_resource_folder(self.provider, path, cancelled=cancelled))

    def _rename(self, row):
        name, accepted = qt.QInputDialog.getText(self, 'Rename', 'New name:', text=row['name'])
        if accepted and name:
            from ...runtime.resources.paths import resource_path
            try:
                name = resource_path(name)
                if '/' in name:
                    raise ValueError('Enter one name; use Move for another folder.')
            except ValueError as error:
                qt.QMessageBox.warning(self, 'Rename', str(error))
                return
            target = '/'.join(p for p in (row['path'].rpartition('/')[0], name) if p)
            self.mutate(lambda cancelled: rename_resource(self.provider, row['path'], target, cancelled=cancelled))

    def _delete(self, row):
        if qt.QMessageBox.question(self, 'Delete permanently',
                'Permanently delete this item and any contents? This cannot be undone.',
                qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.No,
                qt.QMessageBox.StandardButton.No) == qt.QMessageBox.StandardButton.Yes:
            self.mutate(lambda cancelled: delete_resource(self.provider, row['path'], cancelled=cancelled))

    def _maybe_idle(self):
        if not self.busy:
            self.idle.emit()

    def stop(self):
        self.closing = True
        self.search_timer.stop()
        self.search_pending = False
        self._queued_listings.clear()
        return self.operations.stop()

    def resume(self):
        """Resume a picker after its validation failed and all workers retired."""
        if self.busy:
            raise RuntimeError('Wait for browser workers before resuming.')
        self.operations.resume()
        self.closing = self.views.closing = False
        self.views.cover_cancelled.clear()
        self.views.badge_timer.start()
        self.views.tiles.viewport().update()
        if self.preview:
            self.preview.resume()
