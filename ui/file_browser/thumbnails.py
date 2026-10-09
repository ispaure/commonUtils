"""Bounded thumbnail cache and physical-pixel resolution requirements."""

from collections import OrderedDict
import math
from ...dirUtils import Directory
from .. import pyside as qt
from .model import ByteSortModel


class CoverModel(ByteSortModel):
    cover_requested = qt.Signal(str)

    def __init__(self, source, parent=None):
        super().__init__(source, parent)
        self.sort(0, qt.Qt.SortOrder.AscendingOrder)
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
