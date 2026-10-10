"""Native Qt icons rendered from Python painters, without Python engine ownership."""
from functools import lru_cache
from . import pyside as qt


@lru_cache(maxsize=128)
def _render(painter_type, key, palette_key):
    painter_source = painter_type(key)
    icon = qt.QIcon()
    for size in (16, 24, 32):
        for ratio in (1, 2):
            for mode in (qt.QIcon.Mode.Normal, qt.QIcon.Mode.Disabled, qt.QIcon.Mode.Active, qt.QIcon.Mode.Selected):
                for state in (qt.QIcon.State.Off, qt.QIcon.State.On):
                    pixmap = qt.QPixmap(size * ratio, size * ratio)
                    pixmap.setDevicePixelRatio(ratio)
                    pixmap.fill(qt.Qt.GlobalColor.transparent)
                    painter = qt.QPainter(pixmap)
                    try:
                        painter_source.paint(painter, qt.QRect(0, 0, size, size), mode, state)
                    finally:
                        painter.end()
                    icon.addPixmap(pixmap, mode, state)
    return icon


def painted_icon(painter_type, key):
    # QIcon owns only its native pixmap engine, never a Python QIconEngine wrapper.
    return qt.QIcon(_render(painter_type, key, qt.QApplication.palette().cacheKey()))


class _IconBinding(qt.QObject):
    def __init__(self, target, painter_type, key):
        super().__init__(target)
        self.target = target
        self.painter_type, self.key = painter_type, key
        qt.QApplication.instance().paletteChanged.connect(self.refresh)
        self.refresh()

    def refresh(self, *args):
        self.target.setIcon(painted_icon(self.painter_type, self.key))


def set_painted_icon(target, painter_type, key):
    """Set a native icon and refresh its palette when the application's theme changes."""
    binding = getattr(target, '_painted_icon_binding', None)
    if binding is None:
        target._painted_icon_binding = _IconBinding(target, painter_type, key)
    else:
        binding.painter_type, binding.key = painter_type, key
        binding.refresh()
