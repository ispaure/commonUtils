# commonUtils

commonUtils provides reusable Python building blocks for file automation and
desktop tools. Run external commands, build a file browser with your own actions
and previews, and reuse helpers for files, archives, configuration and background
work across projects.

Use the parts you need in your own Python code. Logistics and Blue Hole are
existing consumers; your application supplies its own workflows, file types and
settings. commonUtils supports Windows, macOS and Linux, with some
platform-specific tools.

## Get started

Use **Python 3.10 or newer**. Place this repository in a folder named `commonUtils`
beside your Python code, with its parent directory on Python's import path:

```text
my_project/
├── project_browser.py
└── commonUtils/
```

You can also include it as a Git submodule; run
`git submodule update --init --recursive` after cloning. There is currently no
pip-installable package. Install the dependencies needed by the modules you use;
the browser example below requires `PySide6`.

See [project setup](launchers/README.md#use-it-in-a-project) for other directory
layouts and [dependencies and platforms](runtime/README.md#optional-dependencies-and-platforms)
for module requirements.

## Run commands from Python

Run a tool and inspect its output and exit status without writing your own process
handling. This example uses your current Python interpreter, so it needs no
additional command-line tool:

```python
import sys
from commonUtils.integrations.wrappers.cmdShellWrapper import run_command

result = run_command([sys.executable, "--version"], timeout=10)
if result.success:
    print("\n".join(result.stdout))
else:
    print(result.returncode, result.stderr, result.timed_out, result.cancelled)
```

`run_command()` also supports cancellation and a limit on time without output.
Its argument list runs without a shell by default. To launch a shell command in a
separate terminal window instead, use `exec_cmd()`:

```python
from commonUtils.integrations.wrappers.cmdShellWrapper import exec_cmd

exec_cmd("echo Hello from commonUtils", in_new_window=True)
```

The terminal window stays open after the command completes. Launching it returns
immediately and does not capture the command's output or completion status.
See the [command wrapper guide](integrations/wrappers/cmdShellWrapper/README.md)
for cancellation, timeouts and platform behavior.

## Build a browser with your own actions

Use the file browser inside an existing Qt application or give it its own window.
It provides navigation, search, file operations, previews and storage views;
you add the behavior specific to your project.

The example below opens a browser and adds **Project → Show selected paths** to
its context menu. Select files or folders to show their paths in the window's
status bar. Save it as `project_browser.py` beside `commonUtils`, install
`PySide6`, and run `python project_browser.py /path/to/folder`.

```python
from pathlib import Path
import sys
from commonUtils.ui.features import Feature, BrowserExtension, SelectionAction
from commonUtils.filesystem.files import File
from commonUtils.filesystem.directories import Directory
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser import FileBrowser

def show_paths(context):
    context.host.statusBar().showMessage(
        ' | '.join(str(path) for path in context.paths))

feature = Feature(
    id='project', label='Project',
    browser=BrowserExtension(actions=(SelectionAction(
        id='show_paths', label='Show selected paths',
        accepts=(File, Directory), handler=show_paths,
    ),)),
)

class BrowserWindow(qt.QMainWindow):
    def __init__(self, root):
        super().__init__()
        self.setWindowTitle('Project Browser')
        feature.register_types()  # Before the first listing.
        self.browser = FileBrowser(root, parent=self)
        self.setCentralWidget(self.browser)
        self.binding = feature.install_browser(self.browser, host=self)
        self.browser.idle.connect(self.close)
        self.resize(1000, 700)

    def closeEvent(self, event):
        # This example has no controller jobs; wait for browser workers.
        if self.browser.stop():
            event.ignore()
        else:
            super().closeEvent(event)

if __name__ == '__main__':
    app = qt.initialize_q_app()
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    window = BrowserWindow(root)
    window.show()
    sys.exit(app.exec())
```

The same feature mechanism lets you register custom file types, add preview
panels and thumbnails, and choose what happens when a file is double-clicked.
See [browser features](ui/features/README.md) for those examples and
[the file browser guide](ui/file_browser/README.md) for embedding and configuration.

## More building blocks

| What you want to do | Start here |
| --- | --- |
| Work with files, folders, links and directory indexes | [Filesystem](filesystem/README.md) |
| Read and write text, CSV, JSON, INI, XML and Markdown | [File formats](formats/README.md) |
| Create, inspect, extract and verify archives | [Archives](archives/README.md) |
| Edit INI settings or build a settings interface | [Configuration](configuration/README.md) |
| Run background work with progress and cancellation | [Qt operations](ui/operation_progress.md), [batch operations](runtime/operations/README.md) |
| Copy streams, hash data and verify downloads | [Streams](runtime/streams/README.md), [downloads](runtime/streams/downloads.md) |
| Rename files in batches | [Rename tools](filesystem/rename/README.md) |
| Reuse desktop widgets, readers and editors | [UI](ui/README.md) |
| Open applications, work with web links and wrap external tools | [Integrations](integrations/README.md) |
| Save files atomically and recover editing sessions | [Persistence](persistence/README.md) |

## Work with paths and archives

Use a `Directory` for registered file objects, or the traversal helper for plain
paths. Traversal skips directory links and can be cancelled.

```python
from pathlib import Path
from commonUtils.filesystem.traversal import scan_directory
from commonUtils import archives

folder = Path('/data/notes')
notes = scan_directory(folder, mask='*.txt', recursive=True)
print('Text files:', len(notes))
archives.create(notes, folder.parent / 'notes.zip')
```

Archive creation keeps existing outputs. For passwords, extraction and supported
formats, see [archives](archives/README.md). For saving JSON or replacing a staged
installation, see [persistence examples](persistence/README.md).

## Add progress without freezing a window

A worker callback handles files or commands; its completion handler updates the
UI after the worker stops. Use `OperationProgress` for progress and cancellation.
The [complete dialog example](ui/operation_progress.md#run-a-cancellable-job-in-a-qt-dialog)
shows how to keep the window alive during cancellation. Do not update widgets
from the worker or delete its owner while it is running.

## Contributing and compatibility

Keep application-specific workflows in the consuming project and reusable tools
in commonUtils. Use the module paths shown in the examples for new code;
historical imports remain supported through compatibility aliases.

Implementation boundaries and operation contracts are covered in
[package layout and compatibility](_compat.md). See [testing and development](tests/README.md#development-and-validation)
for validation commands and consumer checks. Keep this overview focused on the
library's purpose and practical entry points; put detailed API behavior and new
module documentation beside the code they describe.

## License

[MIT](LICENSE.md). Copyright © 2020–2026 Marc-André Voyer.
