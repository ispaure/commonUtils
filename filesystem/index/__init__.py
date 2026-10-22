"""Persistent, resumable directory indexing shared by search and storage analysis."""
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
