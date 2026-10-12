"""Platform-standard commonUtils caches and private disposable workspaces.

Path resolution is side-effect free with create=False. Persistent caches are never
cleaned on application exit; a temporary_workspace cleans only its own directory.
Atomic file replacement staging must stay beside its destination, not in Temp.
"""
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from ...runtime.platform.capabilities import Capability, require_capability


def _host_storage_root():
    value = os.environ.get('COMMONUTILS_STORAGE_ROOT')
    if value:
        root = Path(value)
        if not root.is_absolute():
            raise ValueError('COMMONUTILS_STORAGE_ROOT must be an absolute app-private path')
        return root
    require_capability(Capability.DEFAULT_STORAGE, 'commonUtils storage; set COMMONUTILS_STORAGE_ROOT')
    return None


def _disposable_directory():
    if sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Caches'
    elif sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
    else:
        configured = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache')
        base = configured if configured.is_absolute() else Path.home() / '.cache'
    return base / 'commonUtils'


def cache_directory(*, create=True):
    root = _host_storage_root()
    folder = root / 'Cache' if root is not None else (Path.home() / 'Library' / 'Application Support' / 'commonUtils' / 'Cache'
              if sys.platform == 'darwin' else _disposable_directory())
    if create:
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    return folder


def temporary_directory(*, create=True):
    root = _host_storage_root()
    folder = root / 'Temp' if root is not None else (Path.home() / 'Library' / 'Application Support' / 'commonUtils' / 'Temp'
              if sys.platform == 'darwin' else _disposable_directory() / 'Temp')
    if create:
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    return folder


def temporary_workspace(*, prefix='workspace-', ignore_cleanup_errors=False):
    """Return a private TemporaryDirectory context under the shared Temp area."""
    return TemporaryDirectory(dir=temporary_directory(), prefix=prefix,
                              ignore_cleanup_errors=ignore_cleanup_errors)
