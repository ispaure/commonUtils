"""Native browser exports; portable lifecycle imports do not load Toga."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from .lifecycle import BrowserLifecycle

__all__ = ['BrowserLifecycle', 'NativeBrowser', 'clear_box']


def __getattr__(name):
    if name in {'NativeBrowser', 'clear_box'}:
        from . import presentation
        return getattr(presentation, name)
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


def __dir__():
    return sorted(set(globals()) | set(__all__))
