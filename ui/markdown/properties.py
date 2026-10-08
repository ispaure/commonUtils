"""Properties panel for Markdown YAML frontmatter; no application/vault state."""
from datetime import date, datetime
from collections.abc import Mapping, Sequence
from ...markdownUtils import split_frontmatter, parse_properties, replace_property, replace_frontmatter, parse_property_value, RawYAML
from .. import pyside as qt


def property_type(value, name=''):
    if isinstance(value, bool):
        return 'Checkbox'
    if isinstance(value, datetime):
        return 'Date & time'
    if isinstance(value, date):
        return 'Date'
    if isinstance(value, (int, float)):
        return 'Number'
    if isinstance(value, Sequence) and not isinstance(value, str):
        if any(not isinstance(item, str) for item in value):
            return 'YAML'
        return 'Tags' if name == 'tags' else 'List'
    if isinstance(value, Mapping) or getattr(value, 'tag', None):
        return 'YAML'
    return 'Text'


def value_text(value):
    if value is None:
        return ''
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (list, tuple)):
        return '\n'.join(str(item) for item in value)
    if isinstance(value, RawYAML):
        return value.text
    return str(value)


def typed_value(kind, text):
    if kind == 'Text':
        return text
    if kind in ('List', 'Tags'):
        return [line for line in text.splitlines() if line.strip()]
    if kind == 'Checkbox':
        if text.strip().lower() not in ('true', 'false'):
            raise ValueError('A checkbox value must be true or false.')
        return text.strip().lower() == 'true'
    if kind == 'Number':
        value = parse_property_value(text)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError('Enter a literal number.')
        return value
    if kind == 'Date':
        return date.fromisoformat(text.strip())
    if kind == 'Date & time':
        return datetime.fromisoformat(text.strip())
    raise ValueError('Edit complex YAML directly in Source mode or Edit YAML.')


class MarkdownProperties(qt.QGroupBox):
    changed = qt.Signal(str)
    editable_changed = qt.Signal(bool)

    def __init__(self, parent=None):
        super().__init__('', parent)
        self.setFlat(True)
        self.source = ''
        self.data = {}
        self.editable = False
        self.syncing = False
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        header = qt.QHBoxLayout()
        title = qt.QLabel('Properties')
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)
        self.table = qt.QTreeWidget()
        self.table.setHeaderLabels(['Property', 'Type', 'Value'])
        self.table.setRootIsDecorated(False)
        self.table.setHeaderHidden(True)
        self.table.setFrameShape(qt.QFrame.Shape.NoFrame)
        self.table.setSelectionMode(qt.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setUniformRowHeights(True)
        self.table.setStyleSheet("QTreeView::item { padding: 4px 0; }")
        self.table.setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_property_menu)
        self.table.itemSelectionChanged.connect(self._update_selection_actions)
        self.table.setMaximumHeight(170)
        self.table.setAccessibleName('YAML properties')
        self.table.itemDoubleClicked.connect(lambda item, column: self.edit_property(item))
        self.table.itemChanged.connect(self._checkbox_changed)
        layout.addWidget(self.table)
        self.error = qt.QLabel()
        self.error.setWordWrap(True)
        self.error.setTextFormat(qt.Qt.TextFormat.PlainText)
        layout.addWidget(self.error)
        self.add_button = qt.QPushButton('+ Add property')
        self.edit_button = qt.QPushButton('Edit')
        self.remove_button = qt.QPushButton('Remove')
        self.yaml_button = qt.QPushButton('…')
        for button in (self.add_button, self.edit_button, self.remove_button, self.yaml_button):
            header.addWidget(button)
        self.add_button.setToolTip('Add a YAML property')
        self.edit_button.setToolTip('Edit the selected property (or double-click its row)')
        self.remove_button.setToolTip('Remove the selected property')
        self.yaml_button.setToolTip('More property options')
        self.yaml_button.setAccessibleName('More property options')
        self.yaml_button.setFixedWidth(30)
        menu = qt.QMenu(self.yaml_button)
        menu.addAction('Edit YAML…', self.edit_yaml)
        self.yaml_button.setMenu(menu)
        self.add_button.clicked.connect(lambda: self.edit_property())
        self.edit_button.clicked.connect(lambda: self.edit_property(self.table.currentItem()))
        self.remove_button.clicked.connect(self.remove_selected)
        self.set_editable(False)

    def set_editable(self, enabled):
        self.editable = enabled
        for button in (self.add_button, self.edit_button, self.remove_button, self.yaml_button):
            button.setVisible(enabled)
        self.refresh(self.source)
        self.editable_changed.emit(bool(enabled))

    def refresh(self, text):
        self.source = text
        parts = split_frontmatter(text)
        self.syncing = True
        self.table.clear()
        self.error.clear()
        try:
            self.data = parse_properties(parts) if parts.present else {}
            for name, value in self.data.items():
                kind = property_type(value, name)
                item = qt.QTreeWidgetItem([name, kind, value_text(value).replace('\n', ', ')])
                item.setToolTip(2, value_text(value))
                item.setForeground(1, self.palette().color(qt.QPalette.ColorRole.PlaceholderText))
                if kind == 'Checkbox':
                    item.setText(2, '')
                    if self.editable:
                        item.setFlags(item.flags() | qt.Qt.ItemFlag.ItemIsUserCheckable)
                    else:
                        item.setFlags(item.flags() & ~qt.Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(2, qt.Qt.CheckState.Checked if value else qt.Qt.CheckState.Unchecked)
                self.table.addTopLevelItem(item)
            self.table.resizeColumnToContents(0)
            self.table.resizeColumnToContents(1)
        except ValueError as error:
            self.data = {}
            self.error.setText(str(error))
        finally:
            self.syncing = False
        count = self.table.topLevelItemCount()
        self.table.setVisible(count > 0)
        height = self.table.sizeHintForRow(0) if count else 24
        self.table.setFixedHeight(min(170, max(28, height * count + 4)))
        self.error.setVisible(bool(self.error.text()))
        self.setVisible(bool(count or self.error.text()))
        self._update_selection_actions()

    def _update_selection_actions(self):
        selected = self.table.currentItem() is not None
        self.edit_button.setEnabled(self.editable and selected)
        self.remove_button.setEnabled(self.editable and selected)

    def _show_property_menu(self, point):
        if not self.editable:
            return
        item = self.table.itemAt(point)
        if item is not None:
            self.table.setCurrentItem(item)
        menu = qt.QMenu(self.table)
        menu.addAction('Add property…', lambda: self.edit_property())
        if item is not None:
            menu.addAction('Edit property…', lambda: self.edit_property(item))
            menu.addAction('Remove property', self.remove_selected)
        menu.addSeparator()
        menu.addAction('Edit YAML…', self.edit_yaml)
        menu.exec(self.table.viewport().mapToGlobal(point))

    def apply_property(self, name, value=None, *, remove=False):
        if not self.editable:
            return False
        try:
            updated = replace_property(self.source, name, value, remove=remove)
        except ValueError as error:
            self.error.setText(str(error))
            self.error.show()
            self.show()
            return False
        if updated != self.source:
            self.changed.emit(updated)
        return True

    def _checkbox_changed(self, item, column):
        if not self.syncing and self.editable and column == 2 and item.text(1) == 'Checkbox':
            self.apply_property(item.text(0), item.checkState(2) == qt.Qt.CheckState.Checked)

    def remove_selected(self):
        item = self.table.currentItem()
        if item is not None:
            self.apply_property(item.text(0), remove=True)

    def edit_property(self, item=None):
        if not self.editable:
            return
        if item is not None and property_type(self.data[item.text(0)], item.text(0)) == 'YAML':
            self.error.setText('This complex value is kept as raw YAML. Use Edit YAML or Source mode.')
            self.error.show()
            return
        dialog = qt.QDialog(self)
        dialog.setWindowTitle('Edit property' if item else 'Add property')
        form = qt.QFormLayout(dialog)
        name = qt.QLineEdit(item.text(0) if item else '')
        name.setReadOnly(item is not None)
        kind = qt.QComboBox()
        kind.addItems(['Text', 'List', 'Tags', 'Number', 'Checkbox', 'Date', 'Date & time'])
        value = qt.QPlainTextEdit()
        value.setMaximumHeight(150)
        value.setPlaceholderText('For lists/tags, enter one item per line. Dates use YYYY-MM-DD.')
        if item is not None:
            kind.setCurrentText(item.text(1))
            value.setPlainText(value_text(self.data[item.text(0)]))
        form.addRow('Name', name)
        form.addRow('Type', kind)
        form.addRow('Value', value)
        error = qt.QLabel()
        error.setWordWrap(True)
        error.setTextFormat(qt.Qt.TextFormat.PlainText)
        form.addRow(error)
        buttons = qt.QDialogButtonBox(qt.QDialogButtonBox.StandardButton.Ok | qt.QDialogButtonBox.StandardButton.Cancel)
        form.addRow(buttons)
        buttons.rejected.connect(dialog.reject)
        def accept():
            try:
                if item is None and name.text() in self.data:
                    raise ValueError('That property already exists. Edit its existing row.')
                parsed = typed_value(kind.currentText(), value.toPlainText())
                if self.apply_property(name.text(), parsed):
                    dialog.accept()
                else:
                    error.setText(self.error.text())
            except (ValueError, TypeError) as problem:
                error.setText(str(problem))
        buttons.accepted.connect(accept)
        dialog.resize(440, 300)
        dialog.exec()

    def edit_yaml(self):
        if not self.editable:
            return
        dialog = qt.QDialog(self)
        dialog.setWindowTitle('Edit YAML properties')
        layout = qt.QVBoxLayout(dialog)
        source = qt.QPlainTextEdit(split_frontmatter(self.source).yaml_text)
        layout.addWidget(source)
        error = qt.QLabel()
        error.setWordWrap(True)
        error.setTextFormat(qt.Qt.TextFormat.PlainText)
        layout.addWidget(error)
        buttons = qt.QDialogButtonBox(qt.QDialogButtonBox.StandardButton.Ok | qt.QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)
        buttons.rejected.connect(dialog.reject)
        def accept():
            try:
                updated = replace_frontmatter(self.source, source.toPlainText())
                if updated != self.source:
                    self.changed.emit(updated)
                dialog.accept()
            except ValueError as problem:
                error.setText(str(problem))
        buttons.accepted.connect(accept)
        dialog.resize(520, 400)
        dialog.exec()
