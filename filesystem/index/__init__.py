"""Persistent, resumable directory indexing shared by search and storage analysis."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

# Preserve the public metadata API; os remains available for scanner instrumentation.
import os
from .metadata import Entry, Snapshot, scan_metadata, storage_totals, fingerprint
from .store import DirectoryCache, directory_index_path


def __getattr__(name):
    # Mobile hosts supply an explicit database and cannot use desktop defaults.
    if name == 'directory_cache':
        cache = globals()['directory_cache'] = DirectoryCache()
        return cache
    raise AttributeError(name)
