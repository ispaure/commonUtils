"""Reusable object-driven filesystem browser; applications supply domain behavior."""

from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from .. import pyside as qt
from .. import desktop_actions
from ...dirUtils import Directory
from ...filesystem import BrowserDetails, BrowserPanel, format_size, scan_folders
from .model import BrowserFileSystemModel, ByteSortModel, BrowserTree, _BrowserSelection
from .details import DetailsPanel
from .controls import ViewModeSelector, FolderSizeControl, ViewIcon
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
    index_updated = qt.Signal(object)
    index_progress = qt.Signal(str)
    index_state_changed = qt.Signal()

    def __init__(self, directory=None, parent=None, *, services=None, action_providers=(), folder_fields=None, calculate_folder_sizes=True, index_settings_path=None):
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
        self.index_settings_path = index_settings_path
        self.folder_pending = False
        self._index_paused = False
        self._changed_paths = set()
        self._index_priority_owner = object()
        from ...directory_index import directory_cache
        self.destroyed.connect(lambda obj=None, owner=self._index_priority_owner,
                               cache=directory_cache: cache.set_priority_folders(owner))
        self._full_index_refresh = False
        self.folder_root = None
        self.refresh_pending = False
        self._pending_detail_item = None
        self.stopping = False
        self.selected_object = None
        self.last_details = None
        self.cover_pixmap = qt.QPixmap()
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSizeConstraint(qt.QLayout.SizeConstraint.SetMinimumSize)
        self.search_bar = qt.QLineEdit()
        self.search_bar.setAccessibleName('Search indexed files and folders')
        self.search_bar.setPlaceholderText('Search this location and its subfolders')
        self.search_bar.setToolTip('Search names, ignoring case. Words match in any order; '
                                  '"quoted phrases" keep word order. Spaces, underscores and '
                                  'hyphens are equivalent in phrases.')
        layout.addLayout(self._create_navigation_controls())
        from .status import IndexStatusLabel, IndexActivityBar
        self.index_status = IndexStatusLabel()
        self.index_status.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.index_incomplete = False
        self._index_details_dialog = None
        self.index_details_button = qt.QPushButton('Index details…')
        self.index_details_button.setToolTip('Show saved scan errors and unfinished folders')
        self.index_details_button.clicked.connect(self.show_index_details)
        self.index_details_button.hide()
        self.index_activity = IndexActivityBar()
        self.index_activity.setRange(0, 0)
        self.index_activity.setTextVisible(False)
        self.index_activity.setAccessibleName('Background indexing in progress')
        self.index_activity.hide()
        self._create_views()
        layout.addWidget(self.splitter, 1)
        status_row = qt.QHBoxLayout()
        status_row.addWidget(self.index_status,1)
        self.index_activity.setFixedWidth(140)
        self.index_activity.setMaximumHeight(14)
        status_row.addWidget(self.index_activity)
        status_row.addWidget(self.index_details_button)
        status_row.addWidget(self.refresh_button)
        self.index_status.setMinimumHeight(self.refresh_button.sizeHint().height())
        layout.addLayout(status_row)
        self._create_preview_panel()
        self.file_actions = FileActions(self)
        from .keyboard import BrowserKeyboard
        self.keyboard = BrowserKeyboard(self)
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
        # Compatibility timer stays inactive: completed indexes never poll the tree.
        self.clear_search = qt.QShortcut(qt.QKeySequence(qt.Qt.Key.Key_Escape), self)
        self.clear_search.setContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.clear_search.activated.connect(self.close_search)
        self.find_shortcut = qt.QShortcut(qt.QKeySequence(qt.QKeySequence.StandardKey.Find), self)
        self.find_shortcut.setContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.find_shortcut.activated.connect(self.open_search)
        qt.QApplication.instance().aboutToQuit.connect(self.shutdown)
        if directory is not None:
            self.set_directory(directory)

    def _create_navigation_controls(self):
        self.navigation = NavigationBar(self)
        self.navigation.requested.connect(self.navigate)
        toolbar = qt.QHBoxLayout()
        toolbar.setSpacing(6)
        toolbar.addWidget(self.navigation, 1)
        controls = toolbar
        self.view_selector = ViewModeSelector(self)
        self.view_selector.setAccessibleName('Browser view')
        self.folder_size_button = FolderSizeControl(self)
        self.folder_size_slider = self.folder_size_button.slider
        controls.addWidget(self.folder_size_button)
        controls.addWidget(self.view_selector)
        self.preview_toggle = qt.QToolButton(self)
        self.preview_toggle.setText('Preview')
        self.preview_toggle.setIcon(qt.QIcon(ViewIcon(4)))
        self.preview_toggle.setIconSize(qt.QSize(20, 20))
        self.preview_toggle.setToolButtonStyle(qt.Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.preview_toggle.setCheckable(True)
        from ...settings import get_setting
        self.preview_toggle.setChecked(get_setting('FileBrowser', 'preview_enabled', True))
        self.preview_toggle.setText('Preview on' if self.preview_toggle.isChecked() else 'Preview off')
        self.preview_toggle.setToolTip('Show selection details, or current-folder properties when nothing is selected')
        self.preview_toggle.setAccessibleName('Show file and folder preview')
        self.preview_toggle.toggled.connect(self._preview_toggled)
        controls.addWidget(self.preview_toggle)
        controls.addWidget(self.view_selector.storage_controls)
        self.search_button = qt.QToolButton(self)
        self.search_button.setIcon(qt.QIcon(ViewIcon(6)))
        self.search_button.setIconSize(qt.QSize(22, 22))
        self.search_button.setCheckable(True)
        self.search_button.setAutoRaise(True)
        self.search_button.setAccessibleName('Search files and folders')
        self.search_button.setToolTip('Show or hide search (Ctrl/Cmd+F)')
        self.search_button.toggled.connect(self._search_toggled)
        controls.addWidget(self.search_button)
        self.storage_button = qt.QPushButton('Storage…')
        self.storage_button.clicked.connect(self.open_storage)
        self.storage_button.hide() # Legacy dialog API; Storage is now a view.
        self.refresh_button = qt.QPushButton('Refresh index')
        self.refresh_button.setToolTip('Check all files and saved sizes below the current folder')
        self.refresh_button.clicked.connect(self.refresh)
        self.index_pause_button = qt.QToolButton(self)
        self.index_pause_button.setText('Pause')
        self.index_pause_button.setToolTip('Pause this tab’s scan; saved search and sizes remain available')
        self.index_pause_button.clicked.connect(self._toggle_index_pause)
        self.index_pause_button.hide()
        # Retained as a hidden compatibility object; scanning has no pause UI.
        return toolbar

    def open_search(self):
        if self.stopping:
            return None
        self.search_button.setChecked(True)
        self.search_bar.setFocus()
        self.search_bar.selectAll()
        return self.index_search

    def close_search(self):
        if self.search_button.isChecked():
            self.search_button.setChecked(False)
        else:
            self._search_toggled(False)

    def _search_toggled(self, enabled):
        self.search_panel.setVisible(enabled)
        if enabled:
            self.search_bar.setFocus()
        else:
            self.search_bar.clear()
            self.views.currentWidget().setFocus()

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
        self.tree = BrowserTree()
        self.sort_model = ByteSortModel(self.model,self)
        self.tree.setModel(self.sort_model)
        self.tree.setSelectionModel(_BrowserSelection(self.sort_model,self.tree))
        self.tree.expanded.connect(lambda index: self.model.size_parents.add(self.model.filePath(self.sort_model.mapToSource(index))))
        self.tree.collapsed.connect(lambda index: self.model.size_parents.discard(self.model.filePath(self.sort_model.mapToSource(index))))
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
        self.views.directory_opened.connect(self._directory_opened)
        self.views.context_requested.connect(self._context_menu)
        self.views.activated.connect(self._activate)
        self.views.path_activated.connect(self._activate_path)
        self.views.idle.connect(self._maybe_idle)
        self.view_selector.currentIndexChanged.connect(self.views.set_mode)
        self.view_selector.currentIndexChanged.connect(lambda mode: self.folder_size_button.setEnabled(mode < 3))
        self.folder_size_slider.valueChanged.connect(self.views.set_icon_scale)
        self.splitter = qt.QSplitter()
        self.splitter.setChildrenCollapsible(False)
        self.list_stack = qt.QStackedWidget()
        self.list_stack.addWidget(self.views)
        from .index_search import IndexSearch
        self.index_search = IndexSearch(self)
        self.index_search.idle.connect(self._maybe_idle)
        self.list_stack.addWidget(self.index_search)
        self.files_panel = qt.QWidget()
        files_layout = qt.QVBoxLayout(self.files_panel)
        files_layout.setContentsMargins(0, 0, 0, 0)
        self.search_panel = qt.QWidget()
        search_layout = qt.QHBoxLayout(self.search_panel)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.addWidget(self.search_bar, 1)
        self.close_search_button = qt.QToolButton()
        self.close_search_button.setIcon(qt.QIcon(ViewIcon(7)))
        self.close_search_button.setIconSize(qt.QSize(20, 20))
        self.close_search_button.setAutoRaise(True)
        self.close_search_button.setAccessibleName('Close search')
        self.close_search_button.setToolTip('Close search and return to browsing (Esc)')
        self.close_search_button.clicked.connect(self.close_search)
        search_layout.addWidget(self.close_search_button)
        files_layout.addWidget(self.search_panel)
        files_layout.addWidget(self.list_stack, 1)
        self.search_panel.hide()
        self.splitter.addWidget(self.files_panel)

    def _create_preview_panel(self):
        from .preview import create_preview_panel
        create_preview_panel(self)

    def _preview_toggled(self, enabled):
        self.preview_toggle.setText('Preview on' if enabled else 'Preview off')
        self._update_preview_visibility(bool(self.selected_objects()))
        if enabled:
            self._selection_changed()

    def _preview_enabled(self):
        mode = self._preview_mode()
        return mode == 2 or mode != 3 and self.preview_toggle.isChecked()

    def _preview_mode(self):
        # Indexed search presents a list even when the underlying view is columns
        # or a storage chart; its selected results still deserve normal details.
        return 0 if self.index_search.active else self.views.currentIndex()

    def _update_preview_visibility(self, selected):
        from .preview import update_preview_visibility
        update_preview_visibility(self, selected)

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

    def set_directory(self, directory, *, navigation_root=None):
        path = directory.path if isinstance(directory, Directory) else Path(directory)
        path = path.absolute()
        if not path.is_dir():
            raise NotADirectoryError(path)
        root = Path(navigation_root).absolute() if navigation_root is not None else path
        if not root.is_dir() or (path != root and root not in path.parents):
            raise ValueError('Starting folder must be within the navigation root')
        self.navigation.set_library(root, directory=path)
        self.views.navigation_root = root
        self.model.setRootPath(str(root))
        self.views.set_root(path)

    def _directory_changed(self, path):
        from ...directory_index import directory_cache
        directory_cache.set_priority_folders(self._index_priority_owner, (path,))
        self.model.size_parents = {str(path)}
        self.index_search.scope_changed(path)
        if path != self.folder_root:
            self._update_watch_paths(path, (path,))
            self.refresh_folder_totals()

    def _directory_opened(self, path):
        # Reopening the same folder checks new items without checking on every
        # selection event (which also publishes directory_changed).
        from .index_policy import index_policy
        if path == self.folder_root and not self.folder_busy and index_policy(path=self.index_settings_path).refresh_on_revisit:
            from ...directory_index import directory_cache
            directory_cache.invalidate(path)
            self._changed_paths.add(path)
            self.refresh_folder_totals()

    def _update_watch_paths(self, root, paths):
        if self.stopping or root != self.navigation.directory:
            return
        from ...directory_index import directory_cache
        from ..._directory_exclusions import scan_exclusions, is_excluded
        exclusions = scan_exclusions(root, directory_cache.database)
        expected = {str(path) for path in paths if not is_excluded(path, exclusions)}
        previous = set(self.index_watcher.directories()) | set(self.index_watcher.files())
        if previous - expected: self.index_watcher.removePaths(list(previous - expected))
        if expected - previous: self.index_watcher.addPaths(list(expected - previous))

    def _indexed_path_changed(self, path):
        if self.stopping or not self.calculate_folder_sizes: return
        from .index_policy import index_policy
        if not index_policy(path=self.index_settings_path).watch_changes: return
        root = self.navigation.directory
        path = Path(path)
        if root is None or (path != root and root not in path.parents):
            return
        from ...directory_index import directory_cache
        from ..._directory_exclusions import scan_exclusions, is_excluded
        if is_excluded(Path(path), scan_exclusions(self.navigation.directory, directory_cache.database)):
            return
        directory_cache.invalidate(Path(path))
        self._changed_paths.add(Path(path))
        self._reconcile_pending = True
        self.reconcile_debounce.start()

    def _reconcile_index(self):
        if self.stopping or not self.calculate_folder_sizes or self._index_paused or self.folder_busy: return
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
        standard('Move to Trash / Recycle Bin…', lambda: self.file_actions.delete(context.selection),
                 enabled=mutating, key=qt.QKeySequence.StandardKey.Delete)
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
        self._activate_item(item)

    def _activate_path(self, path):
        """Cached chart paths can be hidden or absent from Qt's live model."""
        self._activate_item(self.model.object_for_path(path))

    def _activate_item(self, item):
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
        self._update_preview_visibility(bool(items))
        self._pending_detail_item = None
        if self.busy:
            self.refresh_pending = True
            return
        self._clear_details()
        if not self._preview_enabled():
            self.selected_object = items[0] if len(items) == 1 else None
            return
        if self._preview_mode() == 2 and (len(items) != 1 or isinstance(items[0], Directory)):
            self.selected_object = items[0] if len(items) == 1 else None
            return
        if len(items) == 1:
            self.load(items[0])
        elif len(items) > 1:
            self.heading.setText(f'{len(items)} items selected')
            self.message.setText('Right-click the selection for available actions.')
        else:
            if self.navigation.directory is not None:
                self.load(Directory(self.navigation.directory))

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
                               'Cached; deeper contents may have changed' if stats.stale else 'Up to date'))
                if self.folder_fields is not None:
                    fields.extend(self.folder_fields(item, stats))
                if stats.skipped:
                    fields.append(('Excluded links / unreadable items', stats.skipped))
        return BrowserDetails(tuple(fields))

    def load(self, item, *, preserve=False):
        if self.busy:
            # Public callers can request a file while the default folder details
            # are still loading. Retain that explicit request for the next worker.
            self._pending_detail_item = item
            self._pending_detail_preserve = preserve
            self.selected_object = item
            self.refresh_pending = True
            return
        self._pending_detail_item = None
        self._preserving_details = preserve
        if not preserve:
            self._clear_details()
        self.selected_object = item
        self._update_preview_visibility(True)
        self.heading.setText(item.name if isinstance(item, Directory) else item.file_name)
        if not preserve:
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
        if self._preserving_details:
            selected = self.selected_object
            self._clear_details()
            self.selected_object = selected
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
        if self.cover_pixmap.isNull():
            return
        ratio = self.devicePixelRatioF()
        preview = self.cover_pixmap.scaled(round(min(320, max(1, self.cover.contentsRect().width())) * ratio),
                                          round(440 * ratio),
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
            item = self._pending_detail_item
            if item is not None:
                self.load(item, preserve=getattr(self, '_pending_detail_preserve', False))
            else:
                self._selection_changed()

    def refresh_item(self, path):
        self._changed_paths.add(Path(path).parent)
        self.model.invalidate(path)
        self.views.covers.invalidate(path)
        if self.selected_object is not None and self.selected_object.path == Path(path):
            self._selection_changed()
        self.refresh_folder_totals()

    def refresh(self):
        from ...directory_index import directory_cache
        directory_cache.invalidate(self.navigation.directory)
        self._full_index_refresh = True
        self._index_paused = False
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
            self.index_activity.hide()
            if self.folder_busy:
                self.folder_operation.requestInterruption()
            self._index_progressed('Indexing paused; cached results remain available.')
        else:
            self.refresh_folder_totals()
        if isinstance(self.selected_object, Directory):
            self._selection_changed()

    def refresh_changed(self, paths=()):
        """Reconcile known file-operation changes without revalidating the tree."""
        self._changed_paths.update(Path(path) for path in paths or (self.navigation.directory,))
        self.refresh_folder_totals()
        self._selection_changed()
        self.refreshed.emit()

    def _toggle_index_pause(self):
        self._index_paused = not self._index_paused
        if self._index_paused:
            self.folder_pending = False
            self.reconcile_debounce.stop()
            if self.folder_busy:
                self._changed_paths.update(self._active_index_changes)
                self._full_index_refresh |= self._active_index_full
                self.folder_operation.requestInterruption()
            self.index_status.setText('Indexing paused · Saved search and sizes available')
            self.index_progress.emit(self.index_status.text())
        else:
            self.refresh_folder_totals()
        self._update_pause_button()

    def _update_pause_button(self):
        self.index_details_button.setVisible(self.index_incomplete and not getattr(self, 'workspace_status', False))
        self.refresh_button.setVisible(not self.folder_busy and not getattr(self, 'workspace_status', False))
        self.refresh_button.setEnabled(self.calculate_folder_sizes and self.navigation.directory is not None)
        self.index_pause_button.setText('Resume' if self._index_paused else 'Pause')
        self.index_pause_button.hide()

    def refresh_folder_totals(self):
        if not self.calculate_folder_sizes:
            return
        root = self.navigation.directory
        if self.folder_busy:
            if (root is not None and not self._index_paused and not self._full_index_refresh
                    and not self._active_index_full and not self._changed_paths and not self.folder_pending
                    and self.folder_operation.retarget(root)):
                self.folder_root = root
                return
            self.folder_pending = True
            self._changed_paths.update(self._active_index_changes)
            self._full_index_refresh |= self._active_index_full
            self.folder_operation.requestInterruption()
            return
        if root is None or self.stopping:
            return
        from ...directory_index import directory_cache
        from ...operations import OperationCancelled
        full = self._full_index_refresh
        paused = self._index_paused
        changes = tuple(sorted(self._changed_paths))
        from .index_policy import index_policy
        policy = index_policy(path=self.index_settings_path)
        read_cache = paused or not full and not changes and (not policy.scan_on_open or not policy.refresh_cached_on_startup)
        cached_only = read_cache or not full and not changes and directory_cache.was_checked_this_session(root)
        self._loading_cached_only = cached_only
        if not paused:
            self._full_index_refresh = False
            self._changed_paths.clear()
            self._reconcile_pending = False
        self._active_index_changes = changes if not paused else ()
        self._active_index_full = full and not paused
        self._active_index_recursive = full or policy.recursive_on_open
        self.folder_busy = True
        self.index_activity.setVisible(not cached_only and not getattr(self, 'workspace_status', False))
        self.folder_pending = False
        self.folder_root = root
        self._update_pause_button()
        self.index_status.setText('Loading saved sizes…' if cached_only else 'Checking saved index…')
        def scanner(path, cancelled, *, report, reuse_for):
            try:
                if read_cache:
                    if not paused:
                        directory_cache.repair_cached_exclusions(path, cancelled=cancelled, report=report)
                    snapshot = directory_cache.peek(path, cancelled=cancelled)
                else:
                    snapshot = None
                if not read_cache or snapshot is None and not paused and policy.scan_on_open:
                    snapshot = directory_cache.reconcile_folder(path, changes=changes, full=full, once=True,
                                                               cancelled=cancelled, report=report,
                                                               recursive_initial=policy.recursive_on_open)
                return snapshot.folder_stats(children_of=path, cancelled=cancelled) if snapshot else None
            except OperationCancelled:
                return None
        self.folder_operation = FolderOperation(root, scanner, self,
            request_key=('cached' if read_cache else 'full' if full else 'reconcile', changes),
            background_priority=policy.background_priority)
        self.folder_operation.updated.connect(self._folders_progressed)
        self.folder_operation.progress.connect(lambda message: self._index_progressed(message)
                                               if self.folder_root == self.navigation.directory else None)
        self.folder_operation.watch_paths.connect(self._update_watch_paths)
        self.folder_operation.completed.connect(lambda result, error: self._folders_loaded(self.folder_operation.visible_root, result, error))
        self.folder_operation.finished.connect(self._folders_finished)
        self.folder_operation.start()
        if self.folder_operation.root != root:
            self._loading_cached_only = False
            self.index_activity.setVisible(not getattr(self, 'workspace_status', False))
            self._update_pause_button()
        self.index_state_changed.emit()

    def _folders_progressed(self, root, result):
        if self.calculate_folder_sizes and root == self.navigation.directory and result and not self.folder_pending and not self.stopping:
            if self.model.folder_totals == result:
                return
            self.model.set_folder_totals(result)
            self.index_search.refresh()
            self.index_updated.emit(root)
            if not self.folder_busy:
                self.index_status.setText('Cached or partial sizes available.')
            if (isinstance(self.selected_object, Directory) and not self.refresh_pending
                    and self._preview_enabled() and not self.preview_panel.isHidden()):
                self.load(self.selected_object, preserve=True)

    def _folders_loaded(self, root, result, error=''):
        if error and root == self.navigation.directory and not self.stopping:
            self.index_status.setText('Index unavailable. Any cached sizes remain available; refresh to retry.')
            self.index_progress.emit(self.index_status.text())
        if self.calculate_folder_sizes and root == self.navigation.directory and result is not None and not self.folder_pending and not self.stopping:
            changed = self.model.folder_totals != result
            self.model.set_folder_totals(result)
            self.index_search.refresh()
            stats = result.get(root)
            self.index_incomplete = stats is not None and not stats.complete
            self.index_details_button.setVisible(self.index_incomplete and not getattr(self, 'workspace_status', False))
            checked = datetime.fromtimestamp(stats.scanned_at).strftime('%b %d at %H:%M:%S') if stats else 'just now'
            if self._index_paused:
                message = f'Indexing paused · Saved sizes · Last checked {checked}'
            elif stats is not None and not stats.complete:
                message = ('Visible contents indexed · Subtree sizes are partial · Refresh index scans deeper'
                           if not self._active_index_recursive else
                           'Index incomplete · Index details shows unfinished work · Refresh to retry')
            elif stats is not None and stats.stale:
                message = f'Folder last checked {checked} · Saved subtree sizes · Refresh checks deeper contents'
            else:
                message = f'Index and sizes up to date · Checked {checked}'
            self.index_status.setText(message)
            if changed:
                self.index_updated.emit(root)
            self.index_progress.emit(self.index_status.text())
            if (changed and isinstance(self.selected_object, Directory) and not self.refresh_pending
                    and self._preview_enabled() and not self.preview_panel.isHidden()):
                self.load(self.selected_object, preserve=True)

    def _index_progressed(self, message):
        from .status import private_status
        message = private_status(message)
        if not self.stopping and self.calculate_folder_sizes and not self._index_paused:
            self.index_status.setText(message)
            self.index_progress.emit(message)
        elif message.startswith('Indexing paused'):
            self.index_status.setText(message)
            self.index_progress.emit(message)

    def show_index_details(self):
        from .index_details import IndexDetailsDialog
        if self._index_details_dialog is None:
            self._index_details_dialog = IndexDetailsDialog(self)
            self._index_details_dialog.destroyed.connect(self._index_details_closed)
        self._index_details_dialog.show()
        self._index_details_dialog.raise_()

    def _index_details_closed(self):
        self._index_details_dialog = None

    def _folders_finished(self):
        self.folder_busy = False
        self.index_activity.hide()
        self.index_state_changed.emit()
        self._update_pause_button()
        self.folder_operation.deleteLater()
        if self.stopping:
            self._maybe_idle()
        elif (self.folder_operation.visible_root != self.folder_operation.root
              and not self._index_paused and not self.folder_pending and not self._reconcile_pending):
            from ...directory_index import directory_cache
            if not directory_cache.was_checked_this_session(self.navigation.directory):
                self.refresh_folder_totals()
            else:
                self.index_search.refresh()
        elif self.folder_pending or (self._reconcile_pending and not self._index_paused):
            self._reconcile_pending = False
            self.refresh_folder_totals()
        else:
            self.index_search.refresh()

    def stop(self):
        if self._index_details_dialog is not None:
            self._index_details_dialog.close()
        from ...directory_index import directory_cache
        directory_cache.set_priority_folders(self._index_priority_owner)
        self.stopping = True
        self.reconcile_debounce.stop(); self.reconcile_timer.stop()
        self.index_search.stop()
        for window in tuple(self._scan_windows):
            window.close()
        self.views.stop()
        self.file_actions.stop()
        if self.folder_busy:
            self.folder_operation.requestInterruption()
        return self.busy or self.folder_busy or self.views.cover_busy or self.views.storage.busy or self.file_actions.busy or self._scan_busy()

    def _maybe_idle(self):
        if self.stopping and not (self.busy or self.folder_busy or self.views.cover_busy or self.views.storage.busy or self.file_actions.busy or self._scan_busy()):
            self.idle.emit()

    def shutdown(self):
        self.stop()
        self.views.storage.wait()
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
