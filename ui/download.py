"""Ask before provisioning software and keep downloads off the GUI thread."""
from . import pyside as qt
from .operation_progress import OperationProgress
from ..downloads import is_ready, provision, DownloadCancelled


class _DownloadDialog(qt.QDialog):
    def __init__(self, spec, destination, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'Download {spec.name}')
        self.result_path = None
        self.error = ''
        self.task = OperationProgress(self)
        self.task.completed.connect(self._completed)
        layout = qt.QVBoxLayout(self)
        layout.addWidget(self.task)
        message = f'Downloading and verifying {spec.name} {spec.version}…'
        def download(report, cancelled):
            try:
                return provision(spec, destination,
                                 progress=lambda done, total: report(done, total, message),
                                 cancelled=cancelled)
            except DownloadCancelled:
                return None
        self.task.start(download, message=message, cancel_message='Cancelling download…')

    @property
    def running(self):
        return self.task.busy

    @property
    def cancelled(self):
        return self.task.cancelled

    def _completed(self, path, error):
        self.result_path, self.error = path, error
        self.accept()

    def reject(self):
        if self.running:
            self.task.request_cancel()
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
        if dialog.error:
            qt.display_msg_box_ok(f'{spec.name} Download Failed', dialog.error)
        return dialog.result_path
    finally:
        dialog.deleteLater()
