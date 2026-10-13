"""Filter Windows legacy fonts before asking Qt to render their faces."""
import sys

from .. import pyside as qt


# GDI bitmap/vector families cannot be used reliably by Qt's DirectWrite engine.
# Check names first: even probing these faces can produce native warnings.
_WINDOWS_LEGACY = frozenset({
    'terminal', '8514oem', 'fixedsys', 'modern', 'ms sans serif',
    'ms serif', 'roman', 'script', 'system',
})


def font_database_available():
    """Font metadata needs a GUI application, even for otherwise pure reads."""
    return isinstance(qt.QGuiApplication.instance(), qt.QGuiApplication)


def supported_font_family(family):
    family = family.strip()
    if not family or sys.platform != 'win32':
        return True
    if family.casefold() in _WINDOWS_LEGACY:
        return False
    # Preference loading can run before the GUI starts. Defer metadata checks
    # until the styling controller reloads after QApplication construction.
    return not font_database_available() or qt.QFontDatabase.isSmoothlyScalable(family)
