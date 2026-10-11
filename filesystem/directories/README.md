# Folders and file objects

Use `Directory` when you want file objects resolved through commonUtils' format
registry. Listing does not read file contents.

```python
from pathlib import Path
from commonUtils.filesystem.directories import Directory

folder = Directory(Path('/data/project'))
for file in folder.list_files(recursive=False, filter_extension=['txt', 'md']):
    print(file.path, file.file_name)
```

Use [traversal](../README.md) for plain paths, filename masks and cancellation.
The [format guide](../../formats/README.md) explains custom file types.
