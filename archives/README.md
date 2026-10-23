# Archive operations

ZIP/TAR listing, creation, safe extraction, editing, integrity checks and bounded previews. Domain operations have no UI dependencies. Passwords, progress and cancellation are supplied by callers.

See [ZIP access](zip_access.md) and the contracts below.

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

`archives.zip_access` provides password-aware ZIP access.

## ZIP and TAR archives

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

The existing [ZIP API](zip_access.md) remains available. Archive creation and
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
`commonUtils.runtime.operations.OperationCancelled` and discards staged work; publication
is the success boundary.

ZIP integrity checks read all entries and validate CRCs or AES authentication.
TAR checks readable data and member paths, but TAR has no per-entry payload
checksum. Text previews display at most 256 KiB of UTF-8. A multibyte character
split by the preview ceiling is omitted while the complete prefix and truncation
notice remain visible. Malformed UTF-8 inside that prefix, or an incomplete final
character in a complete file, retains the unsupported-text fallback. Image previews accept up
to 16 MiB and 25 megapixels, return a PNG thumbnail up to 1000 pixels, and show
only the first image frame. Decoding never runs or opens an archive member.

## File browser hooks

`ArchiveFile` is resolved for TAR suffixes, including compound `.tar.gz`, `.tar.xz`
and `.tar.bz2` names. It does not claim ordinary `.gz`/`.xz` files. `ZIPFile`
inherits its **Archive Contents** panel. Panel loaders return `BrowserDetails`
on the browser worker, showing counts, unpacked size, protection and up to 40
entry names; encrypted headers can be inspected without prompting.

Applications contribute opening, extracting and creation actions through
[`Feature`, `SelectionAction` and `FileActivation`](../ui/features/README.md). Keep passwords,
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

Plain ZIP access through `zip_access` uses the standard library without importing
pyzipper. Encrypted ZIP access loads pyzipper on demand and raises an explanatory
RuntimeError if it is absent. This allows unencrypted EPUB/CBZ container I/O in
portable code; rendering and mobile deployment are separate concerns.

## Open-adapter rebuilding

`rebuilding.content_manifest(archive)` hashes open archive adapters, using an
explicit native `content_manifest` shortcut when available. `patched_manifest`
accepts replacement-name/bytes mappings. `rewrite_members(original, output,
replacements, first=(), stored=(), max_member_bytes=None, cancelled=...)` streams
unchanged members, preserves comments/portable member attributes and returns
expected content hashes. Hosts validate inputs, configure encryption, verify the
finished output and publish it. Entry ordering and compression overrides are explicit
names; this layer contains no EPUB/comic rules.

## Member plans and streamed writes

`rebuilding.member_plan(original, replacements, include=None, first=(), stored=())`
yields `MemberOperation` records for retained/replaced members followed by new
replacements. `include` filters existing members; replacements not retained by
that filter are still appended. `first` ranks existing members and `stored`
selects uncompressed output names. It is an operation iterator, not input/path
validation or a publication transaction.

`write_members` consumes that plan, streams unchanged files, checks cancellation
between members/chunks and returns an expected name-to-length/SHA-256 manifest
(with `None` for directories). `max_member_bytes` bounds streamed original members;
callers must bound replacement bytes separately. `rewrite_members` combines the
plan/write path and preserves the archive comment by default.

`members.copy_member_info` copies portable timestamps, comments, platform and
attribute fields into the output adapter's ZipInfo type; crypto flags/headers
are not copied. `members.name_key` supplies normalized identity for callers'
collision checks. Editing/access entry points retain their own validation,
authentication, staging and finished-output verification. EPUB ordering and
comic metadata rules remain consumer policy. Focused regressions live in
`tests/test_archive_rebuilding.py` and archive operation tests.

## Callback-backed member views

`callbacks.CallbackArchive(members, read_member=..., manifest=None)` adapts explicit
`ZipInfo` records and a lazy byte callback to `infolist`, `namelist`, `getinfo`,
`read` and context-managed `open`. Unknown member names fail before invoking the
callback. An optional manifest callback returns member signatures; cancellation
is checked before and after it runs. No file, credential or password is opened by
the facade. The backend owns authentication, size limits, revision checks, caching
and retirement. `open` wraps a complete member in RAM; it is not a streaming API.

## Extraction publication

`extract` validates the archive and stages the entire selection beside the new
output directory. The complete tree is published using an atomic no-replace
rename. A racing file, directory or link is preserved; failed publication cleans
only private staging. There is no public partial output to recursively remove on
failure. Cancellation is checked immediately before publication. Unsupported
atomic no-replace platforms fail closed rather than reverting to per-child moves.
