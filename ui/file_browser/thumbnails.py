"""Bounded thumbnail cache and physical-pixel resolution requirements."""

from collections import OrderedDict
import math
from ...runtime.browsing import BrowseRole
from .. import pyside as qt
from .model import ByteSortModel


class CoverModel(ByteSortModel):
    cover_requested = qt.Signal(object)

    def __init__(self, source, parent=None):
        super().__init__(source, parent)
        self.sort(0, qt.Qt.SortOrder.AscendingOrder)
        self.icons = OrderedDict()
        self.requested = set()
        self.revisions = {}
        self.render_size = (120, 165)
        self.device_ratio = 1.0
        self.resolutions = {}
        self.epoch = 0
        self.snapshots = {}
        source.modelReset.connect(self.clear_cache)
        if hasattr(source, 'snapshot_changed'):
            source.snapshot_changed.connect(self._snapshot_changed)

    def clear_cache(self):
        self.epoch += 1
        self.icons.clear()
        self.requested.clear()
        self.resolutions.clear()
        self.snapshots.clear()

    def _snapshot_changed(self):
        self.epoch += 1
        self.requested.intersection_update(self.icons)
        for identity in list(self.icons):
            index = self.sourceModel().browse_index(identity)
            revision = index.data(BrowseRole.Revision) if index.isValid() else None
            if revision is None or revision != self.snapshots.get(identity):
                self.invalidate(identity)

    def data(self, index, role=qt.Qt.ItemDataRole.DisplayRole):
        if role == qt.Qt.ItemDataRole.DecorationRole and index.column() == 0:
            source = self.mapToSource(index)
            path = source.data(BrowseRole.Identity)
            if source.data(BrowseRole.Thumbnail):
                if path in self.icons:
                    self.icons.move_to_end(path)
                    return self.icons[path]
                if path not in self.requested:
                    self.requested.add(path)
                    self.cover_requested.emit(path)
        value = super().data(index, role)
        if role == qt.Qt.ItemDataRole.DecorationRole and index.column() == 0 and (value is None or value.isNull()):
            source = self.mapToSource(index)
            kind = qt.QStyle.StandardPixmap.SP_DirIcon if source.data(BrowseRole.Container) else qt.QStyle.StandardPixmap.SP_FileIcon
            return qt.QApplication.style().standardIcon(kind)
        return value

    def complete(self, path, data, ratio=1.0, resolution=None):
        path = self.sourceModel().browse_key(path)
        source = self.sourceModel().browse_index(path)
        pixmap = qt.QPixmap()
        pixmap.loadFromData(data)
        pixmap.setDevicePixelRatio(ratio)
        self.resolutions[path] = resolution or self.render_size
        self.snapshots[path] = source.data(BrowseRole.Revision)
        icon = qt.QIcon(pixmap) if not pixmap.isNull() else self.sourceModel().data(source, qt.Qt.ItemDataRole.DecorationRole)
        if icon is None or icon.isNull():
            icon = qt.QApplication.style().standardIcon(qt.QStyle.StandardPixmap.SP_FileIcon)
        self.icons[path] = icon
        self.icons.move_to_end(path)
        while len(self.icons) > 128:
            evicted, _ = self.icons.popitem(last=False)
            self.requested.discard(evicted)
            self.resolutions.pop(evicted, None)
            self.snapshots.pop(evicted, None)
        index = self.mapFromSource(source)
        if index.isValid():
            self.dataChanged.emit(index, index, [qt.Qt.ItemDataRole.DecorationRole])

    def invalidate(self, path):
        path = self.sourceModel().browse_key(path)
        self.revisions[path] = self.revisions.get(path, 0) + 1
        self.icons.pop(path, None)
        self.resolutions.pop(path, None)
        self.snapshots.pop(path, None)
        self.requested.discard(path)
        index = self.mapFromSource(self.sourceModel().browse_index(path))
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


def image_thumbnail(data, size):
    """Resize bounded image bytes on a worker, without QPixmap or disk I/O."""
    if not isinstance(size, qt.QSize):
        size = qt.QSize(*size)
    buffer = qt.QBuffer()
    buffer.setData(qt.QByteArray(data))
    buffer.open(qt.QIODevice.OpenModeFlag.ReadOnly)
    reader = qt.QImageReader(buffer)
    dimensions = reader.size()
    if not dimensions.isValid() or dimensions.width() * dimensions.height() > 16 * 1024 * 1024:
        return b''
    reader.setAutoTransform(True)
    reader.setScaledSize(dimensions.scaled(size, qt.Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    if image.isNull():
        return b''
    image = image.scaled(size, qt.Qt.AspectRatioMode.KeepAspectRatio, qt.Qt.TransformationMode.SmoothTransformation)
    output = qt.QBuffer()
    output.open(qt.QIODevice.OpenModeFlag.WriteOnly)
    image.save(output, 'PNG')
    return bytes(output.data())
