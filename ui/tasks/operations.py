"""Background callbacks with one result/error contract and GUI-owner lifetimes."""
from .. import pyside as qt
from ...runtime.diagnostics import noninteractive_logging


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
        try:
            with noninteractive_logging():
                self.result = self.callback()
        except Exception as error:
            self.cancelled = isinstance(error, self.cancellation_errors)
            fallback = type(error).__name__
            try:
                message = self.error_formatter(error)
            except Exception:
                # A policy formatter may redact secrets. Never fall back to the
                # original exception text when that formatter fails.
                self.error = f'{fallback} (error formatting failed).'
            else:
                self.error = message if isinstance(message, str) and message.strip() else fallback

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
