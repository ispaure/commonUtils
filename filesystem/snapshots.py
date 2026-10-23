"""Verified file hashes and bounded content inventories, without host schemas."""
import os
from pathlib import Path
import stat
from ..runtime.operations import check_cancelled
from ..runtime.streams import stream_signature


def file_revision(path, *, follow_symlinks=True):
    path = Path(path)
    return _revision(path.stat() if follow_symlinks else path.lstat())


def _revision(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def verified_file_snapshot(path, *, cancelled=lambda: False, max_bytes=None):
    """Return (revision, SHA-256 bytes); reject changes during the read.

    Caller chooses whether links/hard links are allowed. Both the opened file and
    its pathname must retain the original revision. An optional max_bytes bound
    rejects growing/oversized input during hashing. This is not a writer lock.
    """
    check_cancelled(cancelled)
    path = Path(path)
    before = file_revision(path)
    with path.open('rb') as stream:
        opened = _revision(os.fstat(stream.fileno()))
        # Windows stat() and fstat() can give ctime different meanings.
        # Compare content/identity across APIs, and each full revision to itself.
        if opened[:4] != before[:4]:
            raise ValueError('File changed during inspection.')
        if max_bytes is None:
            _, digest = stream_signature(stream, cancelled=cancelled)
        else:
            _, digest = stream_signature(stream, cancelled=cancelled, max_bytes=max_bytes)
        if _revision(os.fstat(stream.fileno())) != opened or file_revision(path) != before:
            raise ValueError('File changed during inspection.')
    return before, bytes.fromhex(digest)


def tree_content_state(root, *, cancelled=lambda: False, max_entries=10000):
    """Map relative names to SHA-256 hex, or None for directories.

    Reject symbolic links, junctions, special files and multiply linked files.
    Hashes verify each file's revision independently, not an atomic tree view.
    """
    root = Path(root)
    def linked(path):
        return path.is_symlink() or getattr(path, 'is_junction', lambda: False)()
    if linked(root) or not root.is_dir():
        raise ValueError('Snapshot root must be an unlinked directory.')
    result, pending = {}, [root]
    while pending:
        check_cancelled(cancelled)
        for path in sorted(pending.pop().iterdir()):
            check_cancelled(cancelled)
            if linked(path):
                raise ValueError('Linked paths cannot be inventoried.')
            key = path.relative_to(root).as_posix()
            if path.is_dir():
                result[key] = None
                pending.append(path)
            else:
                info = path.stat()
                if not path.is_file() or info.st_nlink != 1:
                    raise ValueError('Choose independent regular files.')
                result[key] = verified_file_snapshot(path, cancelled=cancelled)[1].hex()
            if len(result) > max_entries:
                raise ValueError(f'Snapshot exceeds {max_entries} entries.')
    return result


def copy_content_state(root):
    """Snapshot copied bytes, kinds and raw link targets without mutation.

    Inodes and timestamps differ between copies, so they are deliberately absent.
    Caller owns source revision checks, collision policy and staged publication.
    Links are inventoried as links; ordinary hard-linked files retain byte meaning.
    """
    root = Path(root)
    result, pending = {}, [root]
    while pending:
        path = pending.pop()
        key = path.relative_to(root).as_posix()
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            result[key] = ('link', os.readlink(path))
        elif stat.S_ISREG(mode):
            result[key] = ('file', verified_file_snapshot(path)[1])
        elif stat.S_ISDIR(mode):
            result[key] = ('directory',)
            pending.extend(path.iterdir())
        else:
            raise ValueError(f'Cannot inventory a special filesystem object: {path}')
    return result
