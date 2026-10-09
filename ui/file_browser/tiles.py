"""Responsive tile layout with bounded, adjustable icons and thumbnails."""

from ...dirUtils import Directory
from .. import pyside as qt
from .editing import FilenameEditorMixin

COVER_WIDTH = 142
COVER_ASPECT_RATIO = 1.375
CELL_PADDING = 28
CAPTION_HEIGHT = 44


class TileDelegate(FilenameEditorMixin, qt.QStyledItemDelegate):
    def paint(self, painter, option, index):
        option = qt.QStyleOptionViewItem(option)
        self.initStyleOption(option, index)
        style = option.widget.style() if option.widget else qt.QApplication.style()
        area = style.subElementRect(qt.QStyle.SubElement.SE_ItemViewItemDecoration, option, option.widget)
        pixmap = option.icon.pixmap(option.decorationSize, self.parent().devicePixelRatioF())
        # Keep the shared caption/selection geometry, but paint the image ourselves:
        # some native/custom icon engines stretch to Qt's portrait decoration rect.
        option.icon = qt.QIcon()
        style.drawControl(qt.QStyle.ControlElement.CE_ItemViewItem, option, painter, option.widget)
        if not pixmap.isNull():
            ratio = pixmap.devicePixelRatioF()
            pixmap = pixmap.scaled(round(area.width() * ratio), round(area.height() * ratio),
                                   qt.Qt.AspectRatioMode.KeepAspectRatio, qt.Qt.TransformationMode.SmoothTransformation)
            pixmap.setDevicePixelRatio(ratio)
            size = pixmap.deviceIndependentSize()
            painter.drawPixmap(qt.QPointF(area.center().x() - size.width()/2,
                                         area.center().y() - size.height()/2), pixmap)

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        view = self.parent()
        source = index.model().mapToSource(index)
        size = (view.folder_icon_size if isinstance(source.model().item(source), Directory)
                else view.iconSize())
        # Native icon engines and cached covers can supply pixmaps larger than requested.
        # Normalize after Qt initializes the option so its intrinsic size cannot override
        # the browser's bounds. Work in physical pixels for Retina displays.
        ratio = view.devicePixelRatioF()
        # macOS native engines can stretch their artwork to the requested canvas.
        # Rasterize onto a square first; fitting an already-stretched pixmap later
        # cannot recover its original proportions. Cached covers keep their ratio.
        edge = max(size.width(), size.height())
        pixmap = option.icon.pixmap(qt.QSize(edge, edge), ratio)
        bounds = qt.QSize(round(size.width() * ratio), round(size.height() * ratio))
        pixmap = pixmap.scaled(bounds, qt.Qt.AspectRatioMode.KeepAspectRatio,
                               qt.Qt.TransformationMode.SmoothTransformation)
        pixmap.setDevicePixelRatio(ratio)
        option.icon = qt.QIcon(pixmap)
        # Reserve the same decoration area so captions line up across icon shapes.
        option.decorationSize = view.iconSize()


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
            raise ValueError('Icon size must be between 25 and 100 percent')
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
            preferred_icon_width = round(COVER_WIDTH * self.folder_scale)
            columns = max(1, width // (preferred_icon_width + CELL_PADDING))
            cell_width = width // columns
            icon_width = min(preferred_icon_width, max(16, cell_width - CELL_PADDING))
            icon_height = icon_width if self.folders_only else round(icon_width * COVER_ASPECT_RATIO)
            folder_width = icon_width
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
