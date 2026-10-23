"""Native browser exports; portable lifecycle imports do not load Toga."""
from .lifecycle import BrowserLifecycle

__all__ = ['BrowserLifecycle', 'NativeBrowser', 'clear_box']


def __getattr__(name):
    if name in {'NativeBrowser', 'clear_box'}:
        from . import presentation
        return getattr(presentation, name)
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


def __dir__():
    return sorted(set(globals()) | set(__all__))
