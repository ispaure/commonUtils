# Files

Import from `commonUtils.filesystem.files`. Implementation and public exports live in
[`__init__.py`](../../../../../filesystem/files/__init__.py).

Public entry points: `File`, `has_subdirectories`, `get_split_character`, `get_current_working_dir`, `get_user_home_dir`, `get_user_name`, `get_user_lib_dir`, `get_user_application_support`, `get_user_appdata_roaming`, `get_user_appdata_local`

[Library overview](../../../overview.md).

## API behavior

| Entry point | Purpose |
| --- | --- |
| `File.move_file` | Move a file, preserving an existing destination if replacement fails. |
| `File.rename_file` | Renames a file on disk. |
| `File.copy_file` | Copy a file from source to destination. |
| `Path.mkdir` / `Directory.make_dir` | Create a directory. |
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

The module-level `copy_file`, `rename_file`, `move_file` and `make_dir`
functions have been removed. Use the instance methods above and catch `OSError`
where a workflow needs a boolean failure result. For directory creation, use
`Path(path).mkdir(parents=True, exist_ok=True)` or `Directory(path).make_dir()`.
User/home/platform helpers remain module functions.

Local file operations do not eagerly import pwd or shell wrappers. iOS/Android
use POSIX separators and native chmod for `make_writable`; actual filesystem
permission failures propagate. Shell-based executable permissions and external
editor/application launching remain desktop adapters. See the
[mobile foundation](../../../mobile-foundation.md).
