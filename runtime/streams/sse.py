"""Bounded incremental data-only SSE framing, independent of event schemas."""


class SSERecordLimit(ValueError):
    """The pending bytes exceed the configured record buffer limit."""


class SSEDataDecoder:
    """Yield data fields on blank LF/CRLF lines, decoding complete UTF-8 events.

    Other fields/comments are ignored. Pending records are not flushed at EOF.
    The limit applies before consuming each incoming chunk, including pending
    data fields. Callers own event schemas, completion markers and total limits.
    """

    def __init__(self, *, max_record):
        self.max_record = max_record
        self.buffer = b""
        self.lines = []

    def feed(self, chunk):
        self.buffer += chunk
        if len(self.buffer) + sum(map(len, self.lines)) > self.max_record:
            raise SSERecordLimit("Stream record exceeds the size limit.")
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            line = line.rstrip(b"\r")
            if line:
                if line.startswith(b"data:"):
                    self.lines.append(line[5:].lstrip(b" "))
            elif self.lines:
                value = b"\n".join(self.lines).decode("utf-8")
                self.lines.clear()
                yield value
