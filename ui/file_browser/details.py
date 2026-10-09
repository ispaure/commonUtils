"""Compact, selectable label/value information for filesystem detail tabs."""

from .. import pyside as qt


class DetailValue(qt.QLabel):
    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        hint.setWidth(0)
        return hint


class DetailsPanel(qt.QScrollArea):
    def __init__(self, fields=(), error='', parent=None):
        super().__init__(parent)
        self.fields = tuple(fields)
        self.error = error
        self.form = None
        self.field_labels = []
        self._compact = None
        self.setWidgetResizable(True)
        self.setFrameShape(qt.QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = qt.QWidget()
        layout = qt.QVBoxLayout(content)
        layout.setContentsMargins(12, 16, 12, 16)
        if error:
            message = qt.QLabel(f'Cannot load information: {error}')
            message.setTextFormat(qt.Qt.TextFormat.PlainText)
            message.setWordWrap(True)
            layout.addWidget(message)
        else:
            form = qt.QFormLayout()
            self.form = form
            form.setContentsMargins(0, 0, 0, 0)
            form.setHorizontalSpacing(14)
            form.setVerticalSpacing(9)
            form.setLabelAlignment(qt.Qt.AlignmentFlag.AlignRight | qt.Qt.AlignmentFlag.AlignTop)
            form.setFieldGrowthPolicy(qt.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            for name, value in self.fields:
                label = qt.QLabel(str(name))
                label.setTextFormat(qt.Qt.TextFormat.PlainText)
                label.setForegroundRole(qt.QPalette.ColorRole.PlaceholderText)
                label.setAlignment(qt.Qt.AlignmentFlag.AlignRight | qt.Qt.AlignmentFlag.AlignTop)
                label.setWordWrap(True)
                label.setMinimumWidth(85)
                label.setMaximumWidth(135)
                self.field_labels.append(label)
                text = DetailValue(str(value))
                text.setAlignment(qt.Qt.AlignmentFlag.AlignLeft | qt.Qt.AlignmentFlag.AlignTop)
                text.setTextFormat(qt.Qt.TextFormat.PlainText)
                text.setTextInteractionFlags(qt.Qt.TextInteractionFlag.TextSelectableByMouse |
                                             qt.Qt.TextInteractionFlag.TextSelectableByKeyboard)
                text.setWordWrap(True)
                text.setMinimumWidth(0)
                policy = qt.QSizePolicy(qt.QSizePolicy.Policy.Expanding, qt.QSizePolicy.Policy.Preferred)
                policy.setHeightForWidth(True)
                text.setSizePolicy(policy)
                text.setAccessibleName(str(name))
                form.addRow(label, text)
            layout.addLayout(form)
        layout.addStretch()
        self.setWidget(content)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.viewport().width() < 300
        if self.form is None or compact == self._compact:
            return
        self._compact = compact
        self.form.setRowWrapPolicy(qt.QFormLayout.RowWrapPolicy.WrapAllRows if compact else
                                   qt.QFormLayout.RowWrapPolicy.DontWrapRows)
        alignment = (qt.Qt.AlignmentFlag.AlignLeft if compact else qt.Qt.AlignmentFlag.AlignRight)
        self.form.setLabelAlignment(alignment | qt.Qt.AlignmentFlag.AlignTop)
        for label in self.field_labels:
            label.setAlignment(alignment | qt.Qt.AlignmentFlag.AlignTop)

    def toPlainText(self):
        """Retain read-only text access for callers inspecting detail content."""
        if self.error:
            return f'Cannot load information: {self.error}'
        return '\n'.join(f'{name}: {value}' for name, value in self.fields)

    def isReadOnly(self):
        return True
