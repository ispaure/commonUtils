"""Reusable process status/log presentation; execution lives in ProcessRunner."""
from . import pyside as qt
from .process_runner import ProcessRunner
from ..filesystem import format_size

_windows = []


class ProcessProgressWindow(qt.QDialog):
    idle = qt.Signal()

    def __init__(self, name, parent=None, *, runner=None, context=None):
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
        self.context_fields = {}
        context_layout = qt.QFormLayout()
        for key, title in (('source', 'Source'), ('destination', 'Destination')):
            if key in self.context:
                value = self._label(str(self.context[key]))
                self.context_fields[key] = value
                context_layout.addRow(title, value)
        layout.addLayout(context_layout)
        layout.addWidget(self.bar)
        self.statistics = qt.QGroupBox('Transfer statistics')
        grid = qt.QGridLayout(self.statistics)
        self.fields = {}
        for index, (key, title) in enumerate((('bytes', 'Planned / total' if self.context.get('dry_run') else 'Transferred / total'), ('speed', 'Speed'),
                ('files', 'Files / total'), ('eta', 'Time remaining'), ('checks', 'Checks / total'),
                ('elapsed', 'Elapsed'), ('errors', 'Errors'), ('warnings', 'Warnings'))):
            value = self._label('Not reported')
            self.fields[key] = value
            row, column = index // 2, (index % 2) * 2
            grid.addWidget(qt.QLabel(title), row, column)
            grid.addWidget(value, row, column + 1)
        grid.setColumnStretch(1, 1); grid.setColumnStretch(3, 1)
        self.statistics.setVisible(bool(self.context))
        layout.addWidget(self.statistics)
        self.active = qt.QTreeWidget()
        self.active.setHeaderLabels(['Active transfer', 'Transferred / size', 'Speed', 'Time remaining'])
        self.active.setRootIsDecorated(False)
        self.active.setUniformRowHeights(True)
        self.active.setMaximumHeight(150)
        self.active.header().setSectionResizeMode(0, qt.QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            self.active.header().setSectionResizeMode(column, qt.QHeaderView.ResizeMode.ResizeToContents)
        self.active_status = self._label('Active transfer details not reported.')
        self.active.setVisible(bool(self.context)); self.active_status.setVisible(bool(self.context))
        layout.addWidget(self.active); layout.addWidget(self.active_status)
        self.issue = self._label('')
        self.issue.hide()
        layout.addWidget(self.issue)
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

    @staticmethod
    def _duration(value):
        if value is None: return 'Not reported'
        seconds = int(value)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        return f'{hours:d}:{minutes:02d}:{seconds:02d}'

    @staticmethod
    def _pair(done, total, *, sizes=False):
        if done is None: return 'Not reported'
        format_value = format_size if sizes else lambda value: f'{int(value):,}'
        return format_value(done) + (' / ' + format_value(total) if total is not None else ' / total not reported')

    def _metrics(self, values):
        self.metrics = dict(values)
        self.statistics.show(); self.active.show(); self.active_status.show()
        self.fields['bytes'].setText(self._pair(values.get('bytes'), values.get('total_bytes'), sizes=True))
        self.fields['files'].setText(self._pair(values.get('files'), values.get('total_files')))
        self.fields['checks'].setText(self._pair(values.get('checks'), values.get('total_checks')))
        speed = values.get('speed')
        self.fields['speed'].setText(format_size(speed) + '/s' if speed is not None else 'Not reported')
        self.fields['eta'].setText(self._duration(values.get('eta')))
        self.fields['elapsed'].setText(self._duration(values.get('elapsed')))
        errors = values.get('errors')
        self.fields['errors'].setText(str(int(errors)) if errors is not None else
                                     f'{values["reported_errors"]} error log records' if values.get('reported_errors') else 'Not reported')
        warnings = values.get('warnings')
        self.fields['warnings'].setText(str(int(warnings)) if warnings is not None else 'Not reported')
        self.issue.setText('Last reported error: ' + values['last_error'] if values.get('last_error') else '')
        self.issue.setVisible(bool(self.issue.text()))
        self.active.clear()
        transfers = values.get('active_transfers')
        for transfer in transfers or ():
            speed = transfer.get('speed')
            row = qt.QTreeWidgetItem([transfer.get('name', ''), self._pair(transfer.get('bytes'), transfer.get('total_bytes'), sizes=True),
                                     format_size(speed) + '/s' if speed is not None else 'Not reported',
                                     self._duration(transfer.get('eta'))])
            row.setToolTip(0, transfer.get('name', ''))
            self.active.addTopLevelItem(row)
        self.active_status.setText('Active transfer details not reported.' if transfers is None else
                                  f'{len(transfers)} active transfer(s).' if transfers else 'No active transfers in the latest statistics.')

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
        if state == 'running' and self.context and self.bar.format() == '100% of known work · Still running':
            self.state.setText(f'Still running · Attempt {attempt}')
            detail = 'All work discovered so far is processed. Scanning or final checks may still be running.'
        self.details.setText(detail)
        if state == 'running':
            self.bar.setProperty('operationState', 'running')
            self.bar.setStyleSheet('QProgressBar { color: #101620; }'
                                  if self.context and self.bar.format() == '100% of known work · Still running' else '')
        if state == 'running' and message == 'Starting process…':
            self.metrics = {}
            for value in self.fields.values(): value.setText('Not reported')
            self.issue.clear(); self.issue.hide(); self.active.clear()
            self.active_status.setText('Active transfer details not reported.')
            self.bar.setRange(0, 0)
            self.bar.setFormat('Starting…')
        if state in ('retrying', 'failed'):
            self.logs_toggle.setText('Details and logs · diagnostics available')

    def _progress(self, update):
        if update.metrics:
            self._metrics(update.metrics)
        if update.total > 0:
            self.bar.setFormat('Planned: %p%' if self.context.get('dry_run') else
                               'Transferred: %p%' if update.metrics.get('progress_basis') == 'bytes' else
                               'Checks / files: %p%' if update.metrics else '%p%')
            self.bar.setRange(0, 1000)
            self.bar.setValue(min(1000, max(0, int(update.done / update.total * 1000))))
            if self.context and update.done >= update.total:
                self.bar.setFormat('100% of known work · Still running')
                self.details.setText('All work discovered so far is processed. Scanning or final checks may still be running.')
            elif self.context:
                self.bar.setFormat(self.bar.format() + ' of known work')
            self.bar.setToolTip('Totals can grow as more files are discovered. Completion is confirmed when the process exits successfully.')
        else:
            self.bar.setRange(0, 0)
            self.bar.setFormat('Discovering / checking files…' if self.context else 'Working…')

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
        if self.metrics:
            self.fields['speed'].setText('—')
            self.fields['eta'].setText('—')
            self.active.clear()
            self.active_status.setText(f'No active transfers · {result.state}.')
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


def open_process(name, program, arguments=(), parent=None, *, parser=None, context=None, **runner_options):
    window = ProcessProgressWindow(name, parent, runner=ProcessRunner(parser=parser, **runner_options), context=context)
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
        else:
            window.close()
    return ready
