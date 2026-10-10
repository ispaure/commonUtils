"""Search and remap caller-owned QAction commands without application imports."""
from . import pyside as qt
from PySide6.QtWidgets import QKeySequenceEdit


def shortcut_text(action):
    return action.shortcut().toString(qt.QKeySequence.SequenceFormat.PortableText)


def validate_shortcut(actions, key, sequence, reserved=("Escape",)):
    proposed = qt.QKeySequence(sequence)
    if proposed.isEmpty() and sequence:
        raise ValueError("Invalid shortcut.")
    candidates = [(other, action.shortcut()) for other, action in actions.items() if other != key]
    candidates += [("reserved navigation", qt.QKeySequence(value)) for value in reserved]
    for other, value in candidates:
        if not proposed.isEmpty() and not value.isEmpty() and (
            proposed.matches(value) != qt.QKeySequence.SequenceMatch.NoMatch
            or value.matches(proposed) != qt.QKeySequence.SequenceMatch.NoMatch
        ):
            raise ValueError(f"Shortcut conflicts with {other}.")
    return proposed


class CommandPalette(qt.QDialog):
    def __init__(self, actions, parent=None):
        super().__init__(parent)
        self.actions = actions
        self.setWindowTitle("Find Editor Command")
        self.resize(560, 420)
        layout = qt.QVBoxLayout(self)
        self.query = qt.QLineEdit()
        self.query.setPlaceholderText("Search commands…")
        self.query.setAccessibleName("Search commands")
        self.results = qt.QListWidget()
        layout.addWidget(self.query)
        layout.addWidget(self.results)
        self.query.textChanged.connect(self.refresh)
        self.query.returnPressed.connect(self.run_current)
        self.results.itemActivated.connect(lambda item: self.run_current())
        self.refresh()
        self.query.setFocus()

    def refresh(self):
        self.results.clear()
        terms = self.query.text().casefold().split()
        for key, action in self.actions.items():
            label = action.text().replace("&", "")
            if all(term in label.casefold() for term in terms):
                item = qt.QListWidgetItem(label + ("    " + shortcut_text(action) if shortcut_text(action) else ""))
                item.setData(qt.Qt.ItemDataRole.UserRole, key)
                if not action.isEnabled():
                    item.setFlags(item.flags() & ~qt.Qt.ItemFlag.ItemIsEnabled)
                self.results.addItem(item)
        for index in range(self.results.count()):
            if self.results.item(index).flags() & qt.Qt.ItemFlag.ItemIsEnabled:
                self.results.setCurrentRow(index)
                break

    def run_current(self):
        item = self.results.currentItem()
        if item is None:
            return
        action = self.actions[item.data(qt.Qt.ItemDataRole.UserRole)]
        if action.isEnabled():
            self.accept()
            action.trigger()

    def eventFilter(self, obj, event):
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() in (qt.Qt.Key.Key_Down, qt.Qt.Key.Key_Up):
            direction = 1 if event.key() == qt.Qt.Key.Key_Down else -1
            self.results.setCurrentRow(max(0, min(self.results.count() - 1, self.results.currentRow() + direction)))
        else:
            super().keyPressEvent(event)


class ShortcutDialog(qt.QDialog):
    def __init__(self, actions, defaults, save, parent=None):
        super().__init__(parent)
        self.actions, self.defaults, self.save = actions, defaults, save
        self.setWindowTitle("Editor Shortcuts")
        self.resize(560, 420)
        layout = qt.QVBoxLayout(self)
        self.commands = qt.QComboBox()
        for key, action in actions.items():
            self.commands.addItem(action.text().replace("&", ""), key)
        self.sequence = QKeySequenceEdit()
        self.error = qt.QLabel()
        self.error.setWordWrap(True)
        for widget in (self.commands, self.sequence, self.error):
            layout.addWidget(widget)
        buttons = qt.QHBoxLayout()
        for label, callback in (("Apply", self.apply), ("Restore Defaults", self.reset), ("Close", self.accept)):
            button = qt.QPushButton(label)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.commands.currentIndexChanged.connect(self.selected)
        self.selected()

    def selected(self):
        self.sequence.setKeySequence(self.actions[self.commands.currentData()].shortcut())
        self.error.clear()

    def apply(self):
        key = self.commands.currentData()
        value = self.sequence.keySequence().toString(qt.QKeySequence.SequenceFormat.PortableText)
        try:
            validate_shortcut(self.actions, key, value)
            overrides = {k: shortcut_text(a) for k, a in self.actions.items()}
            overrides[key] = value
            self.save(overrides)
            self.error.setText("Shortcut saved.")
        except (ValueError, OSError) as error:
            self.error.setText(str(error))

    def reset(self):
        try:
            self.save({})
            self.selected()
        except OSError as error:
            self.error.setText(str(error))
