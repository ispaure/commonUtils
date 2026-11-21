"""Display SQLite storage classes and collect explicitly typed edits."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from ...integrations.sqlite import ValidationError, parse_value
from .. import pyside as qt
from ..appearance.status_line import StatusLine


VALUE_KINDS = ('null', 'integer', 'real', 'text', 'blob')
_KINDS = {type(None): 'null', int: 'integer', float: 'real', str: 'text', bytes: 'blob'}
_MAX_INPUT = 65_536


def value_text(value, limit=160):
    if value is None:
        return 'NULL'
    if isinstance(value, bytes):
        prefix = value[:limit // 2].hex()
        suffix = '…' if len(value) * 2 > limit else ''
        return f"BLOB ({len(value)} bytes) X'{prefix}{suffix}'"
    if isinstance(value, str):
        prefix = repr(value[:limit])
        return f'{prefix}…' if len(value) > limit else prefix
    return str(value)


def _input_text(value):
    if value is None:
        return ''
    if isinstance(value, bytes):
        return value.hex()
    return str(value)


def typed_input(value):
    return _KINDS[type(value)], _input_text(value)


class RowEditor(qt.QDialog):
    """Collect insert fields or replacements for ordinary, stored columns."""

    def __init__(self, table, values, parent):
        super().__init__(parent)
        self.setWindowTitle('Insert row' if values is None else 'Edit row')
        self.resize(670, 400)
        self.changes = {}
        self._fields = []
        self._original = values
        layout = qt.QVBoxLayout(self)
        fields = qt.QWidget(self)
        form = qt.QFormLayout(fields)
        area = qt.QScrollArea(self)
        area.setWidgetResizable(True)
        area.setWidget(fields)
        layout.addWidget(area)
        for column in table.columns:
            if column.hidden:
                continue
            kind = qt.QComboBox()
            if values is None:
                kind.addItem('Use default', 'omit')
            for name in VALUE_KINDS:
                kind.addItem(name.upper(), name)
            value = qt.QLineEdit()
            # Validate our own input size, so a long paste cannot be truncated
            # and then accidentally staged as though it were the original.
            value.setMaxLength(2 ** 31 - 1)
            value.setAccessibleName(f'Value for {column.name}')
            kind.setAccessibleName(f'Type for {column.name}')
            row = qt.QHBoxLayout()
            row.addWidget(kind)
            row.addWidget(value, 1)
            caption = qt.QLabel(column.name)
            caption.setTextFormat(qt.Qt.TextFormat.PlainText)
            caption.setToolTip(column.declared_type)
            caption.setBuddy(value)
            form.addRow(caption, row)
            if values is not None:
                original = values[column.name]
                length = len(original) if isinstance(original, (str, bytes)) else 0
                if isinstance(original, bytes):
                    length *= 2
                if length > _MAX_INPUT:
                    kind.setEnabled(False)
                    value.setReadOnly(True)
                    value.setPlaceholderText('Value exceeds the editor size limit')
                    continue
                kind.setCurrentIndex(kind.findData(_KINDS[type(original)]))
                value.setText(_input_text(original))
            kind.currentIndexChanged.connect(
                lambda _index, k=kind, v=value: self._set_value_input(k, v))
            self._set_value_input(kind, value)
            self._fields.append((column.name, kind, value))
        self.status = StatusLine(parent=self)
        layout.addWidget(self.status)
        buttons = qt.QDialogButtonBox(qt.QDialogButtonBox.StandardButton.Ok |
                                     qt.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(qt.QDialogButtonBox.StandardButton.Ok).setText('Stage row')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _set_value_input(kind, value):
        selected = kind.currentData()
        value.setEnabled(selected not in ('null', 'omit'))
        value.setPlaceholderText('Hexadecimal byte pairs' if selected == 'blob' else '')

    def accept(self):
        changes = {}
        for name, kind, value in self._fields:
            selected = kind.currentData()
            if selected == 'omit':
                continue
            source = '' if selected == 'null' else value.text()
            if self._original is not None:
                old = self._original[name]
                if _KINDS[type(old)] == selected and source == _input_text(old):
                    continue
            try:
                if len(source) > _MAX_INPUT:
                    raise ValidationError(f'Enter at most {_MAX_INPUT:,} characters.')
                changes[name] = parse_value(selected, source)
            except ValidationError as error:
                self.status.setText(f'{name} · {error}')
                value.setFocus()
                return
        self.changes = changes
        super().accept()
