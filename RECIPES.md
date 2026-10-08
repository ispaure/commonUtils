# Reusable workflow recipes

These examples use the public commonUtils helpers. The consuming project supplies
its data, configuration, destination paths and UI policy. For browser extensions,
start with [FEATURES.md](FEATURES.md); for archive layout and verification, use
[ZIP_ARCHIVES.md](ZIP_ARCHIVES.md). The Qt examples require PySide6 and one
QApplication; the standalone examples initialize it themselves.

- [Cancellable Qt dialog](#run-a-cancellable-job-in-a-qt-dialog)
- [Cancellation between batch items](#finish-the-current-item-before-cancelling-a-batch)
- [Bounded stream copying and hashing](#copy-and-hash-bounded-streams)
- [Verified software provisioning](#provision-a-pinned-executable-or-installer)
- [JSON, CSV and text](#read-and-write-application-data)

## Run a cancellable job in a Qt dialog

`OperationProgress` owns the worker and progress controls. Its callback receives
`report(done, total, message)` and `cancelled()`. Reports are queued onto the GUI
thread, throttled, and support arbitrary-size byte counts. `total=0` means busy
progress. `completed(result, error)` is delivered only after the worker stops.

This complete example hashes selected files. It checks cancellation between files
and within each file. Supply actual paths when launching it:

```python
from pathlib import Path
import sys
from commonUtils.operations import OperationCancelled, check_cancelled
from commonUtils.streams import file_sha256
from commonUtils.ui import pyside as qt
from commonUtils.ui.operation_progress import OperationProgress

class HashDialog(qt.QDialog):
    def __init__(self, paths, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Hash files')
        self.paths = tuple(Path(path) for path in paths)
        self.task = OperationProgress(self)
        self.status = qt.QLabel('Ready')
        self.start_button = qt.QPushButton('Start')
        layout = qt.QVBoxLayout(self)
        for widget in (self.status, self.start_button, self.task):
            layout.addWidget(widget)
        self.start_button.clicked.connect(self.start)
        self.task.completed.connect(self.completed)

    def start(self):
        paths = self.paths  # Capture inputs before entering the worker.
        self.start_button.setEnabled(False)
        def work(report, cancelled):
            hashes = {}
            try:
                for index, path in enumerate(paths):
                    check_cancelled(cancelled)
                    report(index, len(paths), f'Hashing {path.name}')
                    hashes[path] = file_sha256(path, cancelled=cancelled)
                check_cancelled(cancelled)
                report(len(paths), len(paths), 'Finished')
                return hashes
            except OperationCancelled:
                return None  # Treat cancellation separately from a failure.
        self.task.start(work, message='Hashing…')

    def completed(self, hashes, error):
        self.start_button.setEnabled(True)
        if error:
            self.status.setText(f'Failed: {error}')
        elif hashes is None:
            self.status.setText('Cancelled')
        else:
            self.status.setText(f'Hashed {len(hashes)} files')
            print(hashes)

    def reject(self):  # Escape uses this path.
        if self.task.busy:
            self.task.request_cancel()
        else:
            super().reject()

    def closeEvent(self, event):
        if self.task.busy:
            self.task.request_cancel()
            event.ignore()
        else:
            super().closeEvent(event)

if __name__ == '__main__':
    app = qt.initialize_q_app()
    dialog = HashDialog(sys.argv[1:])
    dialog.show()
    sys.exit(app.exec())
```

Save as `hash_files.py` and run `python hash_files.py file1 file2` with commonUtils
on the import path. The dialog stays alive while cancellation finishes; after
completion it can be closed or restarted. Capture widget values before work starts,
and use only signals/reporting to communicate back from the worker. Do not open
password dialogs, change widgets or destroy the parent from the callback.

For background work without progress controls, `ui.operations.Operation(callback,
parent)` exposes `completed(result, error)` and the QThread `finished` signal.
The completed signal alone does not establish that its thread has stopped. Use
`OperationProgress` for the managed completion/close lifecycle, or retain the worker
until `finished` and wait for it before destruction.

## Finish the current item before cancelling a batch

Use `operations.run_batch` when each item has a transaction that must finish before
the next cancellation boundary. For example, each comic rebuild verifies and
publishes its own archive before the batch stops.

```python
from commonUtils.operations import run_batch

# These callables/inputs belong to your application.
def process_documents(documents, rebuild_one, report, cancelled):
    return run_batch(documents, rebuild_one,
                     progress=report, cancelled=cancelled)
```

The result has `completed` (list), `failed` (item → message), `remaining` (list) and
`cancelled` (bool). A work callback returning exactly `False` counts as failure;
other return values count as success unless an exception is raised. Failures
normally do not prevent later items from running. Supply `stop_on_error=True` to
stop on the first failure and retain the remainder.

Items must be hashable if they can fail, because failures are dictionary keys.
Progress counts processed items, including failures, so inspect the result instead
of assuming a full progress bar means success. Cancellation after the final item
has completed does not undo its success. Do not pass the batch cancellation callback
into `rebuild_one` if the intended policy is to finish the current item. Finer-grained
cancellation belongs to a different transaction policy.

To use this with `OperationProgress`, pass a callback such as
`lambda report, cancelled: process_documents(paths, rebuild_one, report, cancelled)`.
Inspect both the worker error string and the returned batch's failure dictionary.

## Copy and hash bounded streams

Stream progress callbacks receive the **current chunk's size**, not a cumulative
count. Download progress receives cumulative bytes; `OperationProgress` receives
(done, total, message). Translate deliberately between those interfaces.

```python
from hashlib import sha256
from io import BytesIO
from threading import Event
from commonUtils.streams import copy_stream, stream_signature

cancel = Event()
source = BytesIO(b'example payload')
output = BytesIO()
chunks = []
copy_stream(source, output, progress=chunks.append, cancelled=cancel.is_set)
assert sum(chunks) == len(output.getvalue())
assert stream_signature(BytesIO(output.getvalue())) == (
    len(output.getvalue()), sha256(output.getvalue()).hexdigest())
```

`iter_chunks` reads bounded 1 MiB chunks and checks cancellation before each read,
including the final EOF read. `file_sha256(path, cancelled=...)` hashes a file using
the same rules. Cancellation raises `OperationCancelled`; a partial copy remains
in the supplied output stream. These helpers do not delete files or publish staged
outputs. Use a disposable destination and promote only after your own validation.

## Provision a pinned executable or installer

Keep trusted release metadata in your project's manifest. This example expects a
JSON object with the `DownloadSpec` fields and an additional relative `path`:

```python
import json
from pathlib import Path
from commonUtils.downloads import DownloadSpec, provision

# Example field names: name, version, url, sha256, installed_sha256,
# archive_member (optional), executable (optional), path.
entry = json.loads(Path('tool_release.json').read_text(encoding='utf-8'))
relative_path = Path(entry.pop('path'))
spec = DownloadSpec(**entry)
destination = Path('Software') / relative_path
installed = provision(spec, destination)  # Reuses a matching installed file.
```

Use an HTTPS URL and lowercase 64-character SHA-256 digests. `sha256` verifies the
release bytes; `installed_sha256` verifies the final file. For a raw installer the
hashes are identical. For a ZIP release, set `archive_member` to the exact executable
member and compute the installed hash from that member in the verified release.
Only that member is streamed out. `executable=True` applies Unix execute permission.
The project must validate manifest paths before using untrusted metadata.

`provision` is synchronous and has no prompts. Add `progress(done, total)` and
`cancelled()` callbacks for use in a worker. Cancellation and failure clean staging
and retain a previous destination. Network reads can delay cancellation until the
read returns or times out. `DownloadCancelled` is an alias of `OperationCancelled`.

For a Qt application with an existing QApplication, use the shared prompt/dialog:

```python
from commonUtils.ui.download import ensure_download

path = ensure_download(spec, destination, parent=window)
if path is not None:
    launch_tool(path)  # Your application owns launching and command arguments.
```

`ensure_download` returns a verified Path, or `None` on decline, cancellation or
download-worker failure. Genuine worker failures remain visible even if Cancel was
also requested. Configuration validation and local filesystem errors outside the
download worker can still raise; the application should handle those at its UI
boundary. With
`install=True`, it also asks before returning an already-downloaded installer for
launch; it does not perform system installation. Download versions and destinations
are entirely project policy.

## Read and write application data

```python
from pathlib import Path
from commonUtils.fileTypes.jsonType import JSONFile
from commonUtils.fileTypes.csvType import CSVFile
from commonUtils.fileTypes.txtType import TXTFile

settings = JSONFile(Path('state/settings.json'))
settings.write_json({'enabled': True, 'names': ['Été']}, sort_keys=True)
assert settings.read_json()['enabled'] is True

rows = CSVFile(Path('state/report.csv'))
rows.write_csv([['Name', 'Count'], ['Example', '2']])
assert rows.read_csv()[1] == ['Example', '2']

notes = TXTFile(Path('state/notes.txt'))
notes.line_lst = ['First line', 'Second line']
notes.write_lines()
assert notes.read_lines() == notes.line_lst
```

These formats create parent directories on write. Only JSON's writer promises
atomic staging/replacement; text/CSV helpers retain their existing write semantics.
TXT entries must not contain embedded newlines. JSON rejects non-finite numbers;
use `compact=True` to omit formatting whitespace. Missing/malformed reads should be
handled at the application boundary. See [file-type details](fileTypes/README.md).
