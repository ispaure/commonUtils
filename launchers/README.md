# Project launchers

Platform launch scripts bootstrap the consuming Python project. Projects select and configure a launcher; this folder does not install a global commonUtils package.

macOS `.command`, Linux `.sh` and Windows `.bat` scripts share the launcher contract. See [project setup](#use-it-in-a-project).

## Files

| File | Responsibility / public entry points |
| --- | --- |
| [LaunchPythonProject_LINUX_UV.sh](LaunchPythonProject_LINUX_UV.sh) | Platform launcher. |
| [LaunchPythonProject_MAC.command](LaunchPythonProject_MAC.command) | Platform launcher. |
| [LaunchPythonProject_WIN.bat](LaunchPythonProject_WIN.bat) | Platform launcher. |

[Parent guide](../README.md)

## Use it in a project

Python **3.10+** is required. The repository itself is the `commonUtils` package;
there is currently no `pyproject.toml` or `setup.py` for installing it as a wheel.
Place it beneath a directory on your Python import path, often as a Git submodule:

```text
my_project/
└── Python/                 # Add this directory to PYTHONPATH.
    ├── launch.py
    └── commonUtils/
```

```sh
# Run from my_project (macOS / Linux).
PYTHONPATH=Python python Python/launch.py
```

On PowerShell, set `$env:PYTHONPATH = "Python"` before running your interpreter.
For submodule checkouts, initialize with `git submodule update --init --recursive`.

Import only the tools you need:

```python
from pathlib import Path
from commonUtils.filesystem.directories import Directory
from commonUtils.formats.jsonType import JSONFile

# Use an existing input directory.
files = Directory(Path('data')).list_files(filter_extension='txt')
settings = JSONFile('settings.json')
settings.write_json({'enabled': True}, sort_keys=True)
print(settings.read_json())
```

Directory listing is recursive by default and resolves registered file types
without reading their contents. JSON writes stage and replace atomically;
missing/malformed reads raise exceptions for the application to handle.

## Optional personal launch overrides

Hosts may export `COMMONUTILS_PERSONAL_CONFIG_FILE` with a private INI path before
invoking a shared launcher. `[Launch]` keys in that file override matching software
keys; absent keys inherit. Explicit empty values remain empty. Missing personal
files are ignored. Duplicate entries for a requested launch key within either layer are rejected.
Unix and native Windows readers use the same layered contract. Hosts own the
personal path and expose editable defaults and overrides in their settings UI.
