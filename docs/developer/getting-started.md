# Getting started

## Checkout and environment

Clone or vendor the repository as `commonUtils` beside your application code, or
put its parent on `PYTHONPATH`. For a consumer with a submodule, initialize that
consumer's submodules with `git submodule update --init --recursive`. Do not run
`pip install commonUtils` expecting this checkout: there is no distribution
manifest here. [Launchers](../../launchers/README.md) cover supported consumer layouts.

Create a virtual environment using your project's Python interpreter. The source
uses Python 3.10-era syntax; repository CI selects 3.12.2. Windows, macOS and Linux
are intended targets, but native integrations are operation-specific.

```sh
python -m venv .venv
# Activate .venv using your shell's activation script.
python -m pip install PySide6  # Only needed for Qt components.
```

The application owns dependency pins. Import subsystems through their documented
module paths. The root import does not initialize a GUI or install optional software.

| Capability | Additional dependency or prerequisite |
| --- | --- |
| Qt widgets and workers | PySide6 and a graphical session for interactive use; one QApplication |
| ZIP payload operations | pyzipper; metadata-only archive imports remain lazy |
| External archive extraction | patool (import name patoolib), with appropriate native extractors |
| Syntax highlighting | Optional Pygments; plain code editing does not require a lexer |
| Markdown diagrams | Optional local `mmdc` executable, invoked only on request |
| Read aloud | QtTextToSpeech plus an available native speech engine/voice |
| EXIF wrapper | piexif |
| Platform/application adapters | Their target applications or system commands; consult [integrations](../../integrations/README.md) |

This is a capability map, not an exhaustive dependency lock. Import and exercise
the modules your application actually uses. CI obtains its dependency environment
from Logistics; see [maintenance](maintenance.md).

## Work with registered file objects

```python
from pathlib import Path
from commonUtils.filesystem.directories import Directory
from commonUtils.formats.registry import file_from_path

folder = Directory(Path.cwd())
for item in folder.list_files(recursive=False, filter_extension=['txt', 'md']):
    print(item.path, type(item).__name__)

item = file_from_path(folder.path / 'notes.md')
print(type(item).__name__)  # MarkdownFile, even before the file exists.
```

`Directory` requires a `pathlib.Path`; `File` normalizes its input. Resolution
chooses a class, not a guarantee that a file exists or is valid. Register project
classes before listing. Use [extension points](extension-points.md) for that contract.

For plain paths and cancellable filename filtering, use
`filesystem.traversal.scan_directory`. It skips nested directory links; recursive
`Directory.list_files()` follows them with loop detection. Avoid substituting one
for the other without considering that difference.

## Embed a browser

The [runnable feature example](../../ui/features/README.md#runnable-example-add-a-menu-action-to-a-browser)
creates QApplication, registers a feature, installs it in a FileBrowser and defers
closing until browser workers stop. Save the example beside the `commonUtils`
checkout, install PySide6 and run it with a local folder argument.

Registration belongs before the first listing. Window/controller construction
belongs on the GUI thread. If you add controller jobs, extend close handling to
wait for their completion as well as browser workers. See
[lifecycle contracts](architecture.md#initialization-and-shutdown).

To embed Markdown, use `MarkdownViewer`; to open a retained standalone or hosted
window, use `open_markdown`. Editing is opt-in. See the
[Markdown developer guide](../../ui/markdown/README.md).

[Developer hub](README.md)
