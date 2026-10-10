"""Bounded stream reading, copying and hashing with cooperative cancellation."""
from hashlib import sha256
from pathlib import Path
from ..operations import check_cancelled

CHUNK_SIZE = 1024 * 1024


def iter_chunks(stream, *, cancelled=lambda: False):
    """Check cancellation before each read, including the final EOF read."""
    while True:
        check_cancelled(cancelled)
        chunk = stream.read(CHUNK_SIZE)
        if not chunk:
            return
        yield chunk


def copy_stream(source, destination, *, cancelled=lambda: False, progress=None):
    """Copy bounded chunks; progress receives the bytes written for each chunk."""
    for chunk in iter_chunks(source, cancelled=cancelled):
        destination.write(chunk)
        if progress:
            progress(len(chunk))


def stream_signature(stream, *, cancelled=lambda: False, progress=None):
    """Return (byte count, SHA-256); progress receives each chunk's byte count."""
    total, digest = 0, sha256()
    for chunk in iter_chunks(stream, cancelled=cancelled):
        total += len(chunk)
        digest.update(chunk)
        if progress:
            progress(len(chunk))
    return total, digest.hexdigest()


def file_sha256(path, *, cancelled=lambda: False):
    with Path(path).open('rb') as stream:
        return stream_signature(stream, cancelled=cancelled)[1]
