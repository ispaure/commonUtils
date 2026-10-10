# zipUtils

Shared zipUtils API. The public import path is unchanged after moving its implementation into this package.

Import from `commonUtils.zipUtils`. Implementation and public exports live in
[`__init__.py`](__init__.py).

Public entry points: `unzip_file`, `unrar_file`, `zip_file`

[Library overview](../README.md).

## API behavior

| Entry point | Purpose |
| --- | --- |
| `unzip_file` | Compatibility wrapper: validated streaming extraction for plain/AES ZIPs. |
| `unrar_file` | Extracts rar file to desired location. |
| `zip_file` | Create a zip file from the source to the destination. |
