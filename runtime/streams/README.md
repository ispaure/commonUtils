# streams

Bounded stream reading, copying and hashing with cooperative cancellation.

Import from `commonUtils.runtime.streams`. Implementation and public exports live in
[`__init__.py`](__init__.py).

Public entry points: `read_up_to`, `iter_chunks`, `copy_stream`, `stream_signature`, `file_sha256`

[Library overview](../../README.md).

`runtime.streams.downloads` provides verified download publication.

## API behavior

| Entry point | Purpose |
| --- | --- |
| `read_up_to` | Read through short reads until EOF or a nonnegative byte ceiling; leave the remaining stream unread. |
| `iter_chunks` | Check cancellation before each read, including the final EOF read. |
| `copy_stream` | Complete short writes; progress receives each completed read chunk’s byte count. |
| `stream_signature` | Return (byte count, SHA-256); progress receives each chunk's byte count; optional `max_bytes` rejects oversized input. |

## Copy and hash bounded streams

`read_up_to(stream, limit, cancelled=...)` returns at most `limit` bytes, reading
in requests of at most 1 MiB and checking cancellation before each request. Zero
performs no I/O. Short reads continue; `None` raises `BlockingIOError` and a source
returning more than requested raises `OSError`. The helper does not close the
stream or decide whether a longer input is allowed. To enforce a maximum payload,
read `maximum + 1` and reject a result longer than `maximum` before decoding it.

`stream_signature(..., max_bytes=N)` rejects input exceeding a nonnegative integer
limit with `ValueError`; the default `None` retains unbounded hashing. It reads in
the existing 1 MiB chunks, so detecting overflow may consume one chunk beyond the
limit. It never returns a digest of a truncated prefix. Invalid limits fail before
stream reads. `filesystem.snapshots.verified_file_snapshot(..., max_bytes=N)`
forwards the same bound while retaining its path/descriptor revision checks.

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

Binary destinations must return the number of bytes accepted by `write`. Short
writes are completed before reporting that read chunk; cancellation is checked
between partial writes as well as reads. Zero, negative, oversized or non-integer
counts raise `OSError` rather than losing data or spinning. A `None` read/write
result signals would-block and raises `BlockingIOError`; these blocking helpers
do not schedule asynchronous readiness or mistake it for EOF. Errors leave the
already-written prefix for the caller’s staging/cleanup policy.

## Measured reads

`runtime.streams.progress.reading_stream(stream, progress=None, total=None)`
wraps binary `.read()` calls in at most 64 KiB reads and reports cumulative
`(completed, total)` values. Unknown totals are `None`; ordinary file totals are
inferred from the remaining bytes. Without a callback it yields the original
stream. Entry emits `(0, total)` and scope exit emits `(None, None)`, including on
failure. It does not close the underlying stream. Other delegated stream methods
are not measured. `ReadingProvider(provider, progress=...)` applies the same
measurement to a provider's `open()` using its entry size.
Measured reads retain short-read completion and reject `None` or oversized
underlying results; observing progress cannot turn incomplete input into EOF or
a bounded read into an unlimited read. Failure still retires the progress scope.

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

`write_all(destination, data, cancelled=...)` completes one byte buffer using
the same partial-write and cancellation contract as `copy_stream`. It returns
only after the buffer is accepted; would-block and invalid/nonpositive counts
raise instead of reporting success. Archive member streaming uses this owner.
