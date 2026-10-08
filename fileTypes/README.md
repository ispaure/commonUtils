# File Types

The `commonUtils.fileTypes` package contains specialized `File` subclasses for common file formats. Each type extends the base `File` abstraction from `fileUtils.py` with format-specific behavior while retaining the standard file information and operations provided by `File`.

## Available File Types

| Class | Module | Purpose |
| --- | --- | --- |
| `TXTFile` | `txtType.py` | Read, write, and open text files |
| `CSVFile` | `csvType.py` | Read and write CSV data |
| `JSONFile` | `jsonType.py` | Parse JSON and write it atomically |
| `MarkdownFile` | `markdownType.py` | Text-file operations and activation in the shared Markdown reader |
| `XMLFile` | `xmlType.py` | DOM queries, namespace-aware editing and atomic saving, plus inherited line operations |
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

`XMLFile` retains inherited TXT line operations and also provides a separate DOM
API for structured editing. Do not mix DOM and `line_lst` edits expecting them to
synchronize automatically.

```python
from commonUtils.fileTypes.xmlType import XMLFile

original = b'<Project><!--keep--><Title>Old</Title><Extension flag="x"/></Project>'
document = XMLFile.from_bytes(original)
assert document.to_bytes() == original  # No-op output retains the original bytes.
assert document.get_text('Title') == 'Old'
document.set_text('Title', 'New')
updated = document.to_bytes()           # Returns bytes; does not write a file.
assert b'<!--keep-->' in updated
```

`XMLFile(path).read_xml()` loads the file and returns `xml_root`;
`from_bytes()` creates an in-memory document. `get_text`/`set_text` address direct
children in the root namespace. Missing fields read as empty text; setting empty
text removes the field. Duplicate matching children and nested element content
raise errors rather than selecting an ambiguous value. Unknown extensions,
comments, processing instructions and namespace declarations survive other edits.

`to_bytes()` validates serialization and returns bytes; `write_xml(path=None)`
adds atomic file saving. Nested/repeated elements, namespace-aware attributes and
explicit element creation/removal use the methods in the [XML guide](../XML.md).
Attribute whitespace survives round-trips. Structured edits can change formatting;
unchanged serialization returns the original bytes. Inherited `read_lines()` and
`write_lines()` continue to operate independently.

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

## Usage examples and UI integration

[Workflow recipes](../RECIPES.md#read-and-write-application-data) show text, CSV and
JSON together, including their different write guarantees. The
[feature guide](../FEATURES.md#runnable-example-add-a-menu-action-to-a-browser)
starts with a runnable browser and then adds a custom type, panel and activation.
File-format classes should remain independent of application configuration and UI
windows; browser panel loaders may read metadata asynchronously.

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
TXT, CSV, JSON, XML, Markdown, ZIP, DMG and AppImage modules register their own classes lazily.
Unknown formats remain `File`. Existing directory ordering, recursive traversal and
extension filters are unchanged; listing does not read file contents.

For new feature integrations, [Adding a feature](../FEATURES.md) uses one
`Feature(file_types=[FileType(...)], browser=BrowserExtension(...))` declaration for
types and browser capabilities. The direct registration API below remains supported.

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


### Owned, toggleable registrations

Plugin hosts may pass `owner='feature_name'` to `register_file_type` or register
inside `file_types.owner_scope('feature_name')`. `file_types.set_owner_enabled(owner,
False)` removes that owner's rules from resolution without altering other owners or
built-in fallbacks. `True` restores them with their original precedence. Changes
increment `revision`, letting browser models re-resolve cached objects. Registering
new owned rules while disabled does not activate them. The ledger remains intact;
`unregister(handle)` still permanently removes an individual rule. Scope ownership
is restored after exceptions and is local to the calling context. Existing File
instances and running operations are retained; future resolutions use the new state.

`ZIPFile` supports explicit-password reading/extraction and encryption detection;
see [ZIP archive APIs](../ZIP_ARCHIVES.md). Configuration and prompts belong to the
host application rather than the file-type registry.


### Markdown activation

`file_from_path()` resolves `.md` and `.markdown` (case-insensitively) as
`MarkdownFile`, a `TXTFile` subclass. Double-click activation in FileBrowser opens
the shared [Markdown reader](../ui/README.md#markdown-reader). Resolution and text
operations do not import Qt; only activation requires an existing QApplication.
Feature-installed activation handlers still take precedence over the file's hook.
