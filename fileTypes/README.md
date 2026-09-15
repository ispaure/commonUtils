# File Types

The `commonUtils.fileTypes` package contains specialized `File` subclasses for common file formats. Each type extends the base `File` abstraction from `fileUtils.py` with format-specific behavior while retaining the standard file information and operations provided by `File`.

## Available File Types

| Class | Module | Purpose |
| --- | --- | --- |
| `TXTFile` | `txtType.py` | Read, write, and open text files |
| `CSVFile` | `csvType.py` | Read and write CSV data |
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
file.name
file.ext
file.size
file.delete_file()
file.make_writable()
```

Individual file types add only the behavior specific to their format.

## File Type Resolution

`Directory.list_files()` currently automatically resolves TXT and CSV files to `TXTFile` and `CSVFile` instances.

Other specialized file types can currently be instantiated directly when needed.
