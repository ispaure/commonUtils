"""Shared item views; model adapters own identity, ancestry and source access."""

from collections import deque
from ...runtime.browsing import BrowseRole
from threading import Event
from .. import pyside as qt
from ..entry_views import configure_entry_selection
from ..tasks.operations import Operation
from .tiles import ResponsiveTileView
from .columns import FolderColumnView, ColumnDelegate
from .thumbnails import CoverModel


class BrowserViews(qt.QStackedWidget):
    selection_changed = qt.Signal()
    context_requested = qt.Signal(object)
    activated = qt.Signal(object)
    path_activated = qt.Signal(object)
    idle = qt.Signal()
    directory_changed = qt.Signal(object)
    directory_opened = qt.Signal(object)

    def __init__(self, model, tree, parent=None, *, directory_handler=None, storage=False, column_navigation=True):
        super().__init__(parent)
        self.directory_handler = directory_handler
        self.model = model
        self._switching = False
        self.navigation_root = None
        self._column_extended = False
        self._column_selection_pending = False
        self._column_last_selection = None
        self.tree = tree
        self.tree.expanded.connect(self._expanded)
        self.covers = CoverModel(model, self)
        self.tiles = ResponsiveTileView()
        self.tiles.setModel(self.covers)
        self.tiles.setViewMode(qt.QListView.ViewMode.IconMode)
        self.tiles.setResizeMode(qt.QListView.ResizeMode.Adjust)
        self.tiles.setMovement(qt.QListView.Movement.Static)
        self.tiles.setIconSize(qt.QSize(120, 165))
        self.tiles.setGridSize(qt.QSize(170, 205))
        self.tiles.setWordWrap(True)
        self.columns = FolderColumnView() if column_navigation else None
        # Trim two pixels per row from the shared theme's eight-pixel padding.
        # Keep this local to filename lists; other workspaces have their own density.
        for view in (tree,) + ((self.columns,) if self.columns is not None else ()):
            view.setStyleSheet('QAbstractItemView::item { padding: 3px 4px; }')
        if self.columns is not None:
            self.columns.setModel(model)
            self.columns.setColumnWidths([240, 240, 240, 240])
        self.cover_queue = deque()
        self.cover_busy = False
        self.cover_jobs = {}
        self.thumbnail_workers = 2
        self.closing = False
        self.badge_timer = qt.QTimer(self)
        self.badge_timer.setInterval(1000)
        self.badge_timer.timeout.connect(self._refresh_badges)
        self.badge_timer.start()
        self.cover_path = None
        self.cover_cancelled = Event()
        self.tiles.metrics_changed.connect(self._tile_metrics)
        self.covers.cover_requested.connect(self._request_cover)
        if self.columns is not None:
            self.columns.column_context_requested.connect(self._context)
            self.columns.selection_input.connect(self._column_input)
        for view in self.navigation_views:
            self.addWidget(view)
            configure_entry_selection(view)
            view.setEditTriggers(qt.QAbstractItemView.EditTrigger.SelectedClicked | qt.QAbstractItemView.EditTrigger.EditKeyPressed)
            view.customContextMenuRequested.connect(lambda point, target=view: self._context(target, point))
            if view is self.columns:
                view.selectionModel().selectionChanged.connect(self._queue_column_selection)
                view.selectionModel().currentChanged.connect(self._queue_column_selection)
            else:
                view.selectionModel().selectionChanged.connect(lambda *args, target=view: self._selection(target))
            view.doubleClicked.connect(lambda index: self.activated.emit(self.source_index(index)))
        if self.columns is None:
            self.addWidget(qt.QWidget())  # Preserve established storage-mode indices.
        self.storage = None
        if storage:
            from .storage_view import StorageView
            self.storage = StorageView(parent)
            self.addWidget(self.storage)
            self.storage.selection_changed.connect(self.selection_changed)
            self.storage.activated.connect(self._storage_activated)
            self.storage.context_requested.connect(self._storage_context)
            self.storage.idle.connect(self.idle)
        self.root = None

    @property
    def navigation_views(self):
        return (self.tree, self.tiles) + ((self.columns,) if self.columns is not None else ())

    def source_index(self, index):
        if isinstance(index.model(),qt.QAbstractProxyModel):
            return index.model().mapToSource(index)
        return index

    def _storage_activated(self, path):
        index = self.model.browse_index(path)
        if index.isValid():
            self.activated.emit(index)
        else:
            self.path_activated.emit(path)

    def _storage_context(self, path, position):
        self.context_directory = self.root
        self.context_position = position
        self.context_requested.emit(self.model.browse_index(path))

    def selected_rows(self):
        if self.storage is not None and self.currentWidget() is self.storage:
            index = self.model.browse_index(self.storage.selected_path) if self.storage.selected_path else qt.QModelIndex()
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
        return (self.root, tuple(self.model.browse_identity(index) for index in self.selected_rows()),
                self.model.browse_identity(self.columns.currentIndex()))

    def current_index(self):
        if self.storage is not None and self.currentWidget() is self.storage:
            rows = self.selected_rows()
            return rows[0] if rows else qt.QModelIndex()
        return self.source_index(self.currentWidget().currentIndex())

    def browsing_directory(self):
        if self.storage is not None and self.currentWidget() is self.storage:
            return self.root
        selected = self.selected_rows()
        index = self.current_index()
        if not any(index == item for item in selected):
            index = selected[-1] if selected else qt.QModelIndex()
        if index.isValid():
            path = self.model.browse_identity(index)
            directory = path if self.currentIndex() == 2 and index.data(BrowseRole.Container) else self.model.browse_parent(path)
            if self.model.browse_within(directory, self.root):
                return directory
        return self.root

    def _handled_directory(self, path):
        return bool(path is not None and self.directory_handler and self.directory_handler(path))

    def _expanded(self, index):
        if self._handled_directory(self.model.browse_identity(self.source_index(index))):
            self.tree.collapse(index)

    def _selection(self, view):
        if view is self.currentWidget() and not self._switching:
            if self._handled_directory(self.browsing_directory()):
                return
            self.directory_changed.emit(self.browsing_directory())
            self.selection_changed.emit()

    def _context(self, view, point):
        if view is self.currentWidget() or (self.currentWidget() is self.columns and self.columns.isAncestorOf(view)):
            self.context_directory = self.model.browse_identity(self.source_index(view.rootIndex()))
            self.context_position = view.viewport().mapToGlobal(point)
            self.context_requested.emit(self.source_index(view.indexAt(point)))

    def select_source(self, source):
        if self.storage is not None and self.currentWidget() is self.storage:
            self.storage.select_path(self.model.browse_identity(source))
            return
        view = self.currentWidget()
        index = self.covers.mapFromSource(source) if view is self.tiles else source
        view.selectionModel().setCurrentIndex(index, qt.QItemSelectionModel.SelectionFlag.ClearAndSelect |
                                              qt.QItemSelectionModel.SelectionFlag.Rows)
        view.scrollTo(index)
        view.setFocus()

    def edit_name(self, source):
        if self.storage is not None and self.currentWidget() is self.storage:
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
        if self._handled_directory(path):
            return
        self.root = path
        index = self.model.browse_root_index(path)
        for view in self.navigation_views:
            blocker = qt.QSignalBlocker(view.selectionModel())
            view.clearSelection()
            view.setCurrentIndex(qt.QModelIndex())
            view.setRootIndex(self.covers.mapFromSource(index) if view is self.tiles else index)
            blocker.unblock()
        if self.storage is not None:
            self.storage.set_root(self.root)
        self.tree.collapseAll()
        if self.currentWidget() is self.columns:
            self._column_last_selection = self._column_selection_key()
        self.directory_changed.emit(self.root)
        self.selection_changed.emit()
        self.directory_opened.emit(self.root)

    def set_mode(self, mode):
        if mode not in (0, 1, 2, 3, 4) or (mode >= 3 and self.storage is None):
            raise ValueError('This browser does not offer that view.')
        if mode == 2 and self.columns is None:
            raise ValueError('This host has disabled column navigation.')
        if mode >= 3 and self.root is not None and self.model.browse_network(self.root):
            return
        chart_mode = max(0, mode - 3)
        mode = min(mode, 3)  # Both storage buttons share the established storage widget.
        selected = self.selected_rows()
        directory = self.browsing_directory()
        if mode == 2:
            # A directory already opened in another mode belongs in the first
            # column, with its contents in the next one.
            focus = selected[-1] if selected else self.model.browse_index(directory)
            parent = self.model.browse_identity(focus.parent()) if focus.parent().isValid() else None
            scope = self.navigation_root
            if (focus.isValid() and parent is not None
                    and (scope is None or self.model.browse_within(parent, scope))):
                directory = parent
                selected = selected or [focus]
        if directory != self.root:
            self.set_root(directory)
        self.setCurrentIndex(mode)
        if mode == 3:
            self.storage.set_chart_mode(chart_mode)
            self.storage.set_root(directory)
            if selected:
                self.storage.select_path(self.model.browse_identity(selected[-1]))
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
        if self._handled_directory(self.browsing_directory()):
            return
        self.directory_changed.emit(self.browsing_directory())
        self.selection_changed.emit()

    def set_icon_scale(self, percent):
        self.tiles.set_folder_scale(percent)
        size = round(16 * percent / 50)
        for view in (self.tree,) + ((self.columns,) if self.columns is not None else ()):
            view.setIconSize(qt.QSize(size, size))

    def _tile_metrics(self, size, ratio):
        if self.covers.set_resolution(size, ratio):
            self.cover_queue.clear()
            self.tiles.viewport().update()

    def _refresh_badges(self):
        if not self.closing and self.isVisible() and self.currentIndex() == 1:
            self.tiles.viewport().update()

    def _request_cover(self, path):
        if self.closing or self.model.browse_network(path):
            return
        qt.QTimer.singleShot(0, lambda: self._enqueue_cover(path))

    def _visible_cover(self, path):
        index = self.covers.mapFromSource(self.model.browse_index(path))
        return self.currentIndex() == 1 and self.tiles.visualRect(index).intersects(self.tiles.viewport().rect())

    def _enqueue_cover(self, path):
        if self.closing or not self._visible_cover(path):
            self.covers.requested.discard(path)
            return
        if path not in self.cover_queue and path not in self.cover_jobs:
            self.cover_queue.append(path)
        self._next_cover()

    def _next_cover(self):
        if len(self.cover_jobs) >= self.thumbnail_workers or self.closing or not self.cover_queue:
            return
        self.cover_path = self.cover_queue.popleft()
        path = self.cover_path
        if not self._visible_cover(path):
            self.covers.requested.discard(path)
            qt.QTimer.singleShot(0, self._next_cover)
            return
        self.cover_busy = True
        thumbnail = self.model.browse_index(path).data(BrowseRole.Thumbnail)
        if thumbnail is None:
            self.cover_busy = bool(self.cover_jobs)
            self.covers.requested.discard(path)
            self._next_cover()
            return
        size, ratio = self.covers.render_size, self.covers.device_ratio
        worker = Operation(lambda: thumbnail(size, self.cover_cancelled.is_set), self)
        self.operation = worker
        self.cover_jobs[path] = worker
        revision = self.covers.revisions.get(path, 0)
        epoch = self.covers.epoch
        worker.completed.connect(lambda data, error: self._cover_loaded(path, revision, data or b'', ratio, size, epoch))
        worker.finished.connect(lambda: self._cover_finished(path, worker))
        worker.start()
        self._next_cover()

    def _cover_loaded(self, path, revision, data, ratio=1.0, size=None, epoch=None):
        if not self.closing and (epoch is None or epoch == self.covers.epoch) and revision == self.covers.revisions.get(path, 0):
            self.covers.complete(path, data, ratio, size)
        else:
            self.covers.requested.discard(path)
            self.tiles.viewport().update()

    def _cover_finished(self, path, worker):
        self.cover_jobs.pop(path, None)
        self.cover_busy = bool(self.cover_jobs)
        worker.deleteLater()
        if self.closing:
            if not self.cover_busy:
                self.idle.emit()
        else:
            self._next_cover()
            if not self.cover_busy:
                self.idle.emit()

    def stop(self):
        self.closing = True
        self.badge_timer.stop()
        self.cover_queue.clear()
        self.cover_cancelled.set()
        self.covers.icons.clear()
        self.covers.requested.clear()
        storage_busy = self.storage.stop() if self.storage is not None else False
        return self.cover_busy or storage_busy


class FileViews(BrowserViews):
    """Local browser integration retains its optional indexed storage charts."""
    def __init__(self, model, tree, parent=None, *, directory_handler=None, column_navigation=True):
        super().__init__(model, tree, parent, directory_handler=directory_handler, storage=True,
                         column_navigation=column_navigation)
