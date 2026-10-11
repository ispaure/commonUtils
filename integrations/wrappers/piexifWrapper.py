"""Read JPEG metadata and publish comment changes without partial file writes."""
from io import BytesIO
from pathlib import Path

import piexif

from ...filesystem.traversal import scan_directory
from ...persistence import atomic_write_bytes

COMMENTS_TAG_ADDRESS = 40092


def jpg_batch_set_exif_comments(target_dir, recursive, comments):
    """Set Windows EXIF comments on regular JPEG files."""
    for path in scan_directory(target_dir, recursive=recursive):
        if not path.is_symlink() and path.suffix.lower() in ('.jpg', '.jpeg'):
            jpg_set_exif_comments(path, comments)


def jpg_set_exif_comments(jpg_file, comments):
    """Return whether a comment changed; retain a recovery copy before publication."""
    path = Path(jpg_file)
    if path.is_symlink():
        raise ValueError('JPEG metadata edits cannot replace symbolic links.')
    original = path.read_bytes()
    metadata = piexif.load(original)
    encoded = comments.encode('utf-16-le') + b'\0\0'
    if bytes(metadata['0th'].get(COMMENTS_TAG_ADDRESS, ())) == encoded:
        return False
    metadata['0th'][COMMENTS_TAG_ADDRESS] = tuple(encoded)
    output = BytesIO()
    piexif.insert(piexif.dump(metadata), original, output)
    content = output.getvalue()
    piexif.load(content)  # Validate the staged metadata before touching the source.

    def unchanged():
        if path.is_symlink() or path.read_bytes() != original:
            raise RuntimeError(f'JPEG changed during metadata editing: {path}')

    backup = path.with_name(path.name + '.before-comments')
    if not backup.exists():
        atomic_write_bytes(backup, original, overwrite=False)
    atomic_write_bytes(path, content, validate=unchanged)
    return True
