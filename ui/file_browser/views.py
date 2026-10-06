"""Shared filesystem list, tile and column views with asynchronous cover icons."""

from collections import deque, OrderedDict
from pathlib import Path
import math
from ...dirUtils import Directory
from .. import pyside as qt
from .operations import Operation


class TileDelegate(qt.QStyledItemDelegate):
    def paint(self, painter, option, index):
        view = self.parent()
        source = index.model().mapToSource(index)
        if isinstance(source.model().item(source), Directory):
            option = qt.QStyleOptionViewItem(option)
            option.decorationSize = view.folder_icon_size
        super().paint(painter, option, index)


class ResponsiveTileView(qt.QListView):
    metrics_changed = qt.Signal(object, float)

    def __init__(self):
        super().__init__()
        self.folder_scale = .5
        self.folder_icon_size = qt.QSize(71, 71)
        self.folders_only = None
        self.fitting = False
        self.setSpacing(0)
        self.setVerticalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setItemDelegate(TileDelegate(self))
        self.viewport().installEventFilter(self)

    def setModel(self, model):
        super().setModel(model)
        model.rowsInserted.connect(self._contents_changed)
        model.rowsRemoved.connect(self._contents_changed)
        model.modelReset.connect(self._contents_changed)
        model.layoutChanged.connect(self._contents_changed)

    def _contents_changed(self, *args):
        self.folders_only = None
        self.fit_grid()

    def setRootIndex(self, index):
        super().setRootIndex(index)
        self._contents_changed()

    def set_folder_scale(self, percent):
        self.folder_scale = percent / 100
        self.fit_grid()
        self.viewport().update()

    def eventFilter(self, watched, event):
        if event.type() in (qt.QEvent.Type.Resize, qt.QEvent.Type.Show, qt.QEvent.Type.ScreenChangeInternal, qt.QEvent.Type.DevicePixelRatioChange):
            self.fit_grid()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_grid()

    def showEvent(self, event):
        self.fit_grid()
        super().showEvent(event)

    def fit_grid(self):
        if self.fitting or self.model() is None:
            return
        self.fitting = True
        try:
            if self.folders_only is None:
                model = self.model()
                self.folders_only = all(isinstance(model.sourceModel().item(model.mapToSource(model.index(row, 0, self.rootIndex()))), Directory)
                                        for row in range(model.rowCount(self.rootIndex())))
            target_width = round(142 * self.folder_scale) + 28 if self.folders_only else 170
            # Column count must not oscillate when a vertical scrollbar appears.
            scroll_width = self.style().pixelMetric(qt.QStyle.PixelMetric.PM_ScrollBarExtent)
            available = max(1, self.contentsRect().width() - scroll_width - 2)
            columns = max(1, available // target_width)
            for _ in range(3):
                width = max(1, self.viewport().width() - 2)
                cell = width // columns
                icon_width = max(16, cell - 28)
                icon_height = icon_width if self.folders_only else round(icon_width * 1.375)
                folder_width = icon_width if self.folders_only else round(icon_width * self.folder_scale)
                self.folder_icon_size = qt.QSize(folder_width, folder_width)
                size, grid = qt.QSize(icon_width, icon_height), qt.QSize(cell, icon_height + 44)
                if self.iconSize() != size or self.gridSize() != grid:
                    self.setIconSize(size)
                    self.setGridSize(grid)
                    self.doItemsLayout()
                if width == max(1, self.viewport().width() - 2):
                    break
            self.metrics_changed.emit(self.iconSize(), self.devicePixelRatioF())
        finally:
            self.fitting = False


class ColumnDelegate(qt.QStyledItemDelegate):
    arrow_size = 8

    def paint(self, painter, option, index):
        option = qt.QStyleOptionViewItem(option)
        self.initStyleOption(option, index)
        rtl = option.direction == qt.Qt.LayoutDirection.RightToLeft
        has_children = index.model().hasChildren(index)
        style = option.widget.style() if option.widget else qt.QApplication.style()
        style.drawPrimitive(qt.QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, option.widget)
        rect = qt.QRect(option.rect)
        margin = self.arrow_size + 10
        option.rect.adjust(margin if rtl else 0, 0, 0 if rtl else -margin, 0)
        super().paint(painter, option, index)
        if has_children:
            x = rect.left() + margin / 2 if rtl else rect.right() - margin / 2
            y = rect.center().y()
            color = option.palette.color(qt.QPalette.ColorRole.HighlightedText if option.state & qt.QStyle.StateFlag.State_Selected
                                         else qt.QPalette.ColorRole.Text)
            painter.save()
            painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
            painter.setPen(qt.QPen(color, 1.2))
            half = self.arrow_size / 2
            direction = -1 if rtl else 1
            painter.drawLine(qt.QLineF(x - direction * half / 2, y - half, x + direction * half / 2, y))
            painter.drawLine(qt.QLineF(x + direction * half / 2, y, x - direction * half / 2, y + half))
            painter.restore()


class FolderColumnView(qt.QColumnView):
    def __init__(self):
        super().__init__()
        self.viewport().setBackgroundRole(qt.QPalette.ColorRole.Window)
        self.viewport().setAutoFillBackground(True)
        if hasattr(self, 'setPreviewColumnVisible'):
            self.setPreviewColumnVisible(False)
        else:
            # Before Qt 6.11, the public preview widget still needs a zero-width host.
            preview = qt.QWidget()
            preview.setFixedWidth(0)
            self.setPreviewWidget(preview)
            host = preview.parentWidget().parentWidget()
            host.setFixedWidth(0)
            host.setVerticalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            host.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def createColumn(self, index):
        column = super().createColumn(index)
        column.setItemDelegate(ColumnDelegate(column))
        column.setIconSize(qt.QSize(16, 16))
        column.setVerticalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        return column


class CoverModel(qt.QIdentityProxyModel):
    cover_requested = qt.Signal(str)

    def __init__(self, source, parent=None):
        super().__init__(parent)
        self.setSourceModel(source)
        self.icons = OrderedDict()
        self.requested = set()
        self.revisions = {}
        self.render_size = (120, 165)
        self.device_ratio = 1.0
        self.resolutions = {}

    def data(self, index, role=qt.Qt.ItemDataRole.DisplayRole):
        if role == qt.Qt.ItemDataRole.DecorationRole and index.column() == 0:
            source = self.mapToSource(index)
            path = self.sourceModel().filePath(source)
            item = self.sourceModel().item(source)
            if item.browser_has_thumbnail:
                if path in self.icons:
                    self.icons.move_to_end(path)
                    return self.icons[path]
                if path not in self.requested:
                    self.requested.add(path)
                    self.cover_requested.emit(path)
        value = super().data(index, role)
        if role == qt.Qt.ItemDataRole.DecorationRole and index.column() == 0 and (value is None or value.isNull()):
            source = self.mapToSource(index)
            kind = qt.QStyle.StandardPixmap.SP_DirIcon if isinstance(self.sourceModel().item(source), Directory) else qt.QStyle.StandardPixmap.SP_FileIcon
            return qt.QApplication.style().standardIcon(kind)
        return value

    def complete(self, path, data, ratio=1.0, resolution=None):
        source = self.sourceModel().index(path)
        pixmap = qt.QPixmap()
        pixmap.loadFromData(data)
        pixmap.setDevicePixelRatio(ratio)
        self.resolutions[path] = resolution or self.render_size
        icon = qt.QIcon(pixmap) if not pixmap.isNull() else self.sourceModel().data(source, qt.Qt.ItemDataRole.DecorationRole)
        if icon is None or icon.isNull():
            icon = qt.QApplication.style().standardIcon(qt.QStyle.StandardPixmap.SP_FileIcon)
        self.icons[path] = icon
        self.icons.move_to_end(path)
        while len(self.icons) > 128:
            evicted, _ = self.icons.popitem(last=False)
            self.requested.discard(evicted)
            self.resolutions.pop(evicted, None)
        index = self.mapFromSource(source)
        if index.isValid():
            self.dataChanged.emit(index, index, [qt.Qt.ItemDataRole.DecorationRole])

    def invalidate(self, path):
        path = str(path)
        self.revisions[path] = self.revisions.get(path, 0) + 1
        self.icons.pop(path, None)
        self.resolutions.pop(path, None)
        self.requested.discard(path)
        index = self.mapFromSource(self.sourceModel().index(path))
        if index.isValid():
            self.dataChanged.emit(index, index, [qt.Qt.ItemDataRole.DecorationRole])


    def set_resolution(self, logical_size, ratio):
        size = (math.ceil(logical_size.width() * ratio), math.ceil(logical_size.height() * ratio))
        changed = size != self.render_size or ratio != self.device_ratio
        self.render_size = size
        self.device_ratio = ratio
        if changed:
            for path in list(self.requested):
                previous = self.resolutions.get(path, (0, 0))
                if previous[0] < size[0] or previous[1] < size[1]:
                    self.invalidate(path)
        return changed


class FileViews(qt.QStackedWidget):
    selection_changed = qt.Signal()
    context_requested = qt.Signal(object)
    activated = qt.Signal(object)
    idle = qt.Signal()
    directory_changed = qt.Signal(object)

    def __init__(self, model, tree, parent=None):
        super().__init__(parent)
        self.model = model
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
        for view in (tree, self.tiles, self.columns):
            self.addWidget(view)
            view.setSelectionMode(qt.QAbstractItemView.SelectionMode.ExtendedSelection)
            view.setEditTriggers(qt.QAbstractItemView.EditTrigger.NoEditTriggers)
            view.setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)
            view.customContextMenuRequested.connect(lambda point, target=view: self._context(target, point))
            view.selectionModel().selectionChanged.connect(lambda *args, target=view: self._selection(target))
            view.doubleClicked.connect(lambda index: self.activated.emit(self.source_index(index)))
        self.root = None

    def source_index(self, index):
        return self.covers.mapToSource(index) if index.model() is self.covers else index

    def selected_rows(self):
        return list(dict.fromkeys(self.source_index(index) for index in
                                  self.currentWidget().selectionModel().selectedIndexes() if index.column() == 0))

    def current_index(self):
        return self.source_index(self.currentWidget().currentIndex())

    def browsing_directory(self):
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
        if view is self.currentWidget():
            self.directory_changed.emit(self.browsing_directory())
            self.selection_changed.emit()

    def _context(self, view, point):
        if view is self.currentWidget():
            self.context_position = view.viewport().mapToGlobal(point)
            self.context_requested.emit(self.source_index(view.indexAt(point)))

    def set_root(self, path):
        self.root = Path(path)
        index = self.model.index(str(path))
        for view in (self.tree, self.tiles, self.columns):
            blocker = qt.QSignalBlocker(view.selectionModel())
            view.clearSelection()
            view.setCurrentIndex(qt.QModelIndex())
            view.setRootIndex(self.covers.mapFromSource(index) if view is self.tiles else index)
            blocker.unblock()
        self.tree.collapseAll()
        self.directory_changed.emit(self.root)
        self.selection_changed.emit()

    def set_mode(self, mode):
        selected = self.selected_rows()
        directory = self.browsing_directory()
        if directory != self.root:
            self.set_root(directory)
        self.setCurrentIndex(mode)
        selection = self.currentWidget().selectionModel()
        blocker = qt.QSignalBlocker(selection)
        selection.clearSelection()
        for source in selected:
            index = self.covers.mapFromSource(source) if mode == 1 else source
            selection.select(index, qt.QItemSelectionModel.SelectionFlag.Select | qt.QItemSelectionModel.SelectionFlag.Rows)
            selection.setCurrentIndex(index, qt.QItemSelectionModel.SelectionFlag.NoUpdate)
        blocker.unblock()
        self.directory_changed.emit(self.browsing_directory())
        self.selection_changed.emit()

    def _tile_metrics(self, size, ratio):
        if self.covers.set_resolution(size, ratio):
            self.cover_queue.clear()
            self.tiles.viewport().update()

    def _request_cover(self, path):
        if self.closing:
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
        return self.cover_busy
