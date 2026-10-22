# streams

Bounded stream reading, copying and hashing with cooperative cancellation.

Import from `commonUtils.runtime.streams`. Implementation and public exports live in
[`__init__.py`](__init__.py).

Public entry points: `iter_chunks`, `copy_stream`, `stream_signature`, `file_sha256`

[Library overview](../../README.md).

`runtime.streams.downloads` provides verified download publication.

## API behavior

| Entry point | Purpose |
| --- | --- |
| `iter_chunks` | Check cancellation before each read, including the final EOF read. |
| `copy_stream` | Copy bounded chunks; progress receives the bytes written for each chunk. |
| `stream_signature` | Return (byte count, SHA-256); progress receives each chunk's byte count. |

## Copy and hash bounded streams

Stream progress callbacks receive the **current chunk's size**, not a cumulative
count. Download progress receives cumulative bytes; `OperationProgress` receives
(done, total, message). Translate deliberately between those interfaces.

```python
from hashlib import sha256
from io import BytesIO
from threading import Event
from commonUtils.runtime.streams import copy_stream, stream_signature

cancel = Event()
source = BytesIO(b'example payload')
output = BytesIO()
chunks = []
copy_stream(source, output, progress=chunks.append, cancelled=cancel.is_set)
assert sum(chunks) == len(output.getvalue())
assert stream_signature(BytesIO(output.getvalue())) == (
    len(output.getvalue()), sha256(output.getvalue()).hexdigest())
```

`iter_chunks` reads bounded 1 MiB chunks and checks cancellation before each read,
including the final EOF read. `file_sha256(path, cancelled=...)` hashes a file using
the same rules. Cancellation raises `OperationCancelled`; a partial copy remains
in the supplied output stream. These helpers do not delete files or publish staged
outputs. Use a disposable destination and promote only after your own validation.

## Measured reads

`runtime.streams.progress.reading_stream(stream, progress=None, total=None)`
wraps binary `.read()` calls in at most 64 KiB reads and reports cumulative
`(completed, total)` values. Unknown totals are `None`; ordinary file totals are
inferred from the remaining bytes. Without a callback it yields the original
stream. Entry emits `(0, total)` and scope exit emits `(None, None)`, including on
failure. It does not close the underlying stream. Other delegated stream methods
are not measured. `ReadingProvider(provider, progress=...)` applies the same
measurement to a provider's `open()` using its entry size.

`runtime.progress.CoalescedProgress(loop, changed, active=..., interval=.05)`
accepts `publish(completed=None, total=None)` from workers and coalesces updates
onto the owning loop. `changed(completed, total)` runs only while `active()`.
Call `close()` on that loop before retiring the owner; late publications become
no-ops. The caller chooses status text, percent/indeterminate presentation and
active-session policy. Unlike copy/hash callbacks, these counts are cumulative.

## Incremental data events

`sse.SSEDataDecoder(max_record=...)` yields UTF-8 data payloads from blank-line
separated LF/CRLF events, joining multiple `data:` fields with a newline. Other
fields and comments are ignored; this is data-only framing, not a full SSE client.
Pending records remain buffered at EOF. Limits apply to pending data plus the
incoming chunk before consumption; overflow raises `SSERecordLimit`. Iterate each
feed before feeding again. Application completion markers, JSON schemas, total
response limits and tool semantics belong to the caller.
