# fileUtils

Shared fileUtils API. The public import path is unchanged after moving its implementation into this package.

Import from `commonUtils.fileUtils`. Implementation and public exports live in
[`__init__.py`](__init__.py).

Public entry points: `File`, `move_file`, `has_subdirectories`, `get_split_character`, `rename_file`, `copy_file`, `make_dir`, `get_current_working_dir`, `get_user_home_dir`, `get_user_name`, `get_user_lib_dir`, `get_user_application_support`, `get_user_appdata_roaming`, `get_user_appdata_local`

[Library overview](../README.md).

## API behavior

| Entry point | Purpose |
| --- | --- |
| `move_file` | Move a file, preserving an existing destination if replacement fails. |
| `rename_file` | Renames a file on disk. |
| `copy_file` | Copy a file from source to destination. |
| `make_dir` | Creates directory at location (if it doesn't exist) |
| `get_user_home_dir` | Get the current user's home directory |

## File operations

`File(path).copy_file(destination)`, `.rename_file(destination, force=False)` and
`.move_file(destination)` return a **new plain File object** for the resulting
path. They propagate I/O errors. Assign the result when continuing with the new
location; the source object keeps its original path and cached metadata snapshot.
This avoids silently retargeting objects still referenced by browsers or callers.

Copy overwrites an existing destination as before. Rename preserves an existing
destination unless force=True. Move retains atomic replacement and cross-volume
staging. Specialized file types should be reconstructed through their registry
when format-specific state needs reloading.

The free copy_file/rename_file/move_file functions are compatibility adapters
that delegate to these methods and retain boolean outcomes. User/home/platform
helpers stay module functions; they are not properties of individual files.
