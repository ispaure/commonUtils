# ZIP and TAR archives

`commonUtils.archives` is an application-independent archive API. It accepts
explicit passwords and cooperative cancellation callbacks. It does not load Qt,
read configuration, retain passwords, prompt, navigate windows or launch files.
Format constants and immutable `Entry` metadata load without cryptography or
image decoders; operational modules are imported on first use.

```python
from pathlib import Path
from commonUtils import archives

source = Path('/data/notes.txt')
output = Path('/data/notes.zip')
archives.create([source], output, level=6)  # existing outputs are retained
headers = archives.entries(output)        # encrypted headers need no password
archives.extract(output, Path('/data/unpacked'), selected=['notes.txt'])
archives.test_archive(output)
```

Use ZIP (including AES ZIP and CBZ) or TAR, TAR.gz/TGZ, TAR.xz/TXZ and
TAR.bz2/TBZ2 for reading. Creation supports `format='zip'`, `'tar'`, `'tar.gz'`
and `'tar.xz'`. ZIP levels 0, 1, 6 and 9 correspond to Store, Fast, Balanced and
Maximum; levels 1–9 use DEFLATE. Passwords encrypt ZIP payloads with AES-256;
entry names remain visible. 7z, RAR and split archives are unsupported.

## Modules and ownership

| Module | Responsibility |
| --- | --- |
| `archives/formats.py` | Shared suffix matching, image suffixes and dialog filter |
| `archives/models.py` | Immutable entry metadata |
| `archives/reading.py` | Validated readers, header inspection and integrity checks |
| `archives/extraction.py` | Selected/whole extraction into a new folder |
| `archives/creation.py` | Verified ZIP/TAR creation |
| `archives/editing.py` | Verified atomic ZIP rebuilding |
| `archives/previews.py` | Bounded text and image decoding |
| `fileTypes/archiveType.py` | Passive `ArchiveFile` information hooks and TAR resolution |
| `ui/archive_view/` | Passive Qt folder navigation, sorting, selection and previews |

The existing [ZIP API](ZIP_ARCHIVES.md) remains available. Archive creation and
editing reuse its verified writes, metadata copying and decrypted manifests, plus
shared streams and cancellation. Existing `ZIPFile` extraction methods retain
their behavior; its new `ArchiveFile` base adds inspection and
`extract_to_new_directory` without replacing those methods.

## Publication and validation

Extraction validates the entire member list, stages the requested selection,
then reserves the new destination with exclusive `mkdir`. Existing folders are
never merged or replaced. Cancellation, wrong passwords and corrupt payloads
leave no partial destination. Member names, Unicode/case collisions, path
traversal, symbolic links and special TAR entries are rejected before payloads
are extracted. File timestamps, empty directories and Unix executable bits are
retained; ownership and setuid bits are not restored.

Creation verifies staged payload hashes before exclusive publication. ZIP edits
preserve the original until a rebuilt archive passes decrypted manifest checks
and its source identity is unchanged. Additions do not silently replace names;
removing a directory removes its descendants. Mixed encrypted/plain ZIPs cannot
be rewritten. Source files are never deleted. Cancellation raises
`commonUtils.operations.OperationCancelled` and discards staged work; publication
is the success boundary.

ZIP integrity checks read all entries and validate CRCs or AES authentication.
TAR checks readable data and member paths, but TAR has no per-entry payload
checksum. Text previews read at most 256 KiB of UTF-8. Image previews accept up
to 16 MiB and 25 megapixels, return a PNG thumbnail up to 1000 pixels, and show
only the first image frame. Decoding never runs or opens an archive member.

## File browser hooks

`ArchiveFile` is resolved for TAR suffixes, including compound `.tar.gz`, `.tar.xz`
and `.tar.bz2` names. It does not claim ordinary `.gz`/`.xz` files. `ZIPFile`
inherits its **Archive Contents** panel. Panel loaders return `BrowserDetails`
on the browser worker, showing counts, unpacked size, protection and up to 40
entry names; encrypted headers can be inspected without prompting.

Applications contribute opening, extracting and creation actions through
[`Feature`, `SelectionAction` and `FileActivation`](FEATURES.md). Keep passwords,
window routing and mutations in those application-owned handlers. The generic
file browser contains no application-specific archive manager or routing rules.
Specialized readers can override panels and keep their own activation behavior.

## Reuse the Qt contents view

```python
from commonUtils.ui.archive_view import ArchiveContents

contents = ArchiveContents(parent)
contents.set_entries(output, headers)
contents.preview_requested.connect(request_preview)
contents.extract_requested.connect(request_extraction)
contents.remove_requested.connect(request_removal)
contents.set_state(busy=False, editable=True)
# After a background decode completes on the GUI thread:
contents.show_preview('Decoded UTF-8 text')  # or PNG thumbnail bytes
```

The owner runs jobs, handles the request signals and supplies previews. The view
owns only folders, filtering, numeric sorting, entry details and aspect-preserving
image display. It has no filesystem writes, password prompts, workers or
application navigation. `set_state` controls interaction and whether removal is
offered. `context_menu()` builds the selection menu without opening a popup.

Regression coverage lives in `tests/test_archives.py`, `test_archive_types.py`,
`test_archive_view.py` and the existing ZIP tests. Consumer tests should focus on
routing, credential policy, browser refresh, feature toggles and shutdown.
