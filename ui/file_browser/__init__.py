"""Reusable object-driven filesystem browser; applications supply domain behavior."""

from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from .. import pyside as qt
from .. import desktop_actions
from ...filesystem.directories import Directory
from ...filesystem import BrowserDetails, BrowserPanel, format_size, scan_folders
from .model import BrowserFileSystemModel, ByteSortModel, BrowserTree, _BrowserSelection
from .details import DetailsPanel
from .controls import ViewModeSelector, FolderSizeControl, ViewIcon, create_search_toggle, create_search_panel
from ..appearance.icons import set_painted_icon
from .navigation import NavigationBar
from ..tasks.operations import Operation
from .views import FileViews
from .editing import FilenameDelegate
from .file_actions import FileActions, clipboard_files
from .indexing import BrowserIndexing, IndexPriorityLease


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


class FileBrowser(BrowserIndexing, qt.QWidget):
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

    def __init__(self, directory=None, parent=None, *, services=None, action_providers=(), folder_fields=None, calculate_folder_sizes=True, index_settings_path=None, directory_handler=None, directory_boundary=None, column_navigation=True):
        super().__init__(parent)
        from ..appearance.styling import bind_font
        bind_font(self, 'browser')
        self.idle.connect(self.close)
        self.directory_handler = directory_handler
        self.directory_boundary = directory_boundary
        self.column_navigation = bool(column_navigation)
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
        from ...filesystem.index import directory_cache
        self._index_priority_lease = IndexPriorityLease(self, directory_cache, self._index_priority_owner)
        if directory_cache.shared_activity is not None:
            directory_cache.shared_activity.connect(self._shared_index_changed)
        self._full_index_refresh = False
        self.folder_root = None
        self.refresh_pending = False
        self._pending_detail_item = None
        self.stopping = False
        self.network_location = False
        self.selected_object = None
        self.last_details = None
        self.cover_pixmap = qt.QPixmap()
        from .assembly import BrowserControls
        self.controls = BrowserControls(self)
        self.controls.build()
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
        self.clear_search = qt.QShortcut(qt.QKeySequence(qt.Qt.Key.Key_Escape), self)
        self.clear_search.setContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.clear_search.activated.connect(self.close_search)
        self.find_shortcut = qt.QShortcut(qt.QKeySequence(qt.QKeySequence.StandardKey.Find), self)
        self.find_shortcut.setContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.find_shortcut.activated.connect(self.open_search)
        qt.QApplication.instance().aboutToQuit.connect(self.shutdown)
        if directory is not None:
            self.set_directory(directory)


    def open_search(self):
        if self.network_location:
            return None
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
        if self.stopping or self.navigation.directory is None or self.network_location:
            return None
        window = kind(self)
        self._scan_windows.append(window)
        window.idle.connect(self._maybe_idle)
        window.destroyed.connect(lambda: self._scan_windows.remove(window) if window in self._scan_windows else None)
        window.show()
        return window

    def _scan_busy(self):
        return self.index_search.busy or any(window.busy for window in self._scan_windows)



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
        if self.handle_directory(path):
            return
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
        self._set_network_location(path)
        from ...filesystem.index import directory_cache
        directory_cache.set_priority_folders(self._index_priority_owner, () if self.network_location else (path,))
        self.model.size_parents = {str(path)}
        self.index_search.scope_changed(path)
        if path != self.folder_root:
            self._update_watch_paths(path, (path,))
            self.refresh_folder_totals()

    def _set_network_location(self, path):
        from ...filesystem.network import is_network_location
        network = is_network_location(path)
        changed = self.network_location != network
        self.network_location = network
        self.model.network_location = network
        self.model.setOption(qt.QFileSystemModel.Option.DontWatchForChanges, network)
        for mode in (3, 4):
            self.view_selector.buttons[mode].setEnabled(not network)
            self.view_selector.buttons[mode].setToolTip('Size map disabled for network drives' if network
                else ('Treemap view' if mode == 3 else 'Radial view'))
        self.refresh_button.setToolTip('Indexing and scans disabled for network drives' if network
            else 'Check all files and saved sizes below the current folder')
        self.search_button.setEnabled(not network)
        self.search_button.setToolTip('Indexed search disabled for network drives' if network
            else 'Show or hide search (Ctrl/Cmd+F)')
        if network:
            self.reconcile_debounce.stop()
            self._changed_paths.clear(); self._full_index_refresh = False
            self.folder_pending = False; self._reconcile_pending = False
            if self.folder_busy: self.folder_operation.requestInterruption()
            watches = self.index_watcher.directories() + self.index_watcher.files()
            if watches: self.index_watcher.removePaths(watches)
            self.close_search()
            self.model.set_folder_totals({})
            self.index_incomplete = False
            self.index_activity.hide(); self.index_details_button.hide()
            self.index_status.setText('Indexing and scans disabled for network drives')
            self.index_progress.emit(self.index_status.text())
            if self.views.currentIndex() == 3: self.view_selector.setCurrentIndex(0)
        elif changed:
            self.index_status.setText('Loading saved sizes…')
        self._update_index_controls()
        self.index_state_changed.emit()

    def _directory_opened(self, path):
        # Reopening the same folder checks new items without checking on every
        # selection event (which also publishes directory_changed).
        from .index_policy import index_policy
        if not self.network_location and path == self.folder_root and not self.folder_busy and index_policy(path=self.index_settings_path).refresh_on_revisit:
            from ...filesystem.index import directory_cache
            directory_cache.invalidate(path)
            self._changed_paths.add(path)
            self.refresh_folder_totals()

    def _update_watch_paths(self, root, paths):
        if self.stopping or self.network_location or root != self.navigation.directory:
            return
        from ...filesystem.index import directory_cache
        from ...filesystem.index.exclusions import scan_exclusions, is_excluded
        exclusions = scan_exclusions(root, directory_cache.database)
        expected = {str(path) for path in paths if not is_excluded(path, exclusions)}
        previous = set(self.index_watcher.directories()) | set(self.index_watcher.files())
        if previous - expected: self.index_watcher.removePaths(list(previous - expected))
        if expected - previous: self.index_watcher.addPaths(list(expected - previous))

    def _indexed_path_changed(self, path):
        if self.stopping or self.network_location or not self.calculate_folder_sizes: return
        from .index_policy import index_policy
        if not index_policy(path=self.index_settings_path).watch_changes: return
        root = self.navigation.directory
        path = Path(path)
        if root is None or (path != root and root not in path.parents):
            return
        from ...filesystem.index import directory_cache
        from ...filesystem.index.exclusions import scan_exclusions, is_excluded
        if is_excluded(Path(path), scan_exclusions(self.navigation.directory, directory_cache.database)):
            return
        directory_cache.invalidate(Path(path))
        self._changed_paths.add(Path(path))
        self._reconcile_pending = True
        self.reconcile_debounce.start()

    def _reconcile_index(self):
        if self.stopping or self.network_location or not self.calculate_folder_sizes or self._index_paused or self.folder_busy: return
        self._reconcile_pending = False
        self.refresh_folder_totals()

    def handle_directory(self, path):
        return bool(self.directory_handler and self.directory_handler(Path(path)))

    def navigate(self, path):
        path = Path(path)
        if self.handle_directory(path):
            return
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
        context = self.context(item) if item is not None else BrowserContext(self, ())
        destination = (item.path if isinstance(item, Directory) else None) if item else (
            Path(directory) if directory is not None else self.views.browsing_directory())
        menu = qt.QMenu(self)
        def current_index():
            # Keep paths in action closures, not native indexes whose destruction
            # can be delayed until after the filesystem model is torn down.
            if self.stopping or not (item.path.exists() or item.path.is_symlink()):
                return qt.QModelIndex()
            return self.model.index(str(item.path))
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
                standard('Open', lambda: self._activate(current_index()), enabled=single)
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
        from .link_actions import add_link_actions
        add_link_actions(menu, self, context.selection, destination, mutating)
        if item is None:
            menu.addSeparator()
            standard('Refresh', self.refresh)
            standard(desktop_actions.reveal_label(), lambda: desktop_actions.reveal(destination),
                     enabled=destination is not None)
            return menu
        menu.addSeparator()
        standard('Rename', lambda: self.file_actions.rename(current_index()), enabled=mutating and single,
                 key=qt.Qt.Key.Key_F2)
        contributions = self._selection_actions(context)
        for entry in self._ordered_actions(entry for entry in contributions.values() if entry.category == 'rename'):
            self._add_contributed_action(menu, entry, context, enabled=mutating)
        standard('Move to Trash / Recycle Bin…', lambda: self.file_actions.delete(context.selection),
                 enabled=mutating, key=qt.QKeySequence.StandardKey.Delete)
        groups = {}
        for entry in contributions.values():
            if entry.category != 'rename':
                groups.setdefault(entry.source or 'Extensions', []).append(entry)
        for source, entries in sorted(groups.items(), key=lambda group: (min(entry.order for entry in group[1]), group[0].casefold())):
            menu.addSection(source)
            for entry in self._ordered_actions(entries):
                self._add_contributed_action(menu, entry, context, enabled=mutating)
        menu.addSeparator()
        standard(desktop_actions.reveal_label(), lambda: desktop_actions.reveal(item.path))
        return menu

    def _selection_actions(self, context):
        """Capture providers once per selected item; the first action for a key wins."""
        contributions = {}
        for selected in context.selection:
            entries = list(selected.browser_actions(context))
            for provider in self.action_providers:
                entries.extend(provider(selected, context))
            for entry in entries:
                contributions.setdefault(entry.key, entry)
        return contributions

    @staticmethod
    def _ordered_actions(entries):
        return sorted(entries, key=lambda entry: (entry.order, entry.title.casefold()))

    def _add_contributed_action(self, menu, entry, context, *, enabled):
        """Bind each menu action to its captured contribution and selection."""
        action = menu.addAction(entry.title)
        action.setEnabled(enabled)
        source = entry.source or 'Extensions'
        action.setToolTip(f'Provided by {source}')
        action.setProperty('source', source)
        action.triggered.connect(lambda checked=False: self._run(lambda: entry.run(context)))

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
        if self.handle_directory(item.path if isinstance(item, Directory) else item.path.parent):
            return
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
                fields.append(('Total size', 'Disabled for network drives' if self.network_location else
                               'Not calculated' if not self.calculate_folder_sizes else
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
        if not self.network_location:
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

    def stop(self):
        if self._index_details_dialog is not None:
            self._index_details_dialog.close()
        from ...filesystem.index import directory_cache
        directory_cache.set_priority_folders(self._index_priority_owner)
        self.stopping = True
        self.reconcile_debounce.stop()
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
