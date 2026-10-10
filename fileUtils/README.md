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
