# commonUtils

commonUtils is a collection of Python tools shared by Logistics and Blue Hole. It helps with files, configuration, archives, background tasks and
desktop interfaces, so each project can focus on its own features.

It's a library to use in your code, rather than an app you open on its own.
It supports Windows, macOS and Linux; some tools are platform-specific.

## What can it do?

- **Files and folders:** browse, search, copy, move, rename and inspect files.
- **File formats:** read and write text, CSV, JSON, INI, XML and Markdown.
- **Configuration:** safely edit INIs, validate optional typed settings and show
  them as section tabs with editable fields.
- **Archives:** create, inspect, extract and verify ZIPs, including encrypted ZIPs;
  use external tools for other supported archive formats.
- **Desktop interfaces:** add file browsers, previews, dialogs, readers and storage charts.
- **Background work:** show progress and support cancellation for long tasks.
- **Downloads and streams:** copy or hash data and verify downloaded files.
- **System tools:** run commands, work with links and open files or applications.

## Use it in your project

You'll need **Python 3.10 or newer**. Put this repository in a folder named
`commonUtils` beside your Python code, or add it there as a Git submodule. Its
parent folder must be on Python's import path. There isn't a pip-installable
package for this repository yet.

For example:

```text
my_project/
└── Python/
    ├── launch.py
    └── commonUtils/
```

A small example you can use in `launch.py`:

```python
from commonUtils.formats.jsonType import JSONFile

settings = JSONFile("settings.json")
settings.write_json({"enabled": True})
print(settings.read_json())
```

For Git submodules, run `git submodule update --init --recursive` after cloning.
See the [developer reference](#use-it-in-a-project) for import-path
setup and more examples. If you're using Logistics, its launcher handles setup.

## Dependencies

Consumers install the optional dependencies required by their chosen modules.
See [development and platform setup](#optional-dependencies-and-platforms)
and each area's README for specific requirements.

## Guides

| Looking for… | Start here |
| --- | --- |
| A file browser with your own actions and previews | [Browser features](ui/features/README.md) |
| INI settings and their editor | [Configuration guide](configuration/README.md) |
| Background work and cancellation | [Qt operations](ui/operation_progress.md), [batch operations](runtime/operations/README.md) |
| Streams and verified downloads | [Streams](runtime/streams/README.md), [downloads](runtime/streams/downloads.md) |
| Batch renaming | [Rename tools](filesystem/rename/README.md) |
| File formats and custom file types | [File types](formats/README.md) |
| Archive operations | [Archives](archives/README.md) |
| XML documents | [XML guide](formats/xmlType.md) |
| Desktop widgets and readers | [UI guide](ui/README.md) |
| External tools and processes | [Wrappers](integrations/wrappers/README.md) |
| Directory indexing | [Directory](filesystem/index/README.md) |
| Atomic publication, text and recovery | [Persistence](persistence/README.md) |
| Project bootstrap scripts | [Launchers](launchers/README.md) |
| Regression tests | [Tests](tests/README.md) |
| Module details, behavior and tests | [Developer reference](#developer-reference) |

## Package map

| Area | Responsibility |
| --- | --- |
| [filesystem](filesystem/README.md) | Files, folders, links, transfers, removal, traversal, indexing and storage |
| [formats](formats/README.md) | File types, JSON, INI, XML, Markdown and spreadsheets |
| [archives](archives/README.md) | Archive creation, reading, editing and extraction |
| [runtime](runtime/README.md) | Platform support, diagnostics, logging, operations and streams |
| [integrations](integrations/README.md) | Applications, web links, Steam and command wrappers |
| [configuration](configuration/README.md) | Schemas, settings and legacy config helpers |
| [persistence](persistence/README.md) | Atomic publication, sessions, text recovery and merging |
| [ui](ui/README.md) | Desktop widgets, file browsers, readers and feature declarations |
| [launchers](launchers/README.md) | Project bootstrap scripts |
| [tests](tests/README.md) | Shared regression tests |

Use these canonical paths for new code. Historical paths are lazy aliases defined
in `_compat.py`; they share the canonical modules, classes and state. Both
Logistics and Blue Hole use the same implementation.

## License

[MIT](LICENSE.md). Copyright © 2020–2026 Marc-André Voyer.

## Developer reference

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
from commonUtils.filesystem.directories import Directory
from commonUtils.formats.jsonType import JSONFile

# Use an existing input directory.
files = Directory(Path('data')).list_files(filter_extension='txt')
settings = JSONFile('settings.json')
settings.write_json({'enabled': True}, sort_keys=True)
print(settings.read_json())
```

Directory listing is recursive by default and resolves registered file types
without reading their contents. JSON writes stage and replace atomically;
missing/malformed reads raise exceptions for the application to handle.

## Optional dependencies and platforms

The consuming application manages dependencies. Importing a module may require
its own extras; this repository does not supply one exhaustive install command.

| Capability | Requirements |
| --- | --- |
| Qt browser, workers and PySide UI | `PySide6`; create one QApplication before widgets |
| ZIP operations | `pyzipper`; archive metadata can be imported without it |
| External archive/RAR extraction | `patool` (`patoolib` import) and format-specific system extractors |
| EXIF wrapper | `piexif` |
| Platform workflows | Relevant system tools, such as PowerShell, `hdiutil` or Flatpak |

Windows, macOS and Linux are supported at the library level; individual operations
can remain platform-specific. Route platform choices through `osUtils` and consult
the relevant module before relying on an external tool.

```python
from commonUtils.runtime.platform import get_os, get_arch, OS

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
from commonUtils.runtime.diagnostics import log, Severity

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

## Atomic persistence

`persistence.atomic_write_bytes(path, data, validate=None, overwrite=True)` stages
bytes beside the destination, flushes them, preserves existing permissions and
validates again before publication. No encoding, extension, symlink or size policy
is imposed. `overwrite=False` uses atomic no-clobber creation.

`atomic_write_json` adds caller-selected serialization, byte limits and optional
parent-directory durability. Callers create directories with their own permission
policy and retain their own schemas. TextSnapshot, Markdown and INI save paths
continue to own their format-specific rules. `configuration.legacy` retains the existing configuration behavior.

## Package layout and compatibility

Directory indexing lives in `filesystem/index/`: `metadata`, `store`, `schema`,
`scan`, `reader`, `search`, `order`, `totals`, `exclusions` and `reconcile`.
Import its public API from `commonUtils.filesystem.index`; its cache remains process-wide.
Atomic publication lives in `persistence/`, with text documents in
`persistence.text` and session recovery in `persistence.session`.

Historical public paths remain lazy aliases in `_compat.py`. Canonical and legacy
imports share module state, classes, cache instances and instrumentation, including
nested submodules. The configuration helper now lives in `configuration/legacy.py`.

Logistics uses the canonical imports and pins this repository as a Git submodule.
Blue Hole vendors the same implementation as a subtree and uses canonical imports
under its own package namespace. See [layout decisions](_compat.md) for the
area boundaries and reconciliation checks.
