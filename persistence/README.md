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

## Atomic persistence

`persistence.atomic_write_bytes(path, data, validate=None, overwrite=True)` stages
bytes beside the destination, flushes them, preserves existing permissions and
validates again before publication. No encoding, extension, symlink or size policy
is imposed. `overwrite=False` uses atomic no-clobber creation.

`atomic_write_json` adds caller-selected serialization, byte limits and optional
parent-directory durability. Callers create directories with their own permission
policy and retain their own schemas. TextSnapshot, Markdown and INI save paths
continue to own their format-specific rules. `configuration.legacy` retains the existing configuration behavior.

## Save a small settings file

Create the directory first, then save JSON. A serialization or replacement error
keeps the previous file available.

```python
from pathlib import Path
from commonUtils.persistence import atomic_write_json

settings = Path.home() / '.my-tool' / 'settings.json'
settings.parent.mkdir(parents=True, exist_ok=True)
atomic_write_json(settings, {'theme': 'dark', 'recent_folders': []})
```

## Replace an installation with a recovery copy

Build and validate the new installation in a temporary directory on the same
filesystem, then publish it. The previous installation stays beside the new one.
Keep it until you have checked that the application works.

```python
from pathlib import Path
from commonUtils.persistence import promote_path

previous = promote_path(Path('/apps/.staged-tool'), Path('/apps/tool'))
if previous is not None:
    print('Recovery copy:', previous)
```

If promotion fails, the helper restores the old path before raising. It refuses
symbolic links and junctions. Callers supply installation validation and decide
when recovery copies can be removed.
