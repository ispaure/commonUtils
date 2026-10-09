"""Reusable process status/log presentation; execution lives in ProcessRunner."""
from . import pyside as qt
from .process_runner import ProcessRunner

_windows = []


class ProcessProgressWindow(qt.QDialog):
    idle = qt.Signal()

    def __init__(self, name, parent=None, *, runner=None):
        super().__init__(parent)
        self.setWindowFlag(qt.Qt.WindowType.Window, True)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(name)
        self.resize(850, 550)
        self.closing = False
        self.result = None
        self.runner = runner or ProcessRunner(self)
        self.runner.setParent(self)
        layout = qt.QVBoxLayout(self)
        self.name = qt.QLabel(name)
        self.name.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.state = qt.QLabel('Ready')
        self.state.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.state.setWordWrap(True)
        self.bar = qt.QProgressBar()
        self.bar.setRange(0, 0)
        self.details = qt.QLabel()
        self.details.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.details.setWordWrap(True)
        self.log = qt.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setAccessibleName('Command output')
        self.log.setLineWrapMode(qt.QPlainTextEdit.LineWrapMode.NoWrap)
        self.cancel_button = qt.QPushButton('Cancel')
        self.cancel_button.clicked.connect(self._cancel_or_close)
        for widget in (self.name, self.state, self.bar, self.details, self.log, self.cancel_button):
            layout.addWidget(widget)
        self.runner.output.connect(self._append_output)
        self.runner.status.connect(self._status)
        self.runner.progress.connect(self._progress)
        self.runner.completed.connect(self._completed)

    @property
    def busy(self):
        return self.runner.busy

    def start(self, program, arguments=(), **options):
        self.runner.start(program, arguments, **options)

    def _append_output(self, text):
        bar = self.log.verticalScrollBar()
        follow = bar.value() >= bar.maximum()
        cursor = self.log.textCursor()
        cursor.movePosition(qt.QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        if follow:
            bar.setValue(bar.maximum())

    def _status(self, state, attempt, message):
        self.state.setText(f'{state.capitalize()} · Attempt {attempt}')
        self.details.setText(message)

    def _progress(self, update):
        if update.total > 0:
            self.bar.setRange(0, 1000)
            self.bar.setValue(min(1000, max(0, int(update.done / update.total * 1000))))
        else:
            self.bar.setRange(0, 0)

    def _completed(self, result):
        self.result = result
        self.bar.setRange(0, 1000)
        if result.succeeded:
            self.bar.setValue(1000)
        else:
            self.bar.setValue(0)
        self.cancel_button.setText('Close')
        self.idle.emit()
        if self.closing:
            self.close()

    def _cancel_or_close(self):
        if self.busy:
            self.runner.cancel()
        else:
            self.close()

    def prepare_close(self):
        self.closing = True
        self.runner.cancel()
        return not self.busy

    def closeEvent(self, event):
        if self.prepare_close():
            event.accept()
        else:
            event.ignore()

    def reject(self):
        self.close()


def open_process(name, program, arguments=(), parent=None, *, parser=None, **runner_options):
    window = ProcessProgressWindow(name, parent, runner=ProcessRunner(parser=parser, **runner_options))
    _windows.append(window)
    window.destroyed.connect(lambda: _windows.remove(window) if window in _windows else None)
    window.show()
    window.start(program, arguments)
    return window


def prepare_close_all(retry_close=None):
    ready = True
    for window in tuple(_windows):
        if retry_close and not window.closing:
            window.idle.connect(retry_close)
        if not window.prepare_close():
            ready = False
    return ready
