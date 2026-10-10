# streams

Bounded stream reading, copying and hashing with cooperative cancellation.

Import from `commonUtils.streams`. Implementation and public exports live in
[`__init__.py`](__init__.py).

Public entry points: `iter_chunks`, `copy_stream`, `stream_signature`, `file_sha256`

[Library overview](../README.md).

`downloads.py` owns the historical `downloads` implementation; its compatibility
package preserves existing consumers.

## API behavior

| Entry point | Purpose |
| --- | --- |
| `iter_chunks` | Check cancellation before each read, including the final EOF read. |
| `copy_stream` | Copy bounded chunks; progress receives the bytes written for each chunk. |
| `stream_signature` | Return (byte count, SHA-256); progress receives each chunk's byte count. |
