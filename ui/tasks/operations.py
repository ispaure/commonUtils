"""Background callbacks with one result/error contract and GUI-owner lifetimes."""
from .. import pyside as qt
from ...runtime.diagnostics import noninteractive_logging


def _format_error(error, formatter=str):
    """Keep failures visible without bypassing a host's redaction policy."""
    fallback = type(error).__name__
    try:
        message = formatter(error)
    except Exception:
        return f'{fallback} (error formatting failed).'
    return message if isinstance(message, str) and message.strip() else fallback


def _run_callback(callback, error_formatter=str, cancellation_errors=()):
    try:
        with noninteractive_logging():
            return callback(), None, False
    except Exception as error:
        return None, _format_error(error, error_formatter), isinstance(error, cancellation_errors)


class ResultWorker(qt.QThread):
    """Owners consume result/error after finished, retaining the worker until then.

    The owner supplies cancellation boundaries and error formatting. Calling
    cancel requests cooperative interruption; it never terminates a thread.
    """
    def __init__(self, callback, parent=None, *, error_formatter=str, cancellation_errors=()):
        super().__init__(parent)
        self.callback = callback
        self.error_formatter = error_formatter
        self.cancellation_errors = cancellation_errors
        self.result = None
        self.error = None
        self.cancelled = False

    def run(self):
        self.result = None
        self.error = None
        self.cancelled = False
        self.result, self.error, self.cancelled = _run_callback(
            self.callback, self.error_formatter, self.cancellation_errors)

    def cancel(self):
        self.requestInterruption()


class Operation(ResultWorker):
    """Compatibility callback worker; completed precedes thread retirement.

    Use finished (or OperationProgress) when destroying a worker-owning widget.
    """
    completed = qt.Signal(object, str)

    def run(self):
        super().run()
        self.completed.emit(self.result, self.error or '')


class ProgressOperation:
    """Run a progress job on a plain Qt thread, without a Python Qt subclass."""

    def __init__(self, parent):
        self.thread = qt.QThread(parent)
        self.thread.started.connect(self._run, qt.Qt.ConnectionType.DirectConnection)
        self.callback = None
        self.result = None
        self.error = None

    def start(self):
        self.thread.start()

    def wait(self):
        return self.thread.wait()

    def isRunning(self):
        return self.thread.isRunning()

    def isFinished(self):
        return self.thread.isFinished()

    def _run(self):
        try:
            self.result, self.error, _ = _run_callback(self.callback)
        finally:
            self.thread.quit()
