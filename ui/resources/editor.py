"""Provider-backed text editor: all drafts are session-only, even after export."""
from .. import pyside as qt
from .lifecycle import operations_for
from ..tasks.operation_progress import OperationProgress
from ...runtime.resources.selection import ResourceTextSession


class ResourceTextWindow(qt.QMainWindow):
    idle = qt.Signal()
    document_editor_id = 'text_editor'
    document_editor_name = 'Text Editor'
    private = True

    def __init__(self, choice, session, choose, open_choice, parent=None):
        super().__init__(parent)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.choice, self.session = choice, session
        self.choose, self.open_choice = choose, open_choice
        self.pending_close = False
        self.pending_choice = None
        self.editor = qt.QPlainTextEdit()
        self.editor.setPlainText(session.text.text)
        self.editor.document().setModified(False)
        self.status = qt.QLabel('Session-only draft · No recovery files or recent-file entries')
        self.status.setWordWrap(True)
        self.operation = OperationProgress(self)
        self.operation.completed.connect(self._saved)
        self.operations = operations_for(self)
        self.operations.bind(choice.provider)
        self.operations.own(self.operation, cancel=lambda: None)
        content = qt.QWidget()
        layout = qt.QVBoxLayout(content)
        layout.addWidget(self.editor, 1)
        layout.addWidget(self.status)
        layout.addWidget(self.operation)
        self.setCentralWidget(content)
        menu = self.menuBar().addMenu('File')
        self.open_action = menu.addAction('Open…', self.open_document, qt.QKeySequence.StandardKey.Open)
        self.save_action = menu.addAction('Save', self.save, qt.QKeySequence.StandardKey.Save)
        self.save_as_action = menu.addAction('Save As…', self.save_as, qt.QKeySequence.StandardKey.SaveAs)
        menu.addAction('Close', self.close, qt.QKeySequence.StandardKey.Close)
        self.resize(900, 650)
        self._title()
        self.editor.modificationChanged.connect(self._title)
        self.destroyed.connect(lambda: self.choice.close())

    def _title(self, *args):
        self.setWindowTitle('🕵️ Private - ' + self.session.text.name + (' *' if self.editor.document().isModified() else '') + ' — Text Editor')

    def open_document(self):
        if self.operation.busy:
            return
        choice = self.choose(self, 'open', self.choice.provider, self.session.text.name)
        if choice:
            self.open_choice(choice, self)

    def save(self):
        if self.operation.busy:
            return False
        draft = self.editor.toPlainText()
        self.editor.setReadOnly(True)
        session = self.session
        self.operation.start(lambda report, cancelled: session.save(draft, cancelled=cancelled), message='Saving verified text…')
        return True

    def save_as(self):
        if self.operation.busy:
            return
        choice = self.choose(self, 'save', self.choice.provider, self.session.text.name)
        if not choice:
            return
        draft = self.editor.toPlainText()
        self.pending_choice = choice
        self.editor.setReadOnly(True)
        session = self.session
        self.operation.start(lambda report, cancelled: session.save_as(choice.provider, choice.path, draft, cancelled=cancelled), message='Saving verified copy…')

    def _saved(self, session, error):
        self.editor.setReadOnly(False)
        if error:
            if self.pending_choice:
                self.pending_choice.close()
            self.pending_choice = None
            self.pending_close = False
            self.status.setText(error + ' Your draft is retained.')
        else:
            if self.pending_choice:
                self.choice.close()
                self.choice, self.pending_choice = self.pending_choice, None
            self.session = session
            self.editor.document().setModified(False)
            self._title()
            self.status.setText('Saved. Drafts remain session-only.')
        self.idle.emit()
        if self.pending_close:
            self.close()

    def closeEvent(self, event):
        from .picker import resource_tasks_pending
        if resource_tasks_pending(self):
            self.pending_close = True
            event.ignore()
            return
        if self.operation.busy:
            self.pending_close = True
            event.ignore()
            return
        if self.editor.document().isModified():
            answer = qt.QMessageBox.question(self, 'Unsaved private draft', 'Save your changes before closing?',
                qt.QMessageBox.StandardButton.Save | qt.QMessageBox.StandardButton.Discard | qt.QMessageBox.StandardButton.Cancel)
            if answer == qt.QMessageBox.StandardButton.Save:
                self.pending_close = True
                self.save()
                event.ignore()
                return
            if answer != qt.QMessageBox.StandardButton.Discard:
                self.pending_close = False
                event.ignore()
                return
        self.choice.close()
        self.editor.clear()
        event.accept()
