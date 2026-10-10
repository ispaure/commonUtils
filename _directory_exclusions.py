"""Traversal exclusions shared by discovery and incremental reconciliation."""
import sys
from pathlib import Path
from .network_filesystems import network_mount_roots


MACOS_ROOT = Path('/')
MACOS_DATA = Path('/System/Volumes/Data')


def scan_exclusions(root, database):
    """Keep the cache out of itself and omit macOS's duplicate Data traversal.

    Firmlinks expose Data's contents at ordinary paths under /. Unlike symlinks,
    they look like directories to lstat, so the scanner needs an explicit rule.
    Only a whole-filesystem scan applies this rule; explicit Data scopes remain
    usable. Other system volumes and external drives retain their coverage.
    """
    excluded = set()
    real_root = root.resolve()
    for path in (database.parent, database, database.with_suffix('.lock'),
                 Path(str(database) + '-wal'), Path(str(database) + '-shm')):
        try:
            excluded.add(root / path.resolve().relative_to(real_root))
        except ValueError:
            pass
    if sys.platform == 'darwin' and root == MACOS_ROOT:
        excluded.add(MACOS_DATA)
    for mount in network_mount_roots():
        # Mount metadata and the caller may use /var versus /private/var.
        # Compare both local root spellings without resolving a network mount.
        for local_root in (root.absolute(), real_root):
            try:
                excluded.add(root / mount.relative_to(local_root))
                break
            except ValueError:
                pass
    return excluded


def is_excluded(path, exclusions):
    return any(path == excluded or excluded in path.parents for excluded in exclusions)
