# Persistence

Atomic byte/JSON publication, text decoding and session recovery. Atomic staging belongs beside the destination; transient workspaces belong to storage utilities.

`atomic_write_bytes` and `atomic_write_json` are exported here. `text` owns encoding/newline handling; `session.SessionStore` owns recovery metadata.

## Files

| File | Responsibility / public entry points |
| --- | --- |
| [__init__.py](__init__.py) | Atomic byte publication; format validation and overwrite policy stay with callers. |
| [session.py](session.py) | Versioned, bounded, atomic private JSON checkpoints without Qt dependencies. |
| [text.py](text.py) | Bounded text recognition and conflict-checked, lossless atomic text writes. |

[Parent guide](../README.md)
