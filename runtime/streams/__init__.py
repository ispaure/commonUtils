"""Bounded stream reading, copying and hashing with cooperative cancellation."""
from hashlib import sha256
from pathlib import Path
from operator import index
from ..operations import check_cancelled

CHUNK_SIZE = 1024 * 1024


def read_up_to(stream, limit, *, cancelled=lambda: False):
    """Read a bounded prefix through short reads, stopping at EOF or limit."""
    remaining = index(limit)
    if remaining < 0:
        raise ValueError('Read limit cannot be negative.')
    result = bytearray()
    while remaining:
        check_cancelled(cancelled)
        requested = min(CHUNK_SIZE, remaining)
        chunk = stream.read(requested)
        if chunk is None:
            raise BlockingIOError('Source cannot provide stream data yet.')
        if not chunk:
            break
        if len(chunk) > requested:
            raise OSError('Source exceeded the requested stream read count.')
        result.extend(chunk)
        remaining -= len(chunk)
    return bytes(result)


def iter_chunks(stream, *, cancelled=lambda: False):
    """Check cancellation before each read, including the final EOF read."""
    while True:
        check_cancelled(cancelled)
        chunk = stream.read(CHUNK_SIZE)
        if chunk is None:
            raise BlockingIOError('Source cannot provide stream data yet.')
        if not chunk:
            return
        yield chunk


def copy_stream(source, destination, *, cancelled=lambda: False, progress=None):
    """Copy complete chunks, retrying short writes; report each completed chunk."""
    for chunk in iter_chunks(source, cancelled=cancelled):
        pending = chunk
        while pending:
            check_cancelled(cancelled)
            written = destination.write(pending)
            if written is None:
                raise BlockingIOError('Destination cannot accept stream data yet.')
            if (not isinstance(written, int) or isinstance(written, bool)
                    or written <= 0 or written > len(pending)):
                raise OSError('Destination returned an invalid stream write count.')
            pending = memoryview(pending)[written:]
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
