"""Reusable object-driven filesystem browser; applications supply domain behavior."""

from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from .. import pyside as qt
from .. import desktop_actions
from ...dirUtils import Directory
from ...filesystem import BrowserDetails, BrowserPanel, format_size, scan_folders
from .model import BrowserFileSystemModel
from .details import DetailsPanel
from .controls import ViewModeSelector, FolderSizeControl
from .navigation import NavigationBar
from ..operations import Operation
from .views import FileViews
from .editing import FilenameDelegate
from .file_actions import FileActions, clipboard_files
from .index_worker import FolderOperation


@dataclass(frozen=True)
class BrowserContext:
    browser: object
    selection: tuple

    @property
    def widget(self):
        return self.browser

    def invoke(self, name, *args):
        handler = self.browser.services.get(name)
        if handler is None:
            raise RuntimeError(f'This application has not supplied the action: {name}')
        return handler(*args)


class FileBrowser(qt.QWidget):
    """Embed with a Directory/Path. No project libraries, formats or GUI actions are assumed.

    File hooks return BrowserPanel/BrowserAction descriptors. Panel loaders and
    thumbnail hooks run in workers; actions/activation run on the GUI thread.
    """
    selection_changed = qt.Signal(object)
    details_loaded = qt.Signal(object)
    refreshed = qt.Signal()
    idle = qt.Signal()

    def __init__(self, directory=None, parent=None, *, services=None, action_providers=(), folder_fields=None, calculate_folder_sizes=True):
        super().__init__(parent)
        self.idle.connect(self.close)
        self.services = services or {}
        self.action_providers = tuple(action_providers)
        self.folder_fields = folder_fields
        self._base_services = dict(self.services)
        self._base_action_providers = self.action_providers
        self._base_folder_fields = folder_fields
        self._extensions = {}
        self.activation_handlers = ()
        self._scan_windows = []
        self.busy = False
        self.folder_busy = False
        self.calculate_folder_sizes = calculate_folder_sizes
        self.folder_pending = False
        self.folder_root = None
        self.refresh_pending = False
        self.stopping = False
        self.selected_object = None
        self.last_details = None
        self.cover_pixmap = qt.QPixmap()
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.search_bar = qt.QLineEdit()
        self.search_bar.setAccessibleName('Search indexed files and folders')
        self.search_bar.setClearButtonEnabled(True)
        self.search_bar.setPlaceholderText('Search this location and its subfolders')
        layout.addWidget(self.search_bar)
        layout.addLayout(self._create_navigation_controls())
        self.index_status = qt.QLabel()
        self.index_status.setWordWrap(True)
        self.index_status.setTextFormat(qt.Qt.TextFormat.PlainText)
        layout.addWidget(self.index_status)
        self._create_views()
        layout.addWidget(self.splitter, 1)
        self._create_preview_panel()
        self.file_actions = FileActions(self)
        self._reconcile_pending = False
        self.index_watcher = qt.QFileSystemWatcher(self)
        self.index_watcher.directoryChanged.connect(self._indexed_path_changed)
        self.index_watcher.fileChanged.connect(self._indexed_path_changed)
        self.reconcile_debounce = qt.QTimer(self)
        self.reconcile_debounce.setSingleShot(True); self.reconcile_debounce.setInterval(400)
        self.reconcile_debounce.timeout.connect(self._reconcile_index)
        self.reconcile_timer = qt.QTimer(self)
        self.reconcile_timer.setInterval(60_000)
        self.reconcile_timer.timeout.connect(self._reconcile_index)
        self.reconcile_timer.start()
        self.clear_search = qt.QShortcut(qt.QKeySequence(qt.Qt.Key.Key_Escape), self)
        self.clear_search.setContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.clear_search.activated.connect(self.search_bar.clear)
        qt.QApplication.instance().aboutToQuit.connect(self.shutdown)
        if directory is not None:
            self.set_directory(directory)

    def _create_navigation_controls(self):
        self.navigation = NavigationBar(self)
        self.navigation.requested.connect(self.navigate)
        controls = qt.QHBoxLayout()
        controls.addWidget(self.navigation, 1)
        self.view_selector = ViewModeSelector(self)
        self.view_selector.setAccessibleName('Browser view')
        controls.addWidget(self.view_selector)
        self.folder_size_button = FolderSizeControl(self)
        self.folder_size_slider = self.folder_size_button.slider
        self.folder_size_button.setVisible(False)
        controls.addWidget(self.folder_size_button)
        self.search_button = qt.QPushButton('Search…')
        self.search_button.clicked.connect(self.open_search)
        controls.addWidget(self.search_button)
        self.storage_button = qt.QPushButton('Storage…')
        self.storage_button.clicked.connect(self.open_storage)
        controls.addWidget(self.storage_button)
        self.refresh_button = qt.QPushButton('Refresh')
        self.refresh_button.clicked.connect(self.refresh)
        controls.addWidget(self.refresh_button)
        return controls

    def open_search(self):
        from .discovery import SearchDialog
        return self._open_scan_window(SearchDialog)

    def open_storage(self):
        from .storage import StorageDialog
        return self._open_scan_window(StorageDialog)

    def _open_scan_window(self, kind):
        if self.stopping or self.navigation.directory is None:
            return None
        window = kind(self)
        self._scan_windows.append(window)
        window.idle.connect(self._maybe_idle)
        window.destroyed.connect(lambda: self._scan_windows.remove(window) if window in self._scan_windows else None)
        window.show()
        return window

    def _scan_busy(self):
        return self.index_search.busy or any(window.busy for window in self._scan_windows)

    def _create_views(self):
        self.model = BrowserFileSystemModel(self)
        self.model.setReadOnly(False)
        self.model.setFilter(qt.QDir.Filter.AllDirs | qt.QDir.Filter.Files | qt.QDir.Filter.NoDotAndDotDot)
        self.tree = qt.QTreeView()
        self.tree.setModel(self.model)
        self.tree.expanded.connect(lambda index: self.model.size_parents.add(self.model.filePath(index)))
        self.tree.collapsed.connect(lambda index: self.model.size_parents.discard(self.model.filePath(index)))
        self.tree.setItemDelegate(FilenameDelegate(self.tree))
        self.tree.setSelectionBehavior(qt.QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, qt.Qt.SortOrder.AscendingOrder)
        self.tree.setColumnWidth(0, 400)
        self.tree.setColumnWidth(3, 180)
        self.tree.setColumnWidth(1, 90)
        self.tree.hideColumn(2)
        self.tree.header().moveSection(3, 1)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, qt.QHeaderView.ResizeMode.Stretch)
        for column in (1, 3):
            self.tree.header().setSectionResizeMode(column, qt.QHeaderView.ResizeMode.ResizeToContents)
        self.views = FileViews(self.model, self.tree, self)
        self.views.selection_changed.connect(self._selection_changed)
        self.views.directory_changed.connect(self.navigation.set_directory)
        self.views.directory_changed.connect(self._directory_changed)
        self.views.context_requested.connect(self._context_menu)
        self.views.activated.connect(self._activate)
        self.views.idle.connect(self._maybe_idle)
        self.view_selector.currentIndexChanged.connect(self.views.set_mode)
        self.view_selector.currentIndexChanged.connect(lambda mode: self.folder_size_button.setVisible(mode == 1))
        self.folder_size_slider.valueChanged.connect(self.views.tiles.set_folder_scale)
        self.splitter = qt.QSplitter()
        self.splitter.setChildrenCollapsible(False)
        self.list_stack = qt.QStackedWidget()
        self.list_stack.addWidget(self.views)
        from .index_search import IndexSearch
        self.index_search = IndexSearch(self)
        self.index_search.idle.connect(self._maybe_idle)
        self.list_stack.addWidget(self.index_search)
        self.splitter.addWidget(self.list_stack)

    def _create_preview_panel(self):
        self.preview_panel = qt.QWidget()
        self.preview_panel.setMinimumWidth(280)
        panel_layout = qt.QVBoxLayout(self.preview_panel)
        header = qt.QHBoxLayout()
        self.heading = qt.QLabel('Files')
        self.heading.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.heading.setWordWrap(True)
        header.addWidget(self.heading, 1)
        panel_layout.addLayout(header)
        self.message = qt.QLabel('Select a file or folder.')
        self.message.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.message.setWordWrap(True)
        panel_layout.addWidget(self.message)
        self.cover = qt.QLabel()
        self.cover.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        self.cover.setMinimumSize(180, 200)
        self.cover.setMaximumHeight(500)
        panel_layout.addWidget(self.cover)
        self.tabs = qt.QTabWidget()
        self.tabs.setDocumentMode(True)
        panel_layout.addWidget(self.tabs, 1)
        self._empty_preview = qt.QPlainTextEdit()
        self._empty_preview.setReadOnly(True)
        self.splitter.addWidget(self.preview_panel)
        self.splitter.setSizes([700, 500])

    @property
    def preview(self):
        return self.tabs.currentWidget() or self._empty_preview

    def install_extension(self, owner, *, services=None, action_providers=(), folder_fields=None, activation_handlers=(), enabled=True):
        """Install a reversible, owner-scoped layer of browser capabilities."""
        self._extensions[owner] = (dict(services or {}), tuple(action_providers), folder_fields, tuple(activation_handlers), enabled)
        self._rebuild_extensions()

    def set_extension_enabled(self, owner, enabled):
        if owner not in self._extensions:
            return
        services, providers, fields, activation, previous = self._extensions[owner]
        if previous == enabled:
            return
        self._extensions[owner] = (services, providers, fields, activation, enabled)
        self._rebuild_extensions()

    def remove_extension(self, owner):
        if self._extensions.pop(owner, None) is not None:
            self._rebuild_extensions()

    def _rebuild_extensions(self):
        self.services = dict(self._base_services)
        providers = list(self._base_action_providers)
        fields = [self._base_folder_fields] if self._base_folder_fields else []
        activation = []
        for services, actions, folder_fields, handlers, enabled in self._extensions.values():
            if enabled:
                self.services.update(services)
                providers.extend(actions)
                activation.extend(handlers)
                if folder_fields is not None:
                    fields.append(folder_fields)
        self.action_providers = tuple(providers)
        self.activation_handlers = tuple(activation)
        self.folder_fields = (lambda item, stats: tuple(value for provider in fields
                             for value in provider(item, stats))) if fields else None
        if self.navigation.library is not None and not self.stopping:
            self.refresh()

    def selected_objects(self):
        if self.index_search.active:
            return tuple(self.model.object_for_path(path) for path in self.index_search.selected_paths())
        return tuple(self.model.item(index) for index in self.views.selected_rows())

    def set_directory(self, directory):
        path = directory.path if isinstance(directory, Directory) else Path(directory)
        path = path.absolute()
        if not path.is_dir():
            raise NotADirectoryError(path)
        self.navigation.set_library(path)
        self.model.setRootPath(str(path))
        self.views.set_root(path)

    def _directory_changed(self, path):
        self.model.size_parents = {str(path)}
        self.index_search.scope_changed(path)
        self._update_watch_paths(path, (path,))
        if path != self.folder_root:
            self.refresh_folder_totals()

    def _update_watch_paths(self, root, paths):
        if self.stopping or root != self.navigation.directory:
            return
        expected = {str(path) for path in paths}
        previous = set(self.index_watcher.directories()) | set(self.index_watcher.files())
        if previous - expected: self.index_watcher.removePaths(list(previous - expected))
        if expected - previous: self.index_watcher.addPaths(list(expected - previous))

    def _indexed_path_changed(self, path):
        if self.stopping or not self.calculate_folder_sizes: return
        from ...directory_index import directory_cache
        directory_cache.invalidate(Path(path))
        self._reconcile_pending = True
        self.reconcile_debounce.start()

    def _reconcile_index(self):
        if self.stopping or not self.calculate_folder_sizes or self.folder_busy: return
        self._reconcile_pending = False
        self.refresh_folder_totals()

    def navigate(self, path):
        path = Path(path)
        root = self.navigation.library
        if root is not None and path.is_dir() and (path == root or root in path.parents):
            self.views.set_root(path)
        else:
            self.navigation.set_directory(self.views.browsing_directory())

    def context(self, clicked=None):
        selection = self.selected_objects()
        if clicked is not None and not any(item.path == clicked.path for item in selection):
            selection = (clicked,)
        return BrowserContext(self, selection)

    def context_menu_for(self, index, *, directory=None):
        index = self.views.source_index(index).siblingAtColumn(0) if index.isValid() else index
        item = self.model.item(index) if index.isValid() else None
        if item is not None and not (item.path.exists() or item.path.is_symlink()):
            return None
        persistent = qt.QPersistentModelIndex(index)
        context = self.context(item) if item is not None else BrowserContext(self, ())
        destination = (item.path if isinstance(item, Directory) else None) if item else (
            Path(directory) if directory is not None else self.views.browsing_directory())
        menu = qt.QMenu(self)
        mutating = not self.file_actions.busy and not self.stopping
        def standard(title, callback, *, enabled=True, key=None):
            action = menu.addAction(title)
            action.setEnabled(enabled)
            if key is not None:
                action.setShortcut(qt.QKeySequence(key))
            action.triggered.connect(lambda checked=False: self._run(callback))
            return action
        if item is not None:
            single = len(context.selection) == 1
            if isinstance(item, Directory) or self.activation_handlers:
                standard('Open', lambda: self._activate(qt.QModelIndex(persistent)), enabled=single)
            if not isinstance(item, Directory):
                standard('Open in Default App', lambda: [desktop_actions.open_default(selected.path)
                         for selected in context.selection],
                         enabled=all(not isinstance(selected, Directory) for selected in context.selection))
            menu.addSeparator()
            standard('Cut', lambda: self.file_actions.copy(context.selection, move=True), enabled=mutating,
                     key=qt.QKeySequence.StandardKey.Cut)
            standard('Copy', lambda: self.file_actions.copy(context.selection), key=qt.QKeySequence.StandardKey.Copy)
        if destination is not None:
            standard('Paste', lambda: self.file_actions.paste(destination),
                     enabled=mutating and bool(clipboard_files()[0]) and destination.is_dir(),
                     key=qt.QKeySequence.StandardKey.Paste)
        if item is None:
            menu.addSeparator()
            standard('Refresh', self.refresh)
            standard(desktop_actions.reveal_label(), lambda: desktop_actions.reveal(destination),
                     enabled=destination is not None)
            return menu
        menu.addSeparator()
        standard('Rename', lambda: self.file_actions.rename(persistent), enabled=mutating and single,
                 key=qt.Qt.Key.Key_F2)
        # Capture the full selection, deduplicate, and keep ordering independent of
        # filesystem row order or feature discovery order.
        contributions = {}
        for selected in context.selection:
            entries = list(selected.browser_actions(context))
            for provider in self.action_providers:
                entries.extend(provider(selected, context))
            for entry in entries:
                contributions.setdefault(entry.key, entry)
        def contributed(entry):
            action = menu.addAction(entry.title)
            action.setEnabled(mutating)
            source = entry.source or 'Extensions'
            action.setToolTip(f'Provided by {source}')
            action.setProperty('source', source)
            action.triggered.connect(lambda checked=False: self._run(lambda: entry.run(context)))
        for entry in sorted((entry for entry in contributions.values() if entry.category == 'rename'),
                            key=lambda entry: (entry.order, entry.title.casefold())):
            contributed(entry)
        groups = {}
        for entry in contributions.values():
            if entry.category != 'rename':
                groups.setdefault(entry.source or 'Extensions', []).append(entry)
        for source, entries in sorted(groups.items(), key=lambda group: (min(entry.order for entry in group[1]), group[0].casefold())):
            menu.addSection(source)
            for entry in sorted(entries, key=lambda entry: (entry.order, entry.title.casefold())):
                contributed(entry)
        menu.addSeparator()
        standard(desktop_actions.reveal_label(), lambda: desktop_actions.reveal(item.path))
        return menu

    def _context_menu(self, index):
        menu = self.context_menu_for(index, directory=getattr(self.views, 'context_directory', None))
        if menu is not None:
            menu.exec(self.views.context_position)
            menu.deleteLater()

    def _run(self, callback):
        try:
            callback()
        except Exception as error:
            qt.QMessageBox.warning(self, 'Cannot complete action', str(error))

    def _activate(self, index):
        if not index.isValid():
            return
        item = self.model.item(index)
        if isinstance(item, Directory):
            self.navigate(item.path)
        else:
            def activate():
                context = self.context(item)
                if any(handler(item, context) for handler in self.activation_handlers):
                    return
                if not item.browser_activate(context):
                    desktop_actions.open_default(item.path)
            self._run(activate)

    def _clear_details(self):
        self.last_details = None
        self.selected_object = None
        self.cover.clear()
        self.cover.setToolTip('')
        self.cover_pixmap = qt.QPixmap()
        while self.tabs.count():
            widget = self.tabs.widget(0)
            self.tabs.removeTab(0)
            widget.deleteLater()
        self._empty_preview.clear()

    def _selection_changed(self):
        if self.stopping:
            return
        items = self.selected_objects()
        self.selection_changed.emit(items)
        if self.busy:
            self.refresh_pending = True
            return
        self._clear_details()
        if len(items) == 1:
            self.load(items[0])
        elif len(items) > 1:
            self.heading.setText(f'{len(items)} items selected')
            self.message.setText('Right-click the selection for available actions.')
        else:
            self.heading.setText('Files')
            self.message.setText('Select a file or folder.')

    def _generic_details(self, item, stats):
        fields = list(item.filesystem_information())
        if isinstance(item, Directory):
            if stats is None:
                fields.append(('Total size', 'Not calculated' if not self.calculate_folder_sizes else
                               'Calculating…' if self.folder_busy else 'Unavailable'))
            else:
                fields.extend([('Total size', ('At least ' if not stats.complete else '') + format_size(stats.size)), ('Files', f'{stats.files:,}'),
                               ('Subfolders', f'{stats.folders:,}')])
                fields.append(('Size status', 'Incomplete / calculating' if not stats.complete else
                               'Cached; checking for changes' if stats.stale else 'Up to date'))
                if self.folder_fields is not None:
                    fields.extend(self.folder_fields(item, stats))
                if stats.skipped:
                    fields.append(('Excluded links / unreadable items', stats.skipped))
        return BrowserDetails(tuple(fields))

    def load(self, item):
        if self.busy:
            self.refresh_pending = True
            return
        self._clear_details()
        self.selected_object = item
        self.heading.setText(item.name if isinstance(item, Directory) else item.file_name)
        self.message.setText('Loading information…')
        stats = self.model.folder_totals.get(item.path)
        panels = [BrowserPanel('filesystem', 'File Information', lambda: self._generic_details(item, stats))]
        panels.extend(item.browser_panels())
        self.busy = True
        self.refresh_pending = False
        def read():
            result = []
            for panel in panels:
                try:
                    details = panel.load()
                    if not isinstance(details, BrowserDetails):
                        raise TypeError('Panel loaders must return BrowserDetails')
                    result.append((panel, details, ''))
                except Exception as error:
                    result.append((panel, BrowserDetails(), str(error)))
            return result
        self.operation = Operation(read, self)
        self.operation.completed.connect(self._loaded)
        self.operation.finished.connect(self._finished)
        self.operation.start()

    def _loaded(self, result, error):
        if self.refresh_pending or self.stopping:
            return
        self.message.setText(error)
        self.last_details = result
        for panel, details, issue in result or ():
            editor = DetailsPanel(details.fields, issue)
            self.tabs.addTab(editor, panel.title)
            if details.thumbnail:
                self.cover_pixmap.loadFromData(details.thumbnail)
            if details.message:
                self.cover.setToolTip(details.message)
        if self.tabs.count():
            self.tabs.setCurrentIndex(self.tabs.count() - 1)
        if not self.cover_pixmap.isNull():
            self.cover.setMinimumSize(180, 200)
            self.cover.setMaximumHeight(500)
            self._scale_cover()
        else:
            self.cover.setMinimumSize(96, 96)
            self.cover.setMaximumHeight(120)
            index = self.model.index(str(self.selected_object.path))
            icon = self.model.fileIcon(index)
            if icon.isNull():
                icon = self.model.iconProvider().icon(qt.QFileInfo(str(self.selected_object.path)))
            pixmap = icon.pixmap(96, 96)
            if pixmap.isNull():
                standard = qt.QStyle.StandardPixmap.SP_DirIcon if isinstance(self.selected_object, Directory) else qt.QStyle.StandardPixmap.SP_FileIcon
                pixmap = self.style().standardIcon(standard).pixmap(96, 96)
            self.cover.setPixmap(pixmap)
        self.details_loaded.emit(result)

    def _scale_cover(self):
        ratio = self.devicePixelRatioF()
        preview = self.cover_pixmap.scaled(round(320 * ratio), round(440 * ratio),
                                          qt.Qt.AspectRatioMode.KeepAspectRatio,
                                          qt.Qt.TransformationMode.SmoothTransformation)
        preview.setDevicePixelRatio(ratio)
        self.cover.setPixmap(preview)

    def event(self, event):
        handled = super().event(event)
        if event.type() in (qt.QEvent.Type.ScreenChangeInternal, qt.QEvent.Type.DevicePixelRatioChange):
            pixmap = getattr(self, 'cover_pixmap', None)
            if pixmap is not None and not pixmap.isNull():
                self._scale_cover()
        return handled

    def _finished(self):
        self.busy = False
        self.operation.deleteLater()
        if self.stopping:
            self._maybe_idle()
        elif self.refresh_pending:
            self._selection_changed()

    def refresh_item(self, path):
        self.model.invalidate(path)
        self.views.covers.invalidate(path)
        if self.selected_object is not None and self.selected_object.path == Path(path):
            self._selection_changed()
        self.refresh_folder_totals()

    def refresh(self):
        from ...directory_index import directory_cache
        directory_cache.invalidate(self.navigation.library)
        for path in list(self.views.covers.icons):
            self.model.invalidate(path)
            self.views.covers.invalidate(path)
        self.refresh_folder_totals()
        self._selection_changed()
        self.refreshed.emit()

    def set_folder_sizes_enabled(self, enabled):
        """Pause/resume automatic index totals without blocking on a running scan."""
        self.calculate_folder_sizes = bool(enabled)
        if not enabled:
            self.folder_pending = False
            if self.folder_busy:
                self.folder_operation.requestInterruption()
            self.model.set_folder_totals({})
            self.index_status.setText('Background sizes paused.')
        else:
            self.refresh_folder_totals()
        if isinstance(self.selected_object, Directory):
            self._selection_changed()

    def refresh_folder_totals(self):
        if not self.calculate_folder_sizes:
            self.model.set_folder_totals({})
            return
        if self.folder_busy:
            self.folder_pending = True
            self.folder_operation.requestInterruption()
            return
        root = self.navigation.directory
        if root is None or self.stopping:
            return
        self.folder_busy = True
        self.folder_pending = False
        self.folder_root = root
        self.index_status.setText('Checking saved sizes and indexing this location…')
        self.folder_operation = FolderOperation(root, scan_folders, self)
        self.folder_operation.updated.connect(self._folders_progressed)
        self.folder_operation.watch_paths.connect(self._update_watch_paths)
        self.folder_operation.completed.connect(lambda result, error: self._folders_loaded(root, result, error))
        self.folder_operation.finished.connect(self._folders_finished)
        self.folder_operation.start()

    def _folders_progressed(self, root, result):
        if self.calculate_folder_sizes and root == self.navigation.directory and result and not self.folder_pending and not self.stopping:
            self.model.set_folder_totals(result)
            self.index_search.refresh()
            self.index_status.setText('Cached or partial sizes available; background indexing continues…')
            if isinstance(self.selected_object, Directory):
                self._selection_changed()

    def _folders_loaded(self, root, result, error=''):
        if error and root == self.navigation.directory and not self.stopping:
            self.index_status.setText(f'Index unavailable: {error}. Any cached sizes remain available.')
        if self.calculate_folder_sizes and root == self.navigation.directory and result is not None and not self.folder_pending and not self.stopping:
            self.model.set_folder_totals(result)
            self.index_search.refresh()
            stats = result.get(root)
            self.index_status.setText('Index and sizes up to date.' if stats is None or stats.complete else
                                      'Index incomplete: some folders are unreadable or changed during scanning. Refresh to retry.')
            if isinstance(self.selected_object, Directory):
                self._selection_changed()

    def _folders_finished(self):
        self.folder_busy = False
        elapsed = monotonic() - self.folder_operation.started_at
        self.reconcile_timer.setInterval(max(60_000, min(300_000, int(elapsed * 10_000))))
        self.folder_operation.deleteLater()
        if self.stopping:
            self._maybe_idle()
        elif self.folder_pending or self._reconcile_pending:
            self._reconcile_pending = False
            self.refresh_folder_totals()
        else:
            self.index_search.refresh()

    def stop(self):
        self.stopping = True
        self.reconcile_debounce.stop(); self.reconcile_timer.stop()
        self.index_search.stop()
        for window in tuple(self._scan_windows):
            window.close()
        self.views.stop()
        self.file_actions.stop()
        if self.folder_busy:
            self.folder_operation.requestInterruption()
        return self.busy or self.folder_busy or self.views.cover_busy or self.file_actions.busy or self._scan_busy()

    def _maybe_idle(self):
        if self.stopping and not (self.busy or self.folder_busy or self.views.cover_busy or self.file_actions.busy or self._scan_busy()):
            self.idle.emit()

    def shutdown(self):
        self.stop()
        self.file_actions.wait()
        self.index_search.wait()
        for window in self._scan_windows:
            if window.task.operation is not None:
                window.task.operation.wait()
        for name in ('operation', 'folder_operation'):
            operation = getattr(self, name, None)
            if operation is not None:
                try:
                    operation.wait()
                except RuntimeError:
                    pass
        if self.views.cover_busy:
            self.views.operation.wait()

    def closeEvent(self, event):
        if self.stop():
            self.hide()
            event.ignore()
        else:
            event.accept()
