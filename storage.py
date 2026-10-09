"""Platform-standard commonUtils caches and private disposable workspaces.

Path resolution is side-effect free with create=False. Persistent caches are never
cleaned on application exit; a temporary_workspace cleans only its own directory.
Atomic file replacement staging must stay beside its destination, not in Temp.
"""
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


def cache_directory(*, create=True):
    if sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Caches'
    elif sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
    else:
        configured = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache')
        base = configured if configured.is_absolute() else Path.home() / '.cache'
    folder = base / 'commonUtils'
    if create:
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    return folder


def temporary_directory(*, create=True):
    folder = cache_directory(create=create) / 'Temp'
    if create:
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    return folder


def temporary_workspace(*, prefix='workspace-', ignore_cleanup_errors=False):
    """Return a private TemporaryDirectory context under the shared Temp area."""
    return TemporaryDirectory(dir=temporary_directory(), prefix=prefix,
                              ignore_cleanup_errors=ignore_cleanup_errors)
