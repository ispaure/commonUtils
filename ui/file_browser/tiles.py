"""Immediate responsive tile layout with adjustable folder icons."""

from ...dirUtils import Directory
from .. import pyside as qt

COVER_WIDTH = 142
COVER_ASPECT_RATIO = 1.375
CELL_PADDING = 28
CAPTION_HEIGHT = 44


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
        if not 25 <= percent <= 100:
            raise ValueError('Folder icon size must be between 25 and 100 percent')
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

    def _contains_only_folders(self):
        model = self.model()
        source_model = model.sourceModel()
        root = self.rootIndex()
        for row in range(model.rowCount(root)):
            source = model.mapToSource(model.index(row, 0, root))
            if not isinstance(source_model.item(source), Directory):
                return False
        return True

    def fit_grid(self):
        if self.fitting or self.model() is None:
            return
        self.fitting = True
        try:
            if self.folders_only is None:
                self.folders_only = self._contains_only_folders()
            width = max(1, self.viewport().width() - 2)
            preferred_icon_width = round(COVER_WIDTH * self.folder_scale) if self.folders_only else COVER_WIDTH
            columns = max(1, width // (preferred_icon_width + CELL_PADDING))
            cell_width = width // columns
            icon_width = max(16, cell_width - CELL_PADDING)
            icon_height = icon_width if self.folders_only else round(icon_width * COVER_ASPECT_RATIO)
            folder_width = icon_width if self.folders_only else round(icon_width * self.folder_scale)
            self.folder_icon_size = qt.QSize(folder_width, folder_width)
            icon_size = qt.QSize(icon_width, icon_height)
            grid_size = qt.QSize(cell_width, icon_height + CAPTION_HEIGHT)
            if self.iconSize() != icon_size or self.gridSize() != grid_size:
                self.setIconSize(icon_size)
                self.setGridSize(grid_size)
                self.doItemsLayout()
            self.metrics_changed.emit(icon_size, self.devicePixelRatioF())
        finally:
            self.fitting = False
