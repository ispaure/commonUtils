# Archive operations

ZIP/TAR listing, creation, safe extraction, editing, integrity checks and bounded previews. Domain operations have no UI dependencies. Passwords, progress and cancellation are supplied by callers.

See [archive contracts](../ARCHIVES.md) and [ZIP compatibility](../ZIP_ARCHIVES.md).

## Files

| File | Responsibility / public entry points |
| --- | --- |
| [__init__.py](__init__.py) | Reusable ZIP/TAR operations with bounded streams and verified staged writes. |
| [creation.py](creation.py) | Verified ZIP/TAR creation without deleting or replacing input files. |
| [editing.py](editing.py) | Verified atomic ZIP rebuilding with explicit additions and removals. |
| [extraction.py](extraction.py) | Transactional extraction of whole archives or selected subtrees. |
| [formats.py](formats.py) | Supported suffixes shared by models, dialogs, drag/drop and activation. |
| [models.py](models.py) | Immutable archive metadata; importing this module requires no GUI. |
| [previews.py](previews.py) | Bounded archive text/image decoding; no launching, prompts or GUI objects. |
| [reading.py](reading.py) | Validated ZIP/TAR readers, header inspection and integrity checks. |

[Parent guide](../README.md)
