# Getting started with commonUtils

This guide shows how to import the library and use file objects without starting
a GUI or touching your documents. You need basic Python knowledge and an existing
consumer checkout or a standalone checkout named `commonUtils`.

## Checkout and environment

Clone or vendor the repository as `commonUtils` beside your application code, or
put its parent on `PYTHONPATH`. For a consumer with a submodule, initialize that
consumer's submodules with `git submodule update --init --recursive`. Do not run
`pip install commonUtils` expecting this checkout: there is no distribution
manifest here. [Launchers](reference/launchers/launchers.md) cover supported consumer layouts.

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
| Platform/application adapters | Their target applications or system commands; consult [integrations](reference/integrations/integrations.md) |

This is a capability map, not an exhaustive dependency lock. Import and exercise
the modules your application actually uses. CI obtains its dependency environment
from Logistics; see [maintenance](maintenance.md).

## Check the import path

In Logistics and Build Deployment Manager, `Python/` is a source root. The package
is named `commonUtils`, not `Python.commonUtils`. Put the directory **containing**
`commonUtils` on the import path, not the package directory itself. The consumers'
launchers and test helpers already establish their supported paths.

For a standalone checkout, save the example below in a script beside the
`commonUtils` directory. Run it with the interpreter from the environment you
created above. For an existing consumer, use its configured interpreter and import
path rather than installing another copy. Diagnose `ModuleNotFoundError` by
checking `import commonUtils; print(commonUtils.__file__)`; do not search for a
sibling checkout or install an unrelated package of the same name.

## Work with registered file objects

This complete example creates its own temporary folder, lists one text file and
copies it. All created files are removed when the context exits. It needs no Qt,
remote account or native SDK.

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from commonUtils.filesystem.directories import Directory
from commonUtils.formats.registry import file_from_path

with TemporaryDirectory() as temporary:
    root = Path(temporary)
    source = root / 'notes.txt'
    source.write_text('Hello from commonUtils!\n', encoding='utf-8')
    folder = Directory(root)
    items = folder.list_files(recursive=False, filter_extension=['txt'])
    assert [item.path.name for item in items] == ['notes.txt']

    item = file_from_path(source)
    copied = item.copy_file(root / 'copy.txt')
    assert item.path == source  # The original object is not retargeted.
    assert copied.path.read_text(encoding='utf-8') == source.read_text(encoding='utf-8')
    print('Listed and copied notes.txt; original path preserved.')
```

Expected output: `Listed and copied notes.txt; original path preserved.` Diagnostic
logging may also appear. The destination is new here; `copy_file` overwrites an
existing destination, so choose overwrite policy before using it on real files.
It returns a fresh plain `File`. Use `file_from_path(copied.path)` if you need
specialized format behavior afterward.

`Directory` requires a `pathlib.Path`; `File` normalizes its input. Resolution
chooses a class, not a guarantee that a file exists or is valid. Register project
classes before listing. Use [extension points](extension-points.md) for that contract.

For plain paths and cancellable filename filtering, use
`filesystem.traversal.scan_directory`. It skips nested directory links; recursive
`Directory.list_files()` follows them with loop detection. Avoid substituting one
for the other without considering that difference.

## Choose your next integration

| Need | Continue with |
| --- | --- |
| Resolve a suffix to a file class or register your own type | [Extension points](extension-points.md) |
| Read/write formats or choose save semantics | [Public API map](public-apis.md) |
| Run an external command without Qt | [Command wrapper](reference/integrations/wrappers/cmdShellWrapper/cmdShellWrapper.md) |
| Add widgets to a host application | [UI reference](reference/ui/ui.md) |
| Change library behavior | [Maintenance and tests](maintenance.md) |

A successful import does not certify every optional integration. Missing PySide6,
archive tools or native frameworks matters only when the selected component needs
them; install versions through the consumer's dependency policy.

## Embed a browser

The [runnable feature example](reference/ui/features/features.md#runnable-example-add-a-menu-action-to-a-browser)
creates QApplication, registers a feature, installs it in a FileBrowser and defers
closing until browser workers stop. Save the example beside the `commonUtils`
checkout, install PySide6 and run it with a local folder argument.

Registration belongs before the first listing. Window/controller construction
belongs on the GUI thread. If you add controller jobs, extend close handling to
wait for their completion as well as browser workers. See
[lifecycle contracts](architecture.md#initialization-and-shutdown).

To embed Markdown, use `MarkdownViewer`; to open a retained standalone or hosted
window, use `open_markdown`. Editing is opt-in. See the
[Markdown developer guide](reference/ui/markdown/markdown.md).

[Developer hub](development.md)
