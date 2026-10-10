# Developer reference

For an overview and a quick example, start with [the README](README.md).

commonUtils is a shared Python tools library for filesystem work, file formats,
configuration, processes, platform integration and desktop UI. Applications own
their domain logic, credentials and software policy; this library supplies reusable
mechanics. It is imported by other projects rather than launched on its own.

## Use it in a project

Python **3.10+** is required. The repository itself is the `commonUtils` package;
there is currently no `pyproject.toml` or `setup.py` for installing it as a wheel.
Place it beneath a directory on your Python import path, often as a Git submodule:

```text
my_project/
└── Python/                 # Add this directory to PYTHONPATH.
    ├── launch.py
    └── commonUtils/
```

```sh
# Run from my_project (macOS / Linux).
PYTHONPATH=Python python Python/launch.py
```

On PowerShell, set `$env:PYTHONPATH = "Python"` before running your interpreter.
For submodule checkouts, initialize with `git submodule update --init --recursive`.

Import only the tools you need:

```python
from pathlib import Path
from commonUtils.dirUtils import Directory
from commonUtils.fileTypes.jsonType import JSONFile

# Use an existing input directory.
files = Directory(Path('data')).list_files(filter_extension='txt')
settings = JSONFile('settings.json')
settings.write_json({'enabled': True}, sort_keys=True)
print(settings.read_json())
```

Directory listing is recursive by default and resolves registered file types
without reading their contents. JSON writes stage and replace atomically;
missing/malformed reads raise exceptions for the application to handle.

## Guides and examples

| Task | Guide |
| --- | --- |
| Add a right-click action, custom file type, preview panel or double-click handler | [File-browser feature guide](FEATURES.md) |
| Run work off the GUI thread, show progress and cancel safely | [Background-operation recipes](RECIPES.md#run-a-cancellable-job-in-a-qt-dialog) |
| Finish the current item before cancelling a batch | [Batch recipe](RECIPES.md#finish-the-current-item-before-cancelling-a-batch) |
| Copy/hash streams or provision a pinned download | [Stream and download recipes](RECIPES.md) |
| Plan and batch-rename files/folders with rollback and undo | [Rename engine](RENAME.md) |
| Read/edit Markdown, navigate headings and save documents | [Markdown reader](ui/README.md#markdown-reader) |
| Embed a browser, manage navigation and close workers safely | [UI guide](ui/README.md#reusable-file-browser) |
| Query/edit nested XML with namespaces and save atomically | [XML documents](XML.md) |
| Read/write text, CSV, JSON or register a domain format | [File types](fileTypes/README.md) |
| Read, extract, create or verify ZIPs | [Archive guide](ZIP_ARCHIVES.md) |
| Execute commands and understand timeout/platform behavior | [Command wrapper](wrappers/cmdShellWrapper/README.md) |

The feature guide includes a complete runnable browser example. Lower-level browser
services and providers remain supported for existing integrations, but new features
can declare type rules, actions, activation and controller ownership together.

## Module map

| Module/package | Provides |
| --- | --- |
| `directory` | Persistent indexing, metadata, search, reconciliation and directory totals |
| `persistence` | Atomic byte/JSON publication; `text` snapshots and `session` recovery storage |
| `traversal` | Filtered scans, natural path ordering and cooperative cancellation without link traversal |
| `renameUtils` | Filename rules, rename plans, no-overwrite batches, cancellation and undo receipts |
| `fileUtils` | `File`, path metadata, copy/move/rename and user/application-data paths |
| `dirUtils` | `Directory`, traversal, creation, opening and deletion |
| `filesystem` | Shared object abstraction, browser action/panel/details descriptors and folder totals |
| `fileTypes` | Explicit subclass overrides ([example](fileTypes/README.md#replace-an-existing-type-with-your-subclass)); TXT, CSV, JSON, INI, XML, Markdown, ZIP, DMG and AppImage classes; process-wide type registry |
| `linkUtils` | Symbolic links and Windows junction-aware operations |
| `osUtils` | `OS`, architecture detection and platform-specific path selection |
| `appUtils` | Disk, Store, Flatpak and AppImage application launch helpers |
| `wrappers/cmdShellWrapper` | Captured commands, terminals, idle-output timeouts and process termination |
| `wrappers/powerShellWrapper` | Windows PowerShell workflows |
| `configUtils` | Legacy INI section mapping and configuration updates |
| `configuration` | Optional typed INI schema; see the [configuration guide](configuration/README.md) |
| `debugUtils` / `logUtils` | Diagnostics, severity handling and log helpers |
| `streams` | Bounded reading, copying and SHA-256 with cooperative cancellation |
| `operations` | Cancellation exception/checks and per-item batch results |
| `downloads` | Verified staging and atomic provisioning of a file or named ZIP member |
| `features` | Qt-independent declarations for owned types and browser capabilities |
| `ui` | Lazy native/PySide backends, dialogs, widgets and file browser |
| `ui/operations` | Background Qt callback worker, without browser dependencies |
| `ui/operation_progress` | Queued progress, cancellation and completion after worker shutdown |
| `ui/download` | Confirmed provisioning with background progress |
| `zip_access` | Plain, ZipCrypto and AES archive access, verification and safe creation |
| `zipUtils` | Compatibility ZIP helpers and external RAR extraction |
| `spreadsheetUtils` | Lightweight CSV-backed Spreadsheet, Row and Cell objects |
| `webUtils` / `steamUtils` | URL opening and Steam environment helpers |
| `marcUtils` | Maintainer-specific helpers |

`Directory.list_files()` and `file_from_path()` use process-wide registration.
Direct `File(path)` construction stays generic. Higher-priority rules win, with
newer registrations breaking ties; owned feature rules can be disabled. Existing
objects keep their class, while browsers re-resolve after registry changes.
See [registration examples](fileTypes/README.md#file-type-resolution).

## Optional dependencies and platforms

The consuming application manages dependencies. Importing a module may require
its own extras; this repository does not supply one exhaustive install command.

| Capability | Requirements |
| --- | --- |
| Qt browser, workers and PySide UI | `PySide6`; create one QApplication before widgets |
| Shared ZIP APIs | `pyzipper` is required on import; ordinary ZIP data uses `zipfile` |
| External archive/RAR extraction | `patool` (`patoolib` import) and format-specific system extractors |
| EXIF wrapper | `piexif` |
| Platform workflows | Relevant system tools, such as PowerShell, `hdiutil` or Flatpak |

Windows, macOS and Linux are supported at the library level; individual operations
can remain platform-specific. Route platform choices through `osUtils` and consult
the relevant module before relying on an external tool.

```python
from commonUtils.osUtils import get_os, get_arch, OS

if get_os() == OS.WIN:
    print('Windows-specific workflow')
print(get_arch())
```

The generic UI lazily selects its backend; applications needing Qt objects should
explicitly import `commonUtils.ui.pyside` and initialize QApplication once.
Native UI access does not itself import PySide. The default `ui.use_pyside=True`
assumes a QApplication already exists when PySide is available; fallback cannot
recover from Qt aborting because no application exists. For standalone scripts,
select the native backend explicitly:

```python
from commonUtils import ui
from commonUtils.debugUtils import log, Severity

log(Severity.INFO, 'Example', 'Operation completed')
ui.use_pyside = False  # Standalone script without a QApplication.
ui.display_msg_box_ok('Example', 'Operation completed')
```

`Severity.CRITICAL` raises `DebugException`. Shared Qt workers use
`noninteractive_logging` so failures cannot open dialogs from the worker thread;
GUI owners receive and present the error. Callbacks must not prompt or touch widgets.

## Filesystem and operation contracts

- Directory traversal follows directory links while detecting recursive loops.
  Deleting a Directory that represents a symbolic link or junction removes the
  link itself, retaining its target.
- `Directory.delete_contents()` refuses a linked root unless
  `follow_root_link=True` explicitly permits target-content deletion.
- `linkUtils.update_symbolic_link()` refuses to replace a real destination unless
  `allow_destination_deletion=True` is supplied.
- Cancellation is cooperative. Stream helpers check between chunks; a blocking
  read must return before cancellation can be observed. The caller owns staging
  and transaction boundaries.
- `OperationProgress.completed(result, error)` arrives after worker shutdown.
  Keep the owner alive until then and route close/Escape to cancellation during work.
- `run_batch` finishes each item before observing cancellation. Its result records
  completed items, per-item failures and the unprocessed remainder. An error-free
  Qt callback can still return a batch containing individual failures.
- Downloads verify both release and installed hashes before promotion. Applications
  supply URLs, versions, platform choice and destination; commonUtils does not
  automatically choose software or install drivers.
- ZIP creation preserves sources and existing destinations, verifies decrypted
  content and checks cancellation before publication. Extraction is staged per
  file, rather than a transaction across the whole archive. See the archive guide.
- `cmdShellWrapper.exec_cmd(time_out=...)` uses an **idle-output timeout**, not a
  maximum runtime; ongoing output can keep the command alive.

These contracts are operation-specific. A shared stream copy alone does not make
a file replacement atomic, and using a progress widget does not make arbitrary
callbacks cancellable.

## Development and validation

Keep domain-specific file classes, application configuration and platform software
manifests in the consuming project. Reusable code should preserve established
public names, arguments and fields so dependent projects can update safely.

From the package's parent directory, run its tests with the project interpreter:

```sh
QT_QPA_PLATFORM=offscreen python -m unittest discover -s commonUtils/tests -v
```

For a checkout beneath `Python/`, run from the application's root:

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=Python python -m unittest discover -s Python/commonUtils/tests -v
```

On PowerShell, set `$env:QT_QPA_PLATFORM = "offscreen"` and the appropriate
`$env:PYTHONPATH` first. Optional test dependencies must be available. Tests use
fixtures and mocked integrations; native dialogs, external applications and system
installation/mount behavior need separate platform validation. Test consumers
before updating their submodule references.

## License

MIT. See [LICENSE.md](LICENSE.md). Copyright © 2020–2026 Marc-André Voyer.

## Atomic persistence

`persistence.atomic_write_bytes(path, data, validate=None, overwrite=True)` stages
bytes beside the destination, flushes them, preserves existing permissions and
validates again before publication. No encoding, extension, symlink or size policy
is imposed. `overwrite=False` uses atomic no-clobber creation.

`atomic_write_json` adds caller-selected serialization, byte limits and optional
parent-directory durability. Callers create directories with their own permission
policy and retain their own schemas. TextSnapshot, Markdown and INI save paths
continue to own their format-specific rules. `configUtils.py` is unchanged.

## Package layout and compatibility

Directory indexing now lives in `directory/`: `metadata`, `store`, `schema`,
`scan`, `reader`, `search`, `order`, `totals`, `exclusions` and `reconcile`.
Import its public API from `commonUtils.directory`; its cache remains process-wide.
Atomic publication lives in `persistence/`, with text documents in
`persistence.text` and session recovery in `persistence.session`.

The former public modules `directory_index`, `text_files` and `session_store`
remain aliases to the canonical modules. Both import paths share module state,
classes, cache instances and instrumentation. The private `_directory_*` modules
have moved and no longer exist at the package root. `configUtils.py` retains its
existing location and implementation.

Logistics uses the canonical imports. BlueHole carries a vendored directory
package with the same public alias; Ally Tools imports the shared Logistics
checkout and tests both paths. Other vendored copies must be updated separately.
