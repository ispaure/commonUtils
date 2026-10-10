"""Coordinate filesystem views, selection and asynchronous thumbnail loading."""

from collections import deque
from pathlib import Path
from ...dirUtils import Directory
from .. import pyside as qt
from ..operations import Operation
from .tiles import ResponsiveTileView
from .columns import FolderColumnView, ColumnDelegate
from .thumbnails import CoverModel


class FileViews(qt.QStackedWidget):
    selection_changed = qt.Signal()
    context_requested = qt.Signal(object)
    activated = qt.Signal(object)
    path_activated = qt.Signal(object)
    idle = qt.Signal()
    directory_changed = qt.Signal(object)
    directory_opened = qt.Signal(object)

    def __init__(self, model, tree, parent=None):
        super().__init__(parent)
        self.model = model
        self._switching = False
        self.navigation_root = None
        self._column_extended = False
        self._column_selection_pending = False
        self._column_last_selection = None
        self._hidden_root = None
        self._hidden_filter = None
        self.tree = tree
        self.covers = CoverModel(model, self)
        self.tiles = ResponsiveTileView()
        self.tiles.setModel(self.covers)
        self.tiles.setViewMode(qt.QListView.ViewMode.IconMode)
        self.tiles.setResizeMode(qt.QListView.ResizeMode.Adjust)
        self.tiles.setMovement(qt.QListView.Movement.Static)
        self.tiles.setIconSize(qt.QSize(120, 165))
        self.tiles.setGridSize(qt.QSize(170, 205))
        self.tiles.setWordWrap(True)
        self.columns = FolderColumnView()
        self.columns.setModel(model)
        self.columns.setColumnWidths([240, 240, 240, 240])
        self.cover_queue = deque()
        self.cover_busy = False
        self.closing = False
        self.cover_path = None
        self.tiles.metrics_changed.connect(self._tile_metrics)
        self.covers.cover_requested.connect(self._request_cover)
        self.columns.column_context_requested.connect(self._context)
        self.columns.selection_input.connect(self._column_input)
        for view in (tree, self.tiles, self.columns):
            self.addWidget(view)
            view.setSelectionMode(qt.QAbstractItemView.SelectionMode.ExtendedSelection)
            view.setEditTriggers(qt.QAbstractItemView.EditTrigger.SelectedClicked | qt.QAbstractItemView.EditTrigger.EditKeyPressed)
            view.setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)
            view.customContextMenuRequested.connect(lambda point, target=view: self._context(target, point))
            if view is self.columns:
                view.selectionModel().selectionChanged.connect(self._queue_column_selection)
                view.selectionModel().currentChanged.connect(self._queue_column_selection)
            else:
                view.selectionModel().selectionChanged.connect(lambda *args, target=view: self._selection(target))
            view.doubleClicked.connect(lambda index: self.activated.emit(self.source_index(index)))
        from .storage_view import StorageView
        self.storage = StorageView(parent)
        self.addWidget(self.storage)
        self.storage.selection_changed.connect(self.selection_changed)
        self.storage.activated.connect(self._storage_activated)
        self.storage.context_requested.connect(self._storage_context)
        self.storage.idle.connect(self.idle)
        self.root = None

    def source_index(self, index):
        if isinstance(index.model(),qt.QAbstractProxyModel):
            return index.model().mapToSource(index)
        return index

    def _storage_activated(self, path):
        index = self.model.index(str(path))
        if index.isValid():
            self.activated.emit(index)
        else:
            self.path_activated.emit(path)

    def _storage_context(self, path, position):
        self.context_directory = self.root
        self.context_position = position
        self.context_requested.emit(self.model.index(str(path)))

    def selected_rows(self):
        if self.currentIndex() == 3:
            index = self.model.index(str(self.storage.selected_path)) if self.storage.selected_path else qt.QModelIndex()
            return [index] if index.isValid() else []
        rows = list(dict.fromkeys(self.source_index(index) for index in
                                 self.currentWidget().selectionModel().selectedIndexes() if index.column() == 0))
        if self.currentWidget() is self.columns:
            current = self.columns.currentIndex()
            # QColumnView retains selected ancestors as its visual trail. They
            # aren't a user multi-selection in the currently active column.
            rows = [index for index in rows if index.parent() == current.parent()]
            if current in rows and not self._column_extended:
                return [current]
        return rows

    def _queue_column_selection(self, *args):
        if self._switching:
            return
        if not self._column_selection_pending:
            self._column_selection_pending = True
            qt.QTimer.singleShot(0, self, self._finish_column_selection)

    def _column_input(self, modifiers):
        extended = bool(modifiers & (qt.Qt.KeyboardModifier.ControlModifier |
                        qt.Qt.KeyboardModifier.MetaModifier | qt.Qt.KeyboardModifier.ShiftModifier))
        if extended and not self._column_extended:
            rows = self.selected_rows()
            if rows:
                # Start extending the real selection rather than Qt's retained
                # trail, including directories from a previously visited branch.
                self.columns.selectionModel().select(rows[-1], qt.QItemSelectionModel.SelectionFlag.ClearAndSelect |
                                                     qt.QItemSelectionModel.SelectionFlag.Rows)
        self._column_extended = extended

    def _finish_column_selection(self):
        self._column_selection_pending = False
        key = self._column_selection_key()
        if key == self._column_last_selection:
            return
        self._column_last_selection = key
        self._selection(self.columns)

    def _column_selection_key(self):
        return (self.root, tuple(self.model.filePath(index) for index in self.selected_rows()),
                self.model.filePath(self.columns.currentIndex()))

    def current_index(self):
        if self.currentIndex() == 3:
            rows = self.selected_rows()
            return rows[0] if rows else qt.QModelIndex()
        return self.source_index(self.currentWidget().currentIndex())

    def browsing_directory(self):
        if self.currentIndex() == 3:
            return self.root
        selected = self.selected_rows()
        index = self.current_index()
        if not any(index == item for item in selected):
            index = selected[-1] if selected else qt.QModelIndex()
        if index.isValid():
            path = Path(self.model.filePath(index))
            directory = path if self.currentIndex() == 2 and isinstance(self.model.item(index), Directory) else path.parent
            if directory == self.root or self.root in directory.parents:
                return directory
        return self.root

    def _selection(self, view):
        if view is self.currentWidget() and not self._switching:
            self.directory_changed.emit(self.browsing_directory())
            self.selection_changed.emit()

    def _context(self, view, point):
        if view is self.currentWidget() or (self.currentWidget() is self.columns and self.columns.isAncestorOf(view)):
            self.context_directory = Path(self.model.filePath(self.source_index(view.rootIndex())))
            self.context_position = view.viewport().mapToGlobal(point)
            self.context_requested.emit(self.source_index(view.indexAt(point)))

    def select_source(self, source):
        if self.currentIndex() == 3:
            self.storage.select_path(Path(self.model.filePath(source)))
            return
        view = self.currentWidget()
        index = self.covers.mapFromSource(source) if view is self.tiles else source
        view.selectionModel().setCurrentIndex(index, qt.QItemSelectionModel.SelectionFlag.ClearAndSelect |
                                              qt.QItemSelectionModel.SelectionFlag.Rows)
        view.scrollTo(index)
        view.setFocus()

    def edit_name(self, source):
        if self.currentIndex() == 3:
            self.storage.browser.view_selector.setCurrentIndex(0)
        source = self.source_index(source).siblingAtColumn(0)
        view = self.currentWidget()
        index = self.covers.mapFromSource(source) if view is self.tiles else source
        if view is self.columns:
            view = next((child for child in self.columns.findChildren(qt.QListView)
                         if child.isVisible() and child.rootIndex() == source.parent()), self.columns)
        view.selectionModel().setCurrentIndex(index, qt.QItemSelectionModel.SelectionFlag.ClearAndSelect |
                                              qt.QItemSelectionModel.SelectionFlag.Rows)
        view.setFocus()
        view.edit(index)

    def set_root(self, path):
        self.root = Path(path)
        if (self._hidden_root is not None and self.root != self._hidden_root
                and self._hidden_root not in self.root.parents):
            self.model.setFilter(self._hidden_filter)
            self._hidden_root = self._hidden_filter = None
        index = self.model.index(str(path))
        if not index.isValid():
            # Explicitly opening a hidden folder is valid even when it is
            # excluded from the parent listing or not loaded by Qt yet.
            if self._hidden_filter is None:
                self._hidden_filter = self.model.filter()
                self._hidden_root = self.root
            self.model.setFilter(self._hidden_filter | qt.QDir.Filter.Hidden)
            index = self.model.setRootPath(str(path))
        for view in (self.tree, self.tiles, self.columns):
            blocker = qt.QSignalBlocker(view.selectionModel())
            view.clearSelection()
            view.setCurrentIndex(qt.QModelIndex())
            view.setRootIndex(self.covers.mapFromSource(index) if view is self.tiles else index)
            blocker.unblock()
        self.storage.set_root(self.root)
        self.tree.collapseAll()
        if self.currentWidget() is self.columns:
            self._column_last_selection = self._column_selection_key()
        self.directory_changed.emit(self.root)
        self.selection_changed.emit()
        self.directory_opened.emit(self.root)

    def set_mode(self, mode):
        from ...network_filesystems import is_network_location
        if mode >= 3 and self.root is not None and is_network_location(self.root):
            return
        chart_mode = max(0, mode - 3)
        mode = min(mode, 3)  # Both storage buttons share the established storage widget.
        selected = self.selected_rows()
        directory = self.browsing_directory()
        if mode == 2:
            # A directory already opened in another mode belongs in the first
            # column, with its contents in the next one.
            focus = selected[-1] if selected else self.model.index(str(directory))
            parent = Path(self.model.filePath(focus.parent())) if focus.parent().isValid() else None
            scope = self.navigation_root
            if (focus.isValid() and parent is not None
                    and (scope is None or parent == scope or scope in parent.parents)):
                directory = parent
                selected = selected or [focus]
        if directory != self.root:
            self.set_root(directory)
        self.setCurrentIndex(mode)
        if mode == 3:
            self.storage.chart_selector.setCurrentIndex(chart_mode)
            self.storage.set_root(directory)
            if selected:
                self.storage.select_path(Path(self.model.filePath(selected[-1])))
            self.directory_changed.emit(self.root)
            self.selection_changed.emit()
            return
        selection = self.currentWidget().selectionModel()
        if mode == 2:
            self._column_extended = len(selected) > 1
        self._switching = True
        selection.clearSelection()
        for source in selected:
            index = self.covers.mapFromSource(source) if mode == 1 else source
            selection.select(index, qt.QItemSelectionModel.SelectionFlag.Select | qt.QItemSelectionModel.SelectionFlag.Rows)
            selection.setCurrentIndex(index, qt.QItemSelectionModel.SelectionFlag.NoUpdate)
        self._switching = False
        if selected:
            self.currentWidget().scrollTo(index)
        if mode == 2:
            self._column_last_selection = self._column_selection_key()
        self.directory_changed.emit(self.browsing_directory())
        self.selection_changed.emit()

    def set_icon_scale(self, percent):
        self.tiles.set_folder_scale(percent)
        size = round(16 * percent / 50)
        for view in (self.tree, self.columns):
            view.setIconSize(qt.QSize(size, size))

    def _tile_metrics(self, size, ratio):
        if self.covers.set_resolution(size, ratio):
            self.cover_queue.clear()
            self.tiles.viewport().update()

    def _request_cover(self, path):
        from ...network_filesystems import is_network_location
        if self.closing or is_network_location(path):
            return
        qt.QTimer.singleShot(0, lambda: self._enqueue_cover(path))

    def _visible_cover(self, path):
        index = self.covers.mapFromSource(self.model.index(path))
        return self.currentIndex() == 1 and self.tiles.visualRect(index).intersects(self.tiles.viewport().rect())

    def _enqueue_cover(self, path):
        if self.closing or not self._visible_cover(path):
            self.covers.requested.discard(path)
            return
        if path not in self.cover_queue:
            self.cover_queue.append(path)
        self._next_cover()

    def _next_cover(self):
        if self.cover_busy or self.closing or not self.cover_queue:
            return
        self.cover_path = self.cover_queue.popleft()
        path = self.cover_path
        if not self._visible_cover(path):
            self.covers.requested.discard(path)
            qt.QTimer.singleShot(0, self._next_cover)
            return
        self.cover_busy = True
        item = self.model.item(self.model.index(path))
        size, ratio = self.covers.render_size, self.covers.device_ratio
        self.operation = Operation(lambda: item.browser_thumbnail(size), self)
        revision = self.covers.revisions.get(path, 0)
        self.operation.completed.connect(lambda data, error: self._cover_loaded(path, revision, data or b'', ratio, size))
        self.operation.finished.connect(self._cover_finished)
        self.operation.start()

    def _cover_loaded(self, path, revision, data, ratio=1.0, size=None):
        if revision == self.covers.revisions.get(path, 0):
            self.covers.complete(path, data, ratio, size)
        else:
            self.covers.requested.discard(path)
            self.tiles.viewport().update()

    def _cover_finished(self):
        self.cover_busy = False
        self.operation.deleteLater()
        if self.closing:
            self.idle.emit()
        else:
            self._next_cover()

    def stop(self):
        self.closing = True
        self.cover_queue.clear()
        storage_busy = self.storage.stop()
        return self.cover_busy or storage_busy
