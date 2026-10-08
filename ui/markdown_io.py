"""Internal Markdown encoding and atomic persistence, independent of Qt widgets."""
import os
from pathlib import Path
import stat
from tempfile import NamedTemporaryFile


def _encode_markdown(text, original, modified):
    if not modified and original is not None:
        return original
    source = original or b''
    if b'\r\n' in source and b'\n' not in source.replace(b'\r\n', b''):
        text = text.replace('\n', '\r\n')
    encoded = text.encode('utf-8')
    return b'\xef\xbb\xbf' + encoded if source.startswith(b'\xef\xbb\xbf') else encoded


def _write_markdown(destination, data, *, expected=None):
    destination = Path(destination)
    if destination.suffix.lower() not in ('.md', '.markdown'):
        raise ValueError('Choose a .md or .markdown filename.')
    if destination.is_symlink():
        raise ValueError('Cannot replace a symlink; choose a regular file with Save As.')
    if expected is not None and destination.read_bytes() != expected:
        raise ValueError('The file changed on disk. Use Save As to keep your edits separately, or reopen it.')
    mode = stat.S_IMODE(destination.stat().st_mode) if destination.exists() else None
    staged = None
    try:
        with NamedTemporaryFile(dir=destination.parent, prefix=f'.{destination.name}-',
                                suffix='.tmp', delete=False) as output:
            staged = Path(output.name)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        if mode is not None:
            staged.chmod(mode)
        os.replace(staged, destination)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
