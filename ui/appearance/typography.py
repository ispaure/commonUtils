"""Portable font settings, expressed as points at a 96-logical-DPI reference."""
from .. import pyside as qt


def font_dpi():
    """Return Qt's font resolution without touching GUI APIs before startup."""
    app = qt.QGuiApplication.instance()
    if not isinstance(app, qt.QGuiApplication):
        return 96.0
    screen = app.primaryScreen()
    return screen.logicalDotsPerInchY() if screen is not None else 96.0


def point_size(size):
    """Convert a saved reference size to Qt points; keep OS display scaling."""
    return float(size) * 96.0 / font_dpi()


def setting_size(font):
    """Convert a rendered QFont back to the reference size used by zoom/settings."""
    if font.pixelSize() > 0:
        return font.pixelSize() * 72.0 / 96.0
    return font.pointSizeF() * font_dpi() / 96.0
