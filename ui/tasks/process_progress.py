"""Reusable process status/log presentation; execution lives in ProcessRunner."""
from .. import pyside as qt
from .process_runner import ProcessRunner

_windows = []


class ProcessProgressPresentation:
    """Optional widgets and display policy for a process window.

    The context layout appears above the bar, and the body below it. The
    window owns runner signals, numeric progress, completion and shutdown.
    """

    def __init__(self, window, context_layout, body):
        self.window = window
        window.context_fields = {}

    def status(self, state, attempt):
        if state == 'running':
            self.window.bar.setStyleSheet('')

    def reset(self):
        pass

    def update_metrics(self, values):
        pass

    def progress(self, update):
        self.window.bar.setFormat('%p%' if update.total > 0 else 'Working…')

    def completed(self, state):
        pass


class ProcessProgressWindow(qt.QDialog):
    idle = qt.Signal()

    def __init__(self, name, parent=None, *, runner=None, context=None, presentation=None):
        super().__init__(parent)
        self.setWindowFlag(qt.Qt.WindowType.Window, True)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(name)
        self.resize(850, 630)
        self.closing = False
        self.result = None
        self.metrics = {}
        self.context = dict(context or {})
        self.runner = runner or ProcessRunner(self)
        self.runner.setParent(self)
        layout = qt.QVBoxLayout(self)
        self.name = qt.QLabel(self.context.get('operation', name))
        self.name.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.state = qt.QLabel('Ready')
        self.state.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.state.setWordWrap(True)
        self.bar = qt.QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setAccessibleName('Operation progress')
        self.details = qt.QLabel()
        self.details.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.details.setWordWrap(True)
        self.log = qt.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setAccessibleName('Command output')
        self.log.setLineWrapMode(qt.QPlainTextEdit.LineWrapMode.NoWrap)
        self.cancel_button = qt.QPushButton('Cancel')
        self.cancel_button.clicked.connect(self._cancel_or_close)
        for widget in (self.name, self.state): layout.addWidget(widget)
        context_layout = qt.QFormLayout()
        layout.addLayout(context_layout)
        layout.addWidget(self.bar)
        if presentation is None:
            from .process_transfer_progress import legacy_transfer_presentation
            presentation = legacy_transfer_presentation
        self.presentation = presentation(self, context_layout, layout)
        layout.addWidget(self.details)
        self.logs_toggle = qt.QToolButton()
        self.logs_toggle.setText('Details and logs')
        self.logs_toggle.setCheckable(True)
        self.logs_toggle.setToolButtonStyle(qt.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.logs_toggle.setArrowType(qt.Qt.ArrowType.RightArrow)
        self.logs_toggle.toggled.connect(self._toggle_logs)
        layout.addWidget(self.logs_toggle)
        self.log.hide()
        layout.addWidget(self.log, 1)
        layout.addStretch()
        layout.addWidget(self.cancel_button)
        self.runner.output.connect(self._append_output)
        self.runner.status.connect(self._status)
        self.runner.progress.connect(self._progress)
        self.runner.completed.connect(self._completed)

    @staticmethod
    def _label(text):
        label = qt.QLabel(text)
        label.setTextFormat(qt.Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(qt.Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def _toggle_logs(self, opened):
        self.log.setVisible(opened)
        self.logs_toggle.setArrowType(qt.Qt.ArrowType.DownArrow if opened else qt.Qt.ArrowType.RightArrow)

    def _metrics(self, values):
        self.metrics = dict(values)
        self.presentation.update_metrics(self.metrics)

    @property
    def busy(self):
        return self.runner.busy

    def start(self, program, arguments=(), **options):
        self.result = None
        self.cancel_button.setText('Cancel')
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
        detail = message.splitlines()[0] if message else ''
        self.details.setText(detail)
        if state == 'running':
            self.bar.setProperty('operationState', 'running')
        self.presentation.status(state, attempt)
        if state == 'running' and message == 'Starting process…':
            self.metrics = {}
            self.presentation.reset()
            self.bar.setRange(0, 0)
            self.bar.setFormat('Starting…')
        if state in ('retrying', 'failed'):
            self.logs_toggle.setText('Details and logs · diagnostics available')

    def _progress(self, update):
        if update.metrics:
            self._metrics(update.metrics)
        self.presentation.progress(update)
        if update.total > 0:
            self.bar.setRange(0, 1000)
            self.bar.setValue(min(1000, max(0, int(update.done / update.total * 1000))))
        else:
            self.bar.setRange(0, 0)

    def _completed(self, result):
        self.result = result
        previous_value = self.bar.value()
        had_percentage = self.bar.maximum() > 0
        self.bar.setRange(0, 1000)
        if result.succeeded:
            self.bar.setValue(1000)
            self.bar.setFormat('Complete')
            self.bar.setProperty('operationState', 'succeeded')
            self.bar.setStyleSheet('QProgressBar { color: #ffffff; } QProgressBar::chunk { background-color: #247a46; }')
            self.bar.setToolTip('The process exited successfully.')
        else:
            self.bar.setValue(max(0, previous_value) if had_percentage else 0)
            self.bar.setFormat('Stopped at %p%' if had_percentage else result.state.capitalize())
            self.bar.setProperty('operationState', result.state)
            self.bar.setStyleSheet('QProgressBar::chunk { background-color: #aa7832; }')
        self.presentation.completed(result.state)
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


def present_process_window(window):
    """Show a process window in the current host and track it through shutdown."""
    _windows.append(window)
    window.destroyed.connect(lambda: _windows.remove(window) if window in _windows else None)
    from .process_host import show_process
    show_process(window)


def open_process(name, program, arguments=(), parent=None, *, parser=None, context=None,
                 presentation=None, **runner_options):
    window = ProcessProgressWindow(name, parent, runner=ProcessRunner(parser=parser, **runner_options),
                                   context=context, presentation=presentation)
    present_process_window(window)
    window.start(program, arguments)
    return window


def prepare_close_all(retry_close=None):
    ready = True
    for window in tuple(_windows):
        if retry_close and not window.closing:
            window.idle.connect(retry_close)
        if not window.prepare_close():
            ready = False
        else:
            window.close()
    return ready
