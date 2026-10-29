"""Absolute filesystem I/O paths, including Windows extended-length names."""
import ntpath
import os
from pathlib import Path


def _extended_windows(value):
    if value.startswith(('\\\\?\\', '\\\\.\\')):
        return value
    value = ntpath.normpath(value)
    return '\\\\?\\UNC\\' + value[2:] if value.startswith('\\\\') else '\\\\?\\' + value


def native_path(path):
    """Prepare an absolute I/O path without following links or changing access policy.

    Windows long paths work independently of a machine-wide registry switch.
    Keep these paths inside filesystem adapters; logical names stay unchanged.
    """
    value = str(Path(os.fsdecode(path)).absolute())
    return Path(_extended_windows(value) if os.name == 'nt' else value)
