# Project launchers

When uv is missing, the launchers install uv 0.13.4 from versioned official installers. Existing working uv installations are reused.

Platform launch scripts bootstrap the consuming Python project. Projects select and configure a launcher; this folder does not install a global commonUtils package.

macOS `.command`, Linux `.sh` and Windows `.bat` scripts share the launcher contract. See [project setup](#use-it-in-a-project).

Windows batch scripts must retain CRLF line endings: `cmd.exe` can fail to resolve
`CALL :label` subroutines in LF-only files. Git attributes enforce this on checkout;
consumers packaging source archives must also preserve CRLF in their shipped files.

## Files

| File | Responsibility / public entry points |
| --- | --- |
| [LaunchPythonProject_LINUX_UV.sh](../../../../launchers/LaunchPythonProject_LINUX_UV.sh) | Platform launcher. |
| [LaunchPythonProject_MAC.command](../../../../launchers/LaunchPythonProject_MAC.command) | Platform launcher. |
| [LaunchPythonProject_WIN.bat](../../../../launchers/LaunchPythonProject_WIN.bat) | Platform launcher. |

[Parent guide](../../overview.md)

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

## Application arguments

The first three shared-launcher arguments are the project root, config file and
pause flag. Additional arguments are forwarded to the Python launch file. Root
wrappers must pass their argument list as separate arguments (`"$@"` on Bash,
`%*` on Windows). Launch-file exit codes are returned to the caller.

## Optional environment synchronization wrapper

A project that needs an atomic guard around dependency synchronization may set a
project-relative Python script in either launch configuration layer:

```ini
[Launch]
environment_sync_wrapper = tooling_bootstrap/sync.py
```

An absent or explicitly empty value keeps the original direct `uv sync` behavior.
Configured scripts must exist and be readable; absolute paths and parent traversal
are rejected before synchronization or environment creation. Remove the setting
or restore the script if this validation fails.

After the normal Python availability check, the launcher uses the project's own
`.venv/bin/python` (Windows: `.venv\Scripts\python.exe`) to invoke the script:

```text
PYTHON WRAPPER sync --project-root PROJECT_ROOT --venv VENV_ROOT -- UV sync FLAGS
```

Each value is a separate literal argument. `UV` is the resolved uv executable, and
`FLAGS` preserves the launcher's existing options: `--locked --no-python-downloads`
on macOS, with `--no-dev` additionally on Linux and Windows. The working directory
is the configured source directory. The wrapper must execute the argv after `--`
as an argument list, preserve its exit status, and return before application launch.
The launcher stops on any nonzero wrapper exit and returns that status.
Windows passes the project-root directory with a terminal `\.` component so a
trailing separator from a top-level BAT wrapper cannot escape the closing quote
when Python parses its command line. The wrapper resolves it to the same directory.
Native consumer coverage must invoke the top-level wrapper, as well as the shared
launcher directly; the two paths supply different root argument spellings.

On first launch, an absent or empty environment is initialized with
`uv venv --no-python-downloads VENV_ROOT` from the source directory, honoring the
same Python selection and `.python-version` as normal synchronization. This creates
only the interpreter environment; the wrapper must use the standard library until
it runs dependency synchronization. A nonempty environment missing its interpreter
is preserved and rejected; repair that environment explicitly rather than expecting
the launcher to clear it.

The consuming project owns the wrapper's guard, any explicitly enrolled restore
steps, and their failure policy. A project not enrolled in those steps should still
run the original uv argv. The shared launchers do not select or install project SDKs.
