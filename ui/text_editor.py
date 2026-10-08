"""Reusable UTF-8 text-file editor with atomic saves and unsaved-change protection."""
from pathlib import Path
from . import pyside as qt


class TextFileEditor(qt.QWidget):
    saved = qt.Signal(object)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = Path(path)
        self._original = None
        self._bom = False
        self._newline = '\n'
        layout = qt.QVBoxLayout(self)
        self.path_label = qt.QLabel(str(self.path))
        self.path_label.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.path_label.setTextInteractionFlags(qt.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)
        self.text = qt.QPlainTextEdit()
        self.text.setLineWrapMode(qt.QPlainTextEdit.LineWrapMode.NoWrap)
        self.text.setFont(qt.QFontDatabase.systemFont(qt.QFontDatabase.SystemFont.FixedFont))
        self.text.setAccessibleName(f'Text editor for {self.path.name}')
        layout.addWidget(self.text, 1)
        self.status = qt.QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(qt.Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        buttons = qt.QHBoxLayout()
        self.reload_button = qt.QPushButton('Reload')
        self.save_button = qt.QPushButton('Save')
        buttons.addWidget(self.reload_button)
        buttons.addStretch()
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)
        self.reload_button.clicked.connect(self.reload)
        self.save_button.clicked.connect(self.save)
        self.save_action = qt.QAction('Save', self)
        self.save_action.setShortcut(qt.QKeySequence(qt.QKeySequence.StandardKey.Save))
        self.save_action.setShortcutContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.save_action.triggered.connect(self.save)
        self.addAction(self.save_action)
        self.text.document().modificationChanged.connect(lambda modified: self.save_button.setEnabled(modified))
        self.reload(initial=True)

    @property
    def is_modified(self):
        return self.text.document().isModified()

    def reload(self, *, initial=False):
        if not initial and not self.can_close():
            return False
        try:
            data = self.path.read_bytes()
            text = data.decode('utf-8-sig')
        except (OSError, UnicodeError) as error:
            self.status.setText(f'Could not open file: {error}')
            if initial:
                self.text.setReadOnly(True)
                self.save_button.setEnabled(False)
            return False
        self._original = data
        self._bom = data.startswith(b'\xef\xbb\xbf')
        self._newline = '\r\n' if '\r\n' in text else '\n'
        self.text.setReadOnly(False)
        self.text.setPlainText(text)
        self.text.document().setModified(False)
        self.save_button.setEnabled(False)
        self.status.setText('Edit this file as plain text. Save explicitly to apply changes.')
        return True

    def save(self):
        if self._original is None:
            return False
        try:
            if self.path.read_bytes() != self._original:
                raise OSError('The file changed on disk. Reload before saving to preserve those changes.')
            if not self.is_modified:
                return True
            content = self.text.toPlainText().replace('\n', self._newline).encode('utf-8')
            if self._bom:
                content = b'\xef\xbb\xbf' + content
            file = qt.QSaveFile(str(self.path))
            if not file.open(qt.QIODevice.OpenModeFlag.WriteOnly):
                raise OSError(file.errorString())
            if file.write(content) != len(content) or not file.commit():
                raise OSError(file.errorString())
            self._original = content
            self.text.document().setModified(False)
            self.save_button.setEnabled(False)
            self.status.setText('Saved.')
            self.saved.emit(self.path)
            return True
        except OSError as error:
            self.status.setText(f'Could not save file: {error}')
            return False

    def can_close(self):
        if not self.is_modified:
            return True
        choice = qt.QMessageBox.question(self, 'Unsaved text changes',
            f'Save changes to {self.path.name}?',
            qt.QMessageBox.StandardButton.Save | qt.QMessageBox.StandardButton.Discard | qt.QMessageBox.StandardButton.Cancel,
            qt.QMessageBox.StandardButton.Cancel)
        if choice == qt.QMessageBox.StandardButton.Save:
            return self.save()
        if choice == qt.QMessageBox.StandardButton.Discard:
            return self.reload(initial=True)
        return False
