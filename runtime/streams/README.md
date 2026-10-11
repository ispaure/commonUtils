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
