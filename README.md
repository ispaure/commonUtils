<div align="center">

# commonUtils

**A cross-platform Python helper library for reusable tools and workflows.**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)

</div>

---

`commonUtils` is a cross-platform Python helper library maintained by
Marc-André Voyer. It collects reusable functionality shared across tools
and projects, with a focus on filesystem operations, application/process
launching, platform abstraction, command execution, lightweight UI,
configuration files, archives, and common file types.

The library is designed primarily as a shared dependency for other
Python tools rather than as a standalone application.

## Requirements

-   **Python 3.10+**
-   Windows, macOS, or Linux

Python 3.10 is the minimum supported version because the codebase uses
structural pattern matching (`match` / `case`) and modern type
annotation syntax.

Some modules have additional dependencies:

-   `PySide6` --- optional PySide UI backend
-   `pyzipper` --- encrypted ZIP support
-   `patool` / `patoolib` --- archive extraction support, including RAR
    workflows

Platform-specific functionality may also depend on software provided by
the operating system, such as PowerShell on Windows or `hdiutil` on
macOS.

## Extending applications

[Adding a feature](FEATURES.md) is the recommended entry point for declaring owned
file types, browser actions, activation, folder fields and per-window controllers
in one place. It includes installation and live enable/disable examples.

## Core Modules

### 📄 `fileUtils.py`

Provides the base `File` abstraction and general file/path helpers.

`File` stores commonly needed information such as the path, filename,
extension, name without extension, and file size. It also provides
operations such as safe deletion, making files writable, and setting
executable permissions.

General helpers include file copying, moving and renaming, as well as
common user and application-data paths.

``` python
from pathlib import Path
from commonUtils.fileUtils import File

file = File(Path("/path/to/file.txt"))
print(file.name)
print(file.ext)
```

### 📄 `dirUtils.py`

Provides the `Directory` abstraction for directory traversal, creation,
opening, and deletion.

`Directory.list_files()` is recursive by default and can filter by
extension. Directory traversal follows symbolic links and junctions that
resolve to directories while detecting recursive directory-link loops.

``` python
from pathlib import Path
from commonUtils.dirUtils import Directory

directory = Directory(Path("/path/to/data"))

files = directory.list_files()
txt_files = directory.list_files(filter_extension="txt")
subdirectories = directory.list_directories()
```

Destructive directory operations deliberately distinguish between real
directories and links. Deleting a `Directory` that represents a symbolic
link or Windows junction removes the link itself rather than deleting
the target directory.

### 📁 `fileTypes`

Contains specialized `File` subclasses for formats that require
additional behavior.

Current types include:

| Class | Module | Purpose |
| --- | --- | --- |
| `TXTFile` | `txtType` | Read/write text as lines and open it in the default editor |
| `CSVFile` | `csvType` | Read/write CSV data using Python's CSV handling |
| `JSONFile` | `jsonType` | JSON documents with atomic UTF-8 writes |
| `XMLFile` | `xmlType` | XML-oriented text file type |
| `ZIPFile` | `zipType` | Plain/encrypted ZIP access, validated extraction and root-entry inspection |
| `DMGFile` | `dmgType` | macOS DMG mounting and directory extraction |
| `AppImageFile` | `appimageType` | AppImage file representation |


Example:

``` python
from pathlib import Path
from commonUtils.fileTypes.txtType import TXTFile

file = TXTFile(Path("notes.txt"))
file.line_lst = ["First line", "Second line"]
file.write_lines()
```

`Directory.list_files()` uses the process-wide file-type registry, with built-in
TXT, CSV, JSON, XML, ZIP, DMG and AppImage rules. Applications add owned extension
or detector rules through `Feature.file_types`; disabling a feature disables its
rules. Existing objects keep their class; browser refreshes resolve against the
current registry. See [feature declarations](FEATURES.md).

### 📄 `linkUtils.py`

Provides symbolic-link management and Windows junction detection.

The module can create, delete, and update symbolic links while
protecting link targets during destructive operations.

``` python
from pathlib import Path
from commonUtils import linkUtils

linkUtils.update_symbolic_link(
    Path("/path/to/source"),
    Path("/path/to/link")
)
```

`update_symbolic_link()` refuses to replace a real destination object
unless `allow_destination_deletion=True` is explicitly provided.

Windows junction detection supports the library's Python 3.10+ target.
Python versions that provide `Path.is_junction()` use the native
implementation; older supported Python versions use a Windows
reparse-tag fallback.

### 📄 `osUtils.py`

Provides normalized operating-system and architecture detection.

Supported operating systems:

-   `OS.WIN`
-   `OS.MAC`
-   `OS.LINUX`

Supported architecture categories include x86/x86-64 and ARM/ARM64.

``` python
from commonUtils.osUtils import get_os, get_arch, OS

if get_os() == OS.WIN:
    print("Running on Windows")

print(get_arch())
```

`get_os_path()` can also select a platform-specific value from Windows,
macOS, and Linux alternatives.

### 📄 `debugUtils.py`

Provides the primary structured debug logger.

Available severities are:

-   `Severity.DEBUG`
-   `Severity.INFO`
-   `Severity.WARNING`
-   `Severity.ERROR`
-   `Severity.CRITICAL`

``` python
from commonUtils.debugUtils import log, Severity

log(Severity.INFO, "Example", "Operation completed")
```

Logging supports optional timestamps, elapsed-time display, verbose
debug filtering, project prefixes, log-file output, ANSI console
coloring, and popup messages.

**Important:** `Severity.CRITICAL` is terminal by design. A critical log
displays the error and raises `DebugException`, halting the current
operation unless explicitly handled by the caller.

### 📄 `appUtils.py`

Provides abstractions and helpers for launching applications across
Windows, macOS, and Linux.

The module includes:

-   `DiskApp` for applications stored on disk
-   `StoreApp` for Windows Store applications
-   `Flatpak` for Flatpak applications
-   `AppImage` for Linux AppImages
-   executable validation and permission helpers

`DiskApp` supports normal launches, detached launches, and visible
console/terminal launches depending on the platform.

### 📁 `wrappers/cmdShellWrapper`

Cross-platform command execution used by higher-level utilities.

``` python
from commonUtils.wrappers import cmdShellWrapper

output = cmdShellWrapper.exec_cmd(
    "python --version",
    wait_for_output=True
)
```

The wrapper supports:

-   captured command output
-   commands launched without waiting
-   configurable working directories
-   idle-output timeouts
-   process-tree termination
-   new terminal windows
-   Windows, macOS, and Linux terminal behavior

The `time_out` argument is an **idle-output timeout**, not a maximum
command runtime. A command may continue running as long as it continues
producing output.

### 📄 `wrappers/powerShellWrapper.py`

Provides PowerShell command execution for Windows-specific workflows.

### 📁 `ui`

Provides generic UI functions with lazy backend selection.

``` python
from commonUtils import ui

ui.display_msg_box_ok("commonUtils", "Operation completed")
```

When enabled, the generic UI first attempts to use the PySide backend.
If PySide is unavailable or the operation fails, it falls back to the
native platform backend.

The backends are also available explicitly as:

``` python
ui.native
ui.pyside
```

Lazy loading keeps optional PySide dependencies from being imported
unless needed.

### 📁 `ui/file_browser`

The reusable `FileBrowser` widget supplies filesystem navigation, file information,
previews, selection actions and background work. File types provide format-specific
panels/thumbnails; feature declarations add labeled menu sections, activation,
folder fields and optional controllers. `register() -> Feature(...)` is the unified
entry point, documented with examples in [FEATURES.md](FEATURES.md).

Applications install each declaration into their browser windows. A feature-wide
toggle updates owned type rules and all live bindings; a binding-only toggle affects
one window. Controllers and operation state belong to individual windows. The host
owns feature discovery, dependency policy and application UI. Expensive handlers
must explicitly use workers; action declarations are not automatically asynchronous.

### 📄 `configUtils.py`

Provides helpers for reading and modifying INI-style configuration files
using `configparser`, including section mapping and variable/section
modification.

### 📄 `spreadsheetUtils.py`

Provides lightweight `Spreadsheet`, `Row`, and `Cell` abstractions
backed by `CSVFile` for import and export.

### 📄 `zipUtils.py`

Compatibility ZIP helpers delegate to `zip_access`; RAR extraction retains its
external extractor integration.

### 📄 `zip_access.py`

Reads ordinary ZIP, legacy ZipCrypto and WinZip AES; password-protected writes
always use AES-256. Validated streaming extraction uses the same entry layout for
plain and encrypted archives, rejecting traversal, symlinks and ambiguous names.
`create_archive` deduplicates selections, retains selected folder roots and empty
directories, verifies decrypted content and publishes a separate ZIP without
replacing sources or an existing destination.

```python
from commonUtils.zip_access import open_archive, extract_archive, create_archive

with open_archive("comic.cbz", password=password) as archive:
    metadata = archive.read("ComicInfo.xml")
extract_archive("comic.cbz", workspace, password=password)
create_archive([folder, other_file], "selection.zip", password=password)
```

These primitives accept explicit passwords; configuration lookup, password dialogs,
session caches, batch progress and cancellation policy belong to consuming
applications. ZIP filenames remain visible. Extraction is staged per file rather
than transactional for the whole archive; use disposable workspaces for rewrites.
See [ZIP_ARCHIVES.md](ZIP_ARCHIVES.md) for verification, authentication and failure
semantics, plus the `ZIPFile` wrappers.

### Other Utilities

📄 `webUtils.py` contains URL-opening helpers.

📄 `steamUtils.py` contains Steam-specific environment detection.

📄 `marcUtils.py` contains maintainer-specific helpers and is not intended to
represent general-purpose cross-platform functionality.

## Filesystem Safety

Filesystem helpers intentionally take a conservative approach to
destructive operations.

A symbolic link or Windows junction is treated as a filesystem object
separate from the directory it targets. Operations that remove links are
designed to remove the link without recursively deleting the target.

For `Directory.delete_contents()`, a linked root directory is refused by
default. Following the root link for content deletion requires
explicitly passing:

``` python
directory.delete_contents(follow_root_link=True)
```

Similarly, symbolic-link replacement refuses to delete an existing real
destination unless explicitly authorized:

``` python
linkUtils.update_symbolic_link(
    source,
    destination,
    allow_destination_deletion=True
)
```

These options should only be enabled when deleting the existing
destination or operating on the resolved target is intentional.

## Cross-Platform Design

Platform-specific behavior should generally be routed through `osUtils`
rather than being duplicated by consuming projects.

The library currently contains implementations for Windows, macOS, and
Linux, although individual operations may remain platform-specific.
Examples include Windows Store applications, PowerShell, macOS DMG
handling, Linux AppImages, and Flatpak applications.

## Using commonUtils in Another Project

The repository currently contains the Python package directly and does
not include packaging metadata such as `pyproject.toml` or `setup.py`.

Make the parent directory of `commonUtils` available on `PYTHONPATH` or
otherwise include the package in the consuming project's Python
environment, then import the required modules normally:

``` python
from commonUtils import fileUtils, dirUtils, linkUtils
from commonUtils.osUtils import get_os, OS
from commonUtils.debugUtils import log, Severity
```

Keep project-specific behavior in the consuming project when possible.
`commonUtils` should contain functionality that is reusable across
multiple tools or projects.

## Development Guidelines

The codebase is used as a shared dependency, so changes to established
public functions, argument names, module names, and behavior should be
made carefully to avoid breaking consuming projects.

Prefer:

-   reusable functionality over project-specific behavior
-   `pathlib.Path` for filesystem paths
-   `osUtils` for platform branching
-   `debugUtils.log()` for structured diagnostics
-   `File` and `Directory` abstractions for filesystem operations
-   `linkUtils` for symbolic links and junction handling
-   specialized classes under `fileTypes` for format-specific file
    behavior

Destructive filesystem operations should remain explicit and
conservative, especially when symbolic links or junctions are involved.

## License

This project is licensed under the MIT License. See `LICENSE.md` for the
full license text.

Copyright © 2020-2026 Marc-André Voyer.

## Verified software downloads

`downloads.DownloadSpec` accepts a project's pinned name/version, HTTPS URL,
download SHA-256, installed-file SHA-256, optional exact ZIP member, and executable
flag. `downloads.provision` stages beside the destination, verifies both hashes,
and atomically promotes one file. Errors and cancellation retain the existing file;
ZIP entries other than the named member are never extracted. `is_ready` checks the
installed hash. Projects own URLs, platform selection and installation paths.

`ui.download.ensure_download` adds a confirmation prompt and cancellable background
progress dialog. It returns a verified path or `None` on decline/cancel/failure.
`install=True` also confirms opening an already-downloaded installer; the caller
owns launching it and any privileged installation flow.
