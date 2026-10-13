"""Internal Markdown encoding and atomic persistence, independent of Qt widgets."""
from pathlib import Path


def _encode_markdown(text, original, modified):
    if not modified and original is not None:
        return original
    from ...persistence.text import TextSession
    return TextSession('document.md', original or b'').encode(text)


def _write_markdown(destination, data, *, expected=None):
    destination = Path(destination)
    if destination.suffix.lower() not in ('.md', '.markdown'):
        raise ValueError('Choose a .md or .markdown filename.')
    if destination.is_symlink():
        raise ValueError('Cannot replace a symlink; choose a regular file with Save As.')
    def check():
        if destination.is_symlink():
            raise ValueError('Cannot replace a symlink; choose a regular file with Save As.')
        if expected is not None and destination.read_bytes() != expected:
            raise ValueError('The file changed on disk. Use Save As to keep your edits separately, or reopen it.')
    from ...persistence import atomic_write_bytes
    atomic_write_bytes(destination, data, validate=check)
