"""Filter Windows legacy fonts before asking Qt to render their faces."""
import sys

from .. import pyside as qt


# GDI bitmap/vector families cannot be used reliably by Qt's DirectWrite engine.
# Check names first: even probing these faces can produce native warnings.
_WINDOWS_LEGACY = frozenset({
    'terminal', '8514oem', 'fixedsys', 'modern', 'ms sans serif',
    'ms serif', 'roman', 'script', 'system',
})


def supported_font_family(family):
    family = family.strip()
    if not family or sys.platform != 'win32':
        return True
    return (family.casefold() not in _WINDOWS_LEGACY
            and qt.QFontDatabase.isSmoothlyScalable(family))
