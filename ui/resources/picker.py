"""One provider-backed browser for Open and Save As; hosts supply storage leases."""
from pathlib import Path
from .. import pyside as qt
from .browser import ResourceBrowser
from .lifecycle import ResourceOperations, operations_for
from ..tasks.operation_progress import OperationProgress
from ...runtime.resources.selection import ResourceSelection, ResourceChoice


class ResourcePicker(qt.QDialog):
    def __init__(self, locations, *, parent=None, mode='open', name='', extensions=(), directory=''):
        super().__init__(parent)
        self.setWindowTitle('Open' if mode == 'open' else 'Save As' if mode == 'save' else 'Destination')
        self.resize(800, 600)
        self.locations, self.mode, self.extensions = locations, mode, extensions
        self.active_index = 0
        self.directories = {0: directory}
        self.browser = self.provider = None
        self.release = lambda: None
        self.choice = None
        self._pending_resolution = None
        self.closing = False
        self.operations = ResourceOperations()
        layout = qt.QVBoxLayout(self)
        self.storage = qt.QComboBox()
        self.storage.addItems([label for label, factory in locations])
        storage_row = qt.QHBoxLayout()
        storage_row.addWidget(qt.QLabel('Storage'))
        storage_row.addWidget(self.storage, 1)
        layout.addLayout(storage_row)
        self.folder = qt.QLineEdit(directory)
        self.folder.setPlaceholderText('Folder within this storage')
        self.folder.returnPressed.connect(self.navigate)
        layout.addWidget(self.folder)
        self.content = qt.QVBoxLayout()
        layout.addLayout(self.content, 1)
        self.name = qt.QLineEdit(name)
        self.name.setPlaceholderText('File name')
        layout.addWidget(self.name)
        self.notice = qt.QLabel()
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.operation = OperationProgress(self)
        self.operation.completed.connect(self._resolved)
        self.operations.own(self.operation)
        layout.addWidget(self.operation)
        buttons = qt.QDialogButtonBox(qt.QDialogButtonBox.StandardButton.Ok | qt.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.choose)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.storage.currentIndexChanged.connect(self.switch)
        self.switch(0)

    def switch(self, index):
        if self.operations.busy:
            self.storage.blockSignals(True)
            self.storage.setCurrentIndex(self.active_index)
            self.storage.blockSignals(False)
            return
        if self.browser:
            self.directories[self.active_index] = self.provider.relative(self.browser.navigation.directory)
            self.operations.retire(self.browser)
            self.browser.hide()
            self.content.removeWidget(self.browser)
            self.browser.deleteLater()
            self.browser = None
        self.release()
        self.release = lambda: None
        self.provider = None
        self.active_index = index
        title = 'Open' if self.mode == 'open' else 'Save As' if self.mode == 'save' else 'Destination'
        self.setWindowTitle(title)
        try:
            self.provider, self.release = self.locations[index][1]()
            self.setWindowTitle(('🕵️ Private - ' if getattr(self.provider, 'private', False) else '') + title)
            self.operations.bind(self.provider)
            self.model = ResourceSelection(self.provider, mode=self.mode, extensions=self.extensions)
            directory = self.directories.get(index, '')
            self.folder.setText(directory)
            self.browser = ResourceBrowser(self.model, directory=self.provider.root / directory, parent=self, preview=False)
            self.operations.own(self.browser, cancel=self.browser.stop)
            self.browser.notice.hide()  # The picker already describes the active storage.
            self.content.addWidget(self.browser)
            self.storage.setEnabled(False)
            self.browser.idle.connect(self._idle)
            self.browser.directory_changed.connect(lambda path: self.folder.setText(self.provider.relative(path)))
            self.browser.tree.itemSelectionChanged.connect(self._selected)
            self.browser.activated.connect(self._activated)
            self.notice.setText('Session-only browser. ' + ('Encrypted storage.' if getattr(self.provider, 'private', False)
                                else 'Local storage: files are saved without encryption.'))
        except Exception as error:
            self.notice.setText(str(error))
            self.storage.setEnabled(True)

    def _idle(self, *args):
        if self._pending_resolution is not None and not self.operation.busy and not self.browser.busy:
            path, error = self._pending_resolution
            self._pending_resolution = None
            self._resolved(path, error)
            return
        self.storage.setEnabled(True)
        if self.closing and not self.operation.busy:
            self.reject()

    def navigate(self):
        if self.browser and not self.operation.busy:
            try:
                path = self.provider.relative(self.folder.text())
                self.browser.navigate(self.provider.root / path)
                self.storage.setEnabled(False)
            except Exception as error:
                self.notice.setText(str(error))

    def _selected(self):
        rows = self.browser.selected_rows()
        if rows:
            row = rows[0]
            if not row['directory']:
                self.name.setText(row['name'])

    def _activated(self, path):
        directory = self.provider.relative(self.browser.navigation.directory)
        relative = self.provider.relative(path)
        self.name.setText(relative[len(directory) + 1:] if directory else relative)
        if self.mode == 'open':
            self.choose()

    def choose(self):
        if not self.provider or not self.browser or self.browser.operation.busy or self.operation.busy:
            return
        directory = self.provider.relative(self.browser.navigation.directory)
        name = self.name.text()
        self.storage.setEnabled(False)
        self.browser.setEnabled(False)
        model = self.model
        self._resolution_identity = self.operations.capture()
        self.operation.start(lambda report, cancelled: model.resolve(directory, name, cancelled=cancelled), message='Checking selection…')

    def _resolved(self, path, error):
        if self.browser and self.browser.busy:
            self._pending_resolution = (path, error)
            self.browser.stop()
            return
        self.storage.setEnabled(True)
        if self.browser:
            self.browser.setEnabled(True)
        if self.closing:
            self.reject()
        elif not self.operations.accepts(self._resolution_identity):
            self.notice.setText('Storage changed; choose the selection again.')
        elif error:
            if self.browser and self.browser.closing:
                self.browser.resume()
            self.notice.setText(error)
        else:
            self.choice = ResourceChoice(self.provider, path, self.release)
            self.release = lambda: None
            super().accept()

    def reject(self):
        self.closing = True
        if self.operations.stop():
            return
        self.release()
        self.release = lambda: None
        super().reject()

    def closeEvent(self, event):
        self.reject()
        event.ignore() if self.operations.busy else event.accept()


def choose_resource(locations, **options):
    dialog = ResourcePicker(locations, **options)
    try:
        dialog.exec()
        return dialog.choice
    finally:
        dialog.deleteLater()


class ResourceTaskDialog(qt.QDialog):
    """A short resource job whose window cannot disappear before its worker."""
    def __init__(self, parent, title):
        super().__init__(parent)
        self.owner = parent
        self.setWindowTitle(title)
        self.operation = OperationProgress(self)
        qt.QVBoxLayout(self).addWidget(self.operation)
        if parent is not None:
            operations_for(parent).own(self, busy=lambda: self.operation.busy,
                                       cancel=self.operation.request_cancel)
        self.operation.completed.connect(self._retired)

    def _retired(self, *args):
        if self.owner is not None:
            operations_for(self.owner).retire(self)
            if getattr(self.owner, 'pending_close', False):
                self.owner.close()

    def reject(self):
        if self.operation.busy:
            self.operation.request_cancel()
        else:
            super().reject()

    def closeEvent(self, event):
        if self.operation.busy:
            self.operation.request_cancel()
            event.ignore()
        else:
            event.accept()


def resource_tasks_pending(owner):
    return operations_for(owner).stop()
