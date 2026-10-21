"""Explicit cumulative read measurements; stream ownership stays with the caller."""
from contextlib import contextmanager
import os
import stat


class ReadingStream:
    def __init__(self, stream, progress, total):
        self.stream, self.progress, self.total = stream, progress, total
        self.completed = 0

    def __getattr__(self, name):
        return getattr(self.stream, name)

    def read(self, size=-1):
        # Bound individual reads even when a text reader asks for the whole file.
        remaining = -1 if size is None else size
        chunks = []
        while remaining != 0:
            chunk = self.stream.read(64 * 1024 if remaining < 0 else min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            self.completed += len(chunk)
            self.progress(self.completed, self.total)
            if remaining > 0:
                remaining -= len(chunk)
        return b''.join(chunks)


@contextmanager
def reading_stream(stream, *, progress=None, total=None):
    if progress is None:
        yield stream
        return
    if total is None:
        try:
            info = os.fstat(stream.fileno())
            if stat.S_ISREG(info.st_mode):
                total = max(0, info.st_size - stream.tell())
        except (AttributeError, OSError, ValueError):
            pass
    if type(total) is not int or total < 0:
        total = None
    progress(0, total)
    try:
        yield ReadingStream(stream, progress, total)
    finally:
        progress(None, None)


class ReadingProvider:
    def __init__(self, provider, *, progress=None):
        self.provider = provider
        self.progress = progress

    def __getattr__(self, name):
        return getattr(self.provider, name)

    @contextmanager
    def open(self, path):
        total = self.provider.entry(path).get('size')
        with self.provider.open(path) as stream, reading_stream(stream, progress=self.progress, total=total) as incoming:
            yield incoming
