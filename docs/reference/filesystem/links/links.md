# Symbolic links and junctions

Import from `commonUtils.filesystem.links`. Implementation and public exports live in
[`__init__.py`](../../../../filesystem/links/__init__.py).

Public entry points: `is_junction`, `delete_symbolic_link`, `create_symbolic_link`, `update_symbolic_link`

[Library overview](../../../overview.md).

## API behavior

| Entry point | Purpose |
| --- | --- |
| `is_junction` | Returns whether a path is a Windows junction. |
| `delete_symbolic_link` | Deletes a symbolic link without deleting the target it points to. |
| `create_symbolic_link` | Creates a symbolic link at destination pointing to source. |
| `update_symbolic_link` | Creates or updates a symbolic link at destination pointing to source. |

## Exclusive creation for interactive tools

`creation.create_link(source, destination, kind='symbolic')` returns the new Path
or raises an ordinary filesystem/value error. Source must be an existing regular
file or directory; destination parent must exist. Existing files, directories and
broken links are never replaced. Symbolic links use absolute resolved targets and
support files/folders. Hard links require a file on the same filesystem/volume.
Windows-only junctions require local folders; UNC/mapped-network paths are refused.
Junction creation runs Windows PowerShell New-Item with encoded, quoted literals,
without automatic elevation or replacement. Windows symbolic links report missing
privileges with guidance about Developer Mode. Filesystem permissions still apply.

`creation.create_link_in_directory(source, directory, kind='symbolic')` keeps the
source name when available; collisions use ` - Link` then ` - Link (N)` before a
file extension. Allocation uses exclusive creation and leaves existing resources
untouched. These APIs are also exported by `filesystem.links`; the older symbolic
link APIs retain their diagnostic/parent-creation behavior.
