"""Seekable read-only streams over bounded range callbacks; no disk cache."""
from collections import OrderedDict
from io import RawIOBase, SEEK_SET, SEEK_CUR, SEEK_END
from operator import index


class RangeReader(RawIOBase):
    def __init__(self, size, read_range, *, block_size=1024 * 1024, cache_blocks=8, max_read=128 * 1024 * 1024, validate=None):
        super().__init__()
        if size < 0 or block_size <= 0 or cache_blocks < 0:
            raise ValueError('Invalid range reader limits.')
        self.size, self.read_range = size, read_range
        self.block_size, self.cache_blocks, self.max_read = block_size, cache_blocks, max_read
        self.position = 0
        self.validate = validate
        self.blocks = OrderedDict()

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        self._checkClosed()
        return self.position

    def seek(self, offset, whence=SEEK_SET):
        self._checkClosed()
        offset, whence = index(offset), index(whence)
        if self.validate:
            self.validate()
        base = {SEEK_SET: 0, SEEK_CUR: self.position, SEEK_END: self.size}.get(whence)
        if base is None or base + offset < 0:
            raise ValueError('Invalid seek.')
        self.position = base + offset
        return self.position

    def read(self, count=-1):
        self._checkClosed()
        count = index(count)
        if self.validate:
            self.validate()
        count = max(0, self.size - self.position) if count < 0 else min(count, max(0, self.size - self.position))
        if count > self.max_read:
            raise ValueError('Read exceeds its memory limit.')
        result = bytearray()
        while count:
            block = self.position // self.block_size
            if block not in self.blocks:
                start = block * self.block_size
                length = min(self.block_size, self.size - start)
                data = self.read_range(start, length)
                if not isinstance(data, bytes) or len(data) != length:
                    raise OSError('The document changed or its range is incomplete.')
                self.blocks[block] = data
            self.blocks.move_to_end(block)
            data = self.blocks[block]
            offset = self.position % self.block_size
            part = data[offset:offset + count]
            result.extend(part)
            self.position += len(part)
            count -= len(part)
            while len(self.blocks) > self.cache_blocks:
                self.blocks.popitem(last=False)
        return bytes(result)

    def readinto(self, buffer):
        self._checkClosed()
        with memoryview(buffer) as destination:
            if destination.readonly:
                raise TypeError('readinto() requires a writable bytes-like buffer.')
            if not destination.c_contiguous:
                # Retain the existing one-dimensional strided byte-view support.
                if destination.ndim != 1 or destination.format != 'B':
                    raise TypeError('readinto() requires a contiguous typed buffer or a byte view.')
                value = self.read(destination.nbytes)
                destination[:len(value)] = value
                return len(value)
            with destination.cast('B') as raw:
                value = self.read(raw.nbytes)
                raw[:len(value)] = value
                return len(value)

    def close(self):
        self.blocks.clear()
        super().close()
