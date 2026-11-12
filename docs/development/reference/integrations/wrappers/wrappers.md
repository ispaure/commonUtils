# External integrations

Adapters for command execution, PowerShell, EXIF and SQLite. Dependencies remain local to each wrapper; import the integration you need.

[Command execution](cmdShellWrapper/cmdShellWrapper.md) owns structured outcomes, cancellation and timeouts.

New database callers use the [SQLite API](../sqlite.md), which opens read-only by
default, bounds pages and provides explicit atomic edit transactions. The legacy
SQL wrapper remains a trusted-caller compatibility helper with whole-result
reads; its raw command path commits successful statements. Do not route browser
queries or untrusted SQL through that helper.

## Files

| File | Responsibility / public entry points |
| --- | --- |
| [__init__.py](../../../../../integrations/wrappers/__init__.py) | Package exports and imports. |
| [piexifWrapper.py](../../../../../integrations/wrappers/piexifWrapper.py) | `jpg_batch_set_exif_comments`, `jpg_set_exif_comments` |
| [powerShellWrapper.py](../../../../../integrations/wrappers/powerShellWrapper.py) | `exec_powershell` |
| [sqlWrapper.py](../../../../../integrations/wrappers/sqlWrapper.py) | `exec_sql_command`, `fetch_sql_table` |

[Parent guide](../../../overview.md)

[Perforce](perforce/perforce.md) provides the shared file/group/workspace models.
