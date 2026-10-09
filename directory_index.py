"""Persistent, resumable directory indexing shared by search and storage analysis."""
# Preserve the public metadata API; os remains available for scanner instrumentation.
import os
from ._directory_metadata import Entry, Snapshot, scan_metadata, storage_totals, fingerprint
from ._directory_store import DirectoryCache, directory_index_path


directory_cache = DirectoryCache()
