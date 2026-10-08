"""Ask before provisioning software and keep downloads off the GUI thread."""
from threading import Event
from . import pyside as qt
from .file_browser.operations import Operation
from ..downloads import is_ready, provision


class _DownloadDialog(qt.QDialog):
    progress_changed = qt.Signal(int, int)

    def __init__(self, spec, destination, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'Download {spec.name}')
        self.cancelled = Event()
        self.running = True
        self.result_path = None
        self.error = ''
        layout = qt.QVBoxLayout(self)
        self.label = qt.QLabel(f'Downloading and verifying {spec.name} {spec.version}…')
        layout.addWidget(self.label)
        self.progress = qt.QProgressBar()
        self.progress.setRange(0, 0)
        layout.addWidget(self.progress)
        self.cancel = qt.QPushButton('Cancel')
        self.cancel.clicked.connect(self.reject)
        layout.addWidget(self.cancel)
        self.progress_changed.connect(self._progress)
        self.operation = Operation(lambda: provision(spec, destination,
            progress=self._notify_progress, cancelled=self.cancelled.is_set), self)
        self.operation.completed.connect(self._completed)
        self.operation.finished.connect(self._finished)
        self.operation.start()

    def _notify_progress(self, done, total):
        # Qt int signals cannot carry very large download byte counts.
        self.progress_changed.emit(int(100 * done / total) if total else 0, 100 if total else 0)

    def _progress(self, done, total):
        self.progress.setRange(0, total)
        self.progress.setValue(done)

    def _completed(self, path, error):
        self.result_path, self.error = path, error

    def _finished(self):
        self.running = False
        self.operation.wait()
        self.accept()

    def reject(self):
        if self.running:
            self.cancelled.set()
            self.cancel.setEnabled(False)
            self.label.setText('Cancelling download…')
        else:
            super().reject()

    def closeEvent(self, event):
        if self.running:
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)


def ensure_download(spec, destination, *, parent=None, install=False):
    """Return the verified local file, or None on decline/cancel/failure."""
    if is_ready(spec, destination):
        if install and not qt.display_msg_box_yes_no(f'{spec.name} Required',
                f'{spec.name} filesystem support is missing. Open the verified installer?\n\n{destination}'):
            return None
        return provision(spec, destination)
    action = 'download and open its installer' if install else 'download it now'
    if not qt.display_msg_box_yes_no(f'{spec.name} Required',
            f'{spec.name} {spec.version} is missing or does not match the expected version.\n\n'
            f'Would you like to {action}?\n\n'
            f'Destination: {destination}\nSource: {spec.url}'):
        return None
    dialog = _DownloadDialog(spec, destination, parent)
    try:
        dialog.exec()
        if dialog.error and not dialog.cancelled.is_set():
            qt.display_msg_box_ok(f'{spec.name} Download Failed', dialog.error)
        return dialog.result_path
    finally:
        dialog.deleteLater()
