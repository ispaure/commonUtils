# File Types

The `commonUtils.fileTypes` package contains specialized `File` subclasses for common file formats. Each type extends the base `File` abstraction from `fileUtils.py` with format-specific behavior while retaining the standard file information and operations provided by `File`.

## Available File Types

| Class | Module | Purpose |
| --- | --- | --- |
| `TXTFile` | `txtType.py` | Read, write, and open text files |
| `CSVFile` | `csvType.py` | Read and write CSV data |
| `JSONFile` | `jsonType.py` | Parse JSON and write it atomically |
| `XMLFile` | `xmlType.py` | XML file representation built on `TXTFile` |
| `ZIPFile` | `zipType.py` | ZIP extraction and root-entry inspection |
| `DMGFile` | `dmgType.py` | Mount and extract directories from macOS DMG files |
| `AppImageFile` | `appimageType.py` | AppImage file representation |

## Modules

### 📄 `txtType.py`

Provides `TXTFile`, a text-file abstraction that stores file contents as a list of lines.

```python
from pathlib import Path
from commonUtils.fileTypes.txtType import TXTFile

file = TXTFile(Path("example.txt"))
file.line_lst = ["First line", "Second line"]
file.write_lines()

lines = file.read_lines()
```

`TXTFile` can also open a file in the platform's default text editor on Windows, macOS, and Linux.

### 📄 `csvType.py`

Provides `CSVFile` for reading and writing standard CSV data.

CSV contents are represented as a list of rows, with each row containing a list of string values.

```python
from pathlib import Path
from commonUtils.fileTypes.csvType import CSVFile

file = CSVFile(Path("example.csv"))

file.write_csv([
    ["Name", "Value"],
    ["Example", "123"]
])

data = file.read_csv()
```

Files are read using UTF-8 with BOM support and written using standard Python CSV formatting.

### 📄 `jsonType.py`

`JSONFile` extends `File` directly, because JSON is structured data rather than
an editable list of text lines. `read_json()` accepts UTF-8 with optional BOM and
returns any JSON value. Missing and malformed files raise standard Python errors
so applications can decide how to recover.

```python
from commonUtils.fileTypes.jsonType import JSONFile

file = JSONFile("settings.json")
file.write_json({"enabled": True, "names": ["Été"]}, compact=True, sort_keys=True)
settings = file.read_json()
```

Writes serialize before touching the destination, create parent directories,
stage UTF-8 text next to the target, flush it, and replace atomically. Existing
permissions are preserved; temporary files are cleaned up on failure. Non-finite
numbers are rejected. Formatting is indented by default; `compact=True` removes
extra whitespace. `ensure_ascii` and `sort_keys` are optional serialization settings.

### 📄 `xmlType.py`

Provides `XMLFile`, which currently extends `TXTFile`.

This gives XML files the standard text-file functionality such as line-based reading and writing while providing a distinct file type for XML-specific use.

### 📄 `zipType.py`

Provides `ZIPFile` for ZIP archive operations.

```python
from pathlib import Path
from commonUtils.fileTypes.zipType import ZIPFile

archive = ZIPFile(Path("archive.zip"))

archive.extract(Path("output"))
root_files = archive.get_root_file_lst()
```

`extract()` uses the shared archive extraction functionality in `zipUtils.py` and optionally supports progress display.

`get_root_file_lst()` returns files located directly at the root of the ZIP archive.

### 📄 `dmgType.py`

Provides `DMGFile` for macOS disk images.

`extract_directory_from_dmg()` mounts a DMG using `hdiutil`, locates a requested directory inside the mounted image, copies it to an output location, and then unmounts the image.

This operation is macOS-specific.

### 📄 `appimageType.py`

Provides `AppImageFile`, a distinct `File` subclass representing Linux AppImage files.

It currently inherits the standard `File` functionality without adding additional operations, allowing AppImages to be represented as their own file type for application and platform-specific workflows.

## Base File Functionality

All file types ultimately inherit from `fileUtils.File`, giving them access to the common file abstraction and operations provided by `commonUtils`.

For example:

```python
file.path
file.file_name
file.ext
file.size
file.delete_file()
file.make_writable()
```

Individual file types add only the behavior specific to their format.

## File Type Resolution

`Directory.list_files()` resolves files through a **process-wide registry**. Built-in
TXT, CSV, JSON, XML, ZIP, DMG and AppImage modules register their own classes lazily.
Unknown formats remain `File`. Existing directory ordering, recursive traversal and
extension filters are unchanged; listing does not read file contents.

Projects own domain-specific types and can register them without changing commonUtils:

```python
from commonUtils.fileUtils import File
from commonUtils.fileTypes.registry import register_file_type, file_from_path

class ProjectArchive(File):
    pass

register_file_type(ProjectArchive, '.myarchive')
file = file_from_path('example.myarchive')
```

Registration is global within the current Python process. Every subsequent
`Directory.list_files()` call and `file_from_path()` call uses it, including calls
from other project modules and Directory objects created before registration.
Already-created File objects keep their class. Separate processes must register
independently. Direct `File(path)` construction intentionally remains generic.

**Startup guideline:** register built-ins and project-specific types during project
initialization, before the first commonUtils directory listing, resolution or browser
use. This is recommended, not enforced; late registration affects subsequent
resolutions too. Importing commonUtils before registration is fine.

`register_file_type(MyFile, ('foo', 'bar'), detector=rule, priority=10)` supports
case-insensitive extensions, compound suffixes and optional `rule(Path) -> bool`.
An extension plus detector requires both to match; a detector alone can recognize
extensionless files. Higher priority wins, with the most recent registration
breaking ties. Built-ins use priority -100 so project registrations normally win.
Identical registrations are idempotent. Detector failures propagate, allowing
callers to decide how to handle them. Keep detectors cheap and read-only because
they run during listing. `file_types.unregister(registration)` removes a rule;
`FileTypeRegistry` also supports isolated registries for specialized callers/tests.
