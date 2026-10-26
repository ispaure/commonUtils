"""Reusable worker, progress and cooperative-cancellation UI for long operations.

A callback receives (report, cancelled). It must never touch Qt widgets. Reports
are (done, total, message); total=0 means indeterminate. Completion is delivered
on the GUI thread only after the worker has stopped, so owners can close safely.
"""
from threading import Event
from time import monotonic
from .. import pyside as qt
from ..appearance.status_line import StatusFooter
from .operations import Operation, _format_error


class OperationProgress(StatusFooter):
    completed = qt.Signal(object, str)
    progress_changed = qt.Signal(object, object, str)

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.busy = False
        self.cancelled = Event()
        self.operation = None
        self._result = (None, '')
        self.bar = qt.QProgressBar()
        self.bar.setMaximumWidth(140)
        self.bar.setSizePolicy(qt.QSizePolicy.Policy.Preferred, qt.QSizePolicy.Policy.Fixed)
        self.cancel_button = qt.QPushButton('Cancel')
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.request_cancel)
        for widget in (self.bar, self.cancel_button):
            self.layout().addWidget(widget)
        self.progress_changed.connect(self._progress)
        self.hide()

    def start(self, work, *, message='Working…', cancel_text='Cancel', cancel_message='Cancelling safely…',
              show_progress=True):
        """Start a job; show_progress=False keeps automatic background work out of the layout."""
        if self.busy:
            raise RuntimeError('An operation is already running')
        self.setVisible(show_progress)
        self.busy = True
        self.cancelled.clear()
        self.cancel_message = cancel_message
        self._result = (None, '')
        self.message.setText(message)
        self.bar.setRange(0, 0)
        self.cancel_button.setText(cancel_text)
        self.cancel_button.setEnabled(True)
        last_report = 0.0
        def report(done, total, message):
            nonlocal last_report
            now = monotonic()
            if now - last_report >= .05 or (total and done >= total):
                last_report = now
                self.progress_changed.emit(done, total, message)
        try:
            self.operation = Operation(lambda: work(report, self.cancelled.is_set), self)
            self.operation.completed.connect(self._remember_result)
            self.operation.finished.connect(self._finished)
            self.operation.start()
        except Exception as error:
            self._remember_result(None, _format_error(error))
            # Preserve asynchronous completion even when no worker could start.
            qt.QTimer.singleShot(0, self, self._finished)

    def _remember_result(self, result, error):
        self._result = result, error

    def _finished(self):
        operation = self.operation
        if operation is not None:
            operation.wait()
        self.operation = None
        self.busy = False
        self.cancel_button.setEnabled(False)
        result, error = self._result
        cancelled = self.cancelled.is_set() or getattr(result, 'cancelled', False)
        self.bar.setRange(0, 1000)
        self.bar.setValue(0 if error or cancelled else 1000)
        self.message.setText(f'Operation failed: {error}' if error else
                             'Cancelled.' if cancelled else 'Finished.')
        if operation is not None:
            operation.deleteLater()
        self.completed.emit(*self._result)

    def _progress(self, done, total, message):
        if not self.busy:
            return
        if total:
            self.bar.setRange(0, 1000)
            self.bar.setValue(min(1000, int(done * 1000 / total)))
        else:
            self.bar.setRange(0, 0)
        if not self.cancelled.is_set():
            self.message.setText(message)

    def request_cancel(self):
        if self.busy:
            self.cancelled.set()
            self.cancel_button.setEnabled(False)
            self.message.setText(self.cancel_message)
