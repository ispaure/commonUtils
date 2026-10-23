# Qt operation progress

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
from commonUtils.runtime.operations import OperationCancelled, check_cancelled
from commonUtils.runtime.streams import file_sha256
from commonUtils.ui import pyside as qt
from commonUtils.ui.tasks.operation_progress import OperationProgress

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

For background work without progress controls, `ui.tasks.operations.Operation(callback,
parent)` exposes `completed(result, error)` and the QThread `finished` signal.
The completed signal alone does not establish that its thread has stopped. Use
`OperationProgress` for the managed completion/close lifecycle, or retain the worker
until `finished` and wait for it before destruction.

ProcessRunner and open_process accept an optional `environment` mapping containing
the complete child environment. Omitting it inherits the system environment; an
empty mapping supplies none. Values are never added to command arguments or job
context. The caller owns filtering and the lifetime of sensitive values.

## Result-worker failure admission

`ui.tasks.operations.ResultWorker` clears its result, error and cancellation flag
at the start of each run, including a restarted worker. A failed callback always
produces a nonempty error string: empty exception text and blank/non-string
formatter output fall back to the exception type. If a host redaction formatter
raises, the error reports the exception type and formatting failure without
falling back to unredacted exception messages. The configured cancellation flag
is retained for that failed run. Successful callbacks still expose `error=None`.

`Operation` and `OperationProgress` share this behavior. An empty-message exception
must never be displayed as a successful finished operation. Thread retention and
`finished`-before-destruction requirements are unchanged.
