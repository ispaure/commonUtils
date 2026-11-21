"""Refresh rules read at each request; applications may supply their own INI."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from dataclasses import dataclass
from ...configuration.settings import get_setting


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
