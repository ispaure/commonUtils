# External integrations

Adapters for command execution, PowerShell, EXIF and SQLite. Dependencies remain local to each wrapper; import the integration you need.

[Command execution](cmdShellWrapper/README.md) owns structured outcomes, cancellation and timeouts.

## Files

| File | Responsibility / public entry points |
| --- | --- |
| [.DS_Store](.DS_Store) | Platform launcher. |
| [__init__.py](__init__.py) | Package exports and imports. |
| [piexifWrapper.py](piexifWrapper.py) | `jpg_batch_set_exif_comments`, `jpg_set_exif_comments` |
| [powerShellWrapper.py](powerShellWrapper.py) | `exec_powershell` |
| [sqlWrapper.py](sqlWrapper.py) | `exec_sql_command`, `fetch_sql_table` |

[Parent guide](../README.md)

[Perforce](perforce/README.md) provides the shared file/group/workspace models.
