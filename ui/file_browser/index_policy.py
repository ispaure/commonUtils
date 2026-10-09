"""Refresh rules read at each request; applications may supply their own INI."""
from dataclasses import dataclass
from ...settings import get_setting


@dataclass(frozen=True)
class IndexPolicy:
    scan_on_open: bool = True
    recursive_on_open: bool = True
    refresh_cached_on_startup: bool = True
    refresh_on_revisit: bool = False
    watch_changes: bool = True
    background_priority: bool = True


def index_policy(*, path=None):
    defaults = IndexPolicy(recursive_on_open=False, refresh_cached_on_startup=False) if path is not None else IndexPolicy()
    return IndexPolicy(**{name: get_setting('FileIndex', name, default, path=path)
                          for name, default in vars(defaults).items()})
