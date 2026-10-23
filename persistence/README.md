# Persistence

Atomic byte/JSON publication, text decoding and session recovery. Atomic staging belongs beside the destination; transient workspaces belong to storage utilities.

`atomic_write_bytes` and `atomic_write_json` are exported here. `text` owns encoding/newline handling; `session.SessionStore` owns recovery metadata.

## Files

| File | Responsibility / public entry points |
| --- | --- |
| [atomic.py](atomic.py) | Atomic byte publication; format validation and overwrite policy stay with callers. |
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

## Verified publication and text sessions

[publication.py](publication.py) owns the shared staging/verification/publication
transaction and platform no-replace rename. Ordinary atomic writes and virtual
resource saves use the same sequence. See the [provider contract](../ui/resource-providers.md)
for callback ownership, cancellation and partial-failure results.

`text.TextSession` holds an in-memory baseline plus a resource key/revision. Its
`encode` and `modified` methods accept the host's draft; `accept` updates the
baseline after publication while preserving encoding and newline behavior. It has
no filesystem, account, archive or recovery policy.

## Verified transfer phases

`transfers.py` contains shared mechanics used by filesystem transfers, relocation
and virtual resource moves. `try_rename` returns false only for an `EXDEV`
cross-volume failure; other rename errors propagate. `verify_unchanged` compares a
captured state with a fresh snapshot before destructive cleanup. The caller
supplies the snapshot and exception policy.

`cleanup_published` wraps source cleanup after a verified destination exists.
Failure raises `MutationIncomplete` with `destination_published=True` and the
known source state/removals, or `unknown` if source-state inspection also fails.
It never describes a published destination as rolled back. Hosts refresh both
locations and choose recovery rather than replaying the full transfer blindly.
These helpers do not choose overwrite, link, encryption or directory-merge policy,
and provide no cross-process lock or crash-recovery journal.

## Exclusive publication with copy fallback

`exclusive_copy.link_or_copy_exclusive(staged_path, destination)` first hard-links
without replacement. For unsupported/cross-device links it exclusively creates,
copies, flushes and fsyncs the destination; failure removes only the target it
created. The staged source is retained on success and failure. Other link errors
propagate without copying. The copy fallback exposes a partial destination while
writing and is **not atomic**. Callers needing atomic no-replace publication must
continue using `publication.rename_exclusive`; the contracts are intentionally
different. Hosts own verification, replacement decisions and source deletion.
