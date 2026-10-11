# Archive convenience functions

Convenience functions for compression and extraction. Import this module through
`commonUtils.archives.legacy`; general archive operations also live in `commonUtils.archives`.

Import from `commonUtils.archives.legacy`. Implementation and public exports live in
[`__init__.py`](__init__.py).

Public entry points: `unzip_file`, `unrar_file`, `zip_file`

[Library overview](../../README.md).

## API behavior

| Entry point | Purpose |
| --- | --- |
| `unzip_file` | Validated streaming extraction for plain/AES ZIPs. |
| `unrar_file` | Extracts rar file to desired location. |
| `zip_file` | Create a zip file from the source to the destination. |
