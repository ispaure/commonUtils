"""Reusable transfer details for process windows."""
from ...filesystem import format_size
from .. import pyside as qt
from .process_progress import ProcessProgressPresentation


class TransferProgressPresentation(ProcessProgressPresentation):
    """Render byte counts, active items and optional operation-specific counters."""

    def __init__(self, window, context_layout, body, *, bytes_title='Transferred / total',
                 progress_format=None, count_rows=()):
        super().__init__(window, context_layout, body)
        self.progress_format = progress_format
        self.count_labels = {}
        for key, title in (('source', 'Source'), ('destination', 'Destination')):
            if key in window.context:
                value = window._label(str(window.context[key]))
                window.context_fields[key] = value
                context_layout.addRow(title, value)
        window.statistics = qt.QGroupBox('Transfer statistics')
        grid = qt.QGridLayout(window.statistics)
        window.fields = {}
        for index, (key, title) in enumerate((('bytes', bytes_title), ('speed', 'Speed'),
                ('files', 'Files / total'), ('eta', 'Time remaining'), ('checks', 'Checks / total'),
                ('elapsed', 'Elapsed'), ('errors', 'Errors'), ('warnings', 'Warnings'))):
            value = window._label('Not reported')
            window.fields[key] = value
            row, column = index // 2, (index % 2) * 2
            grid.addWidget(qt.QLabel(title), row, column)
            grid.addWidget(value, row, column + 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        window.statistics.setVisible(bool(window.context))
        body.addWidget(window.statistics)
        window.active = qt.QTreeWidget()
        window.active.setHeaderLabels(['Active transfer', 'Transferred / size', 'Speed', 'Time remaining'])
        window.active.setRootIsDecorated(False)
        window.active.setUniformRowHeights(True)
        window.active.setMaximumHeight(150)
        window.active.header().setSectionResizeMode(0, qt.QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            window.active.header().setSectionResizeMode(column, qt.QHeaderView.ResizeMode.ResizeToContents)
        window.active_status = window._label('Active transfer details not reported.')
        window.active.setVisible(bool(window.context))
        window.active_status.setVisible(bool(window.context))
        body.addWidget(window.active)
        body.addWidget(window.active_status)
        window.issue = window._label('')
        window.issue.hide()
        body.addWidget(window.issue)
        self.add_count_rows(count_rows)

    def add_count_rows(self, rows):
        window = self.window
        grid = window.statistics.layout()
        row = grid.rowCount()
        for index, (key, title) in enumerate(rows):
            label = qt.QLabel('Not reported')
            label.setTextInteractionFlags(qt.Qt.TextInteractionFlag.TextSelectableByMouse)
            self.count_labels[key] = window.fields[key] = label
            column = 2 * (index % 2)
            grid.addWidget(qt.QLabel(title), row + index // 2, column)
            grid.addWidget(label, row + index // 2, column + 1)

    @staticmethod
    def _duration(value):
        if value is None:
            return 'Not reported'
        seconds = int(value)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        return f'{hours:d}:{minutes:02d}:{seconds:02d}'

    @staticmethod
    def _pair(done, total, *, sizes=False):
        if done is None:
            return 'Not reported'
        format_value = format_size if sizes else lambda value: f'{int(value):,}'
        return format_value(done) + (' / ' + format_value(total) if total is not None else ' / total not reported')

    def update_metrics(self, values):
        window = self.window
        window.statistics.show()
        window.active.show()
        window.active_status.show()
        window.fields['bytes'].setText(self._pair(values.get('bytes'), values.get('total_bytes'), sizes=True))
        window.fields['files'].setText(self._pair(values.get('files'), values.get('total_files')))
        window.fields['checks'].setText(self._pair(values.get('checks'), values.get('total_checks')))
        speed = values.get('speed')
        window.fields['speed'].setText(format_size(speed) + '/s' if speed is not None else 'Not reported')
        window.fields['eta'].setText(self._duration(values.get('eta')))
        window.fields['elapsed'].setText(self._duration(values.get('elapsed')))
        errors = values.get('errors')
        window.fields['errors'].setText(str(int(errors)) if errors is not None else
                                     f'{values["reported_errors"]} error log records' if values.get('reported_errors') else 'Not reported')
        warnings = values.get('warnings')
        window.fields['warnings'].setText(str(int(warnings)) if warnings is not None else 'Not reported')
        window.issue.setText('Last reported error: ' + values['last_error'] if values.get('last_error') else '')
        window.issue.setVisible(bool(window.issue.text()))
        window.active.clear()
        transfers = values.get('active_transfers')
        for transfer in transfers or ():
            speed = transfer.get('speed')
            row = qt.QTreeWidgetItem([transfer.get('name', ''), self._pair(transfer.get('bytes'), transfer.get('total_bytes'), sizes=True),
                                     format_size(speed) + '/s' if speed is not None else 'Not reported',
                                     self._duration(transfer.get('eta'))])
            row.setToolTip(0, transfer.get('name', ''))
            window.active.addTopLevelItem(row)
        window.active_status.setText('Active transfer details not reported.' if transfers is None else
                                  f'{len(transfers)} active transfer(s).' if transfers else 'No active transfers in the latest statistics.')

    def reset(self):
        window = self.window
        for value in window.fields.values():
            value.setText('Not reported')
        window.issue.clear()
        window.issue.hide()
        window.active.clear()
        window.active_status.setText('Active transfer details not reported.')

    def status(self, state, attempt):
        if state != 'running':
            return
        window = self.window
        at_known_total = window.context and window.bar.format() == '100% of known work · Still running'
        window.bar.setStyleSheet('QProgressBar { color: #101620; }' if at_known_total else '')
        if at_known_total:
            window.state.setText(f'Still running · Attempt {attempt}')
            window.details.setText('Reported progress is 100%. Scanning or final checks may still be running.')

    def progress(self, update):
        window = self.window
        for key, label in self.count_labels.items():
            count = update.metrics.get(key)
            label.setText(f'{int(count):,}' if count is not None else 'Not reported')
        if update.total <= 0:
            window.bar.setFormat('Discovering / checking files…' if window.context else 'Working…')
            return
        if window.context and update.done >= update.total:
            window.bar.setFormat('100% of known work · Still running')
            window.details.setText('Reported progress is 100%. Scanning or final checks may still be running.')
        else:
            text = self.progress_format
            if text is None:
                text = ('Transferred: %p%' if update.metrics.get('progress_basis') == 'bytes' else
                        'Checks / files: %p%' if update.metrics else '%p%')
            window.bar.setFormat(text + ' of known work' if window.context else text)
        window.bar.setToolTip('Totals can grow as more files are discovered. Completion is confirmed when the process exits successfully.')

    def completed(self, state):
        window = self.window
        if window.metrics:
            window.fields['speed'].setText('—')
            window.fields['eta'].setText('—')
            window.active.clear()
            window.active_status.setText(f'No active transfers · {state}.')


def legacy_transfer_presentation(window, context_layout, body):
    """Preserve ProcessProgressWindow's original context and display contract."""
    options = (dict(bytes_title='Planned / total', progress_format='Planned: %p%')
               if window.context.get('dry_run') else {})
    return TransferProgressPresentation(window, context_layout, body, **options)
