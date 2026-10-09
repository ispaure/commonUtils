"""Default clipboard and inline-rename actions for every reusable browser."""

from pathlib import Path
from uuid import uuid4
from .. import pyside as qt
from ..operation_progress import OperationProgress
from ...file_operations import transfer_paths

OPERATION_MIME = 'application/x-commonutils-file-operation'
WINDOWS_EFFECT_MIME = 'application/x-qt-windows-mime;value="Preferred DropEffect"'


def clipboard_files():
    mime = qt.QApplication.clipboard().mimeData()
    if mime is None:
        return (), False, b''
    paths = tuple(dict.fromkeys(Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile()))
    marker = bytes(mime.data(OPERATION_MIME))
    gnome = bytes(mime.data('x-special/gnome-copied-files'))
    if not paths and gnome.startswith((b'cut\n', b'copy\n')):
        urls = [qt.QUrl.fromEncoded(line) for line in gnome.splitlines()[1:]]
        paths = tuple(dict.fromkeys(Path(url.toLocalFile()) for url in urls if url.isLocalFile()))
    move = (marker.startswith(b'move:') or gnome.startswith(b'cut\n')
            or bytes(mime.data(WINDOWS_EFFECT_MIME))[:4] == (2).to_bytes(4, 'little'))
    return paths, move, marker


def set_clipboard_files(paths, move=False):
    mime = qt.QMimeData()
    urls = [qt.QUrl.fromLocalFile(str(Path(path).absolute())) for path in paths]
    mime.setUrls(urls)
    mime.setData(OPERATION_MIME, f'{"move" if move else "copy"}:{uuid4()}'.encode())
    mime.setData('x-special/gnome-copied-files', ('cut\n' if move else 'copy\n').encode() +
                 '\n'.join(url.toString(qt.QUrl.ComponentFormattingOption.FullyEncoded) for url in urls).encode())
    mime.setData(WINDOWS_EFFECT_MIME, (2 if move else 1).to_bytes(4, 'little'))
    qt.QApplication.clipboard().setMimeData(mime)


class FileActions(qt.QObject):
    def __init__(self, browser):
        super().__init__(browser)
        self.browser = browser
        self.task = OperationProgress(browser)
        browser.layout().addWidget(self.task)
        self.task.completed.connect(self._completed)
        self.shortcuts = []
        for key, callback in ((qt.QKeySequence.StandardKey.Copy, lambda: self.copy(browser.selected_objects())),
                              (qt.QKeySequence.StandardKey.Cut, lambda: self.copy(browser.selected_objects(), move=True)),
                              (qt.QKeySequence.StandardKey.Paste, self.paste_current)):
            shortcut = qt.QShortcut(qt.QKeySequence(key), browser)
            shortcut.setContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(lambda callback=callback: browser._run(callback))
            self.shortcuts.append(shortcut)
        rename = qt.QShortcut(qt.QKeySequence(qt.Qt.Key.Key_F2), browser)
        rename.setContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        rename.activated.connect(self.rename_selected)
        self.shortcuts.append(rename)
        browser.model.edit_failed.connect(self._error)
        browser.model.fileRenamed.connect(self._renamed)

    @property
    def busy(self):
        return self.task.busy

    def copy(self, selection, move=False):
        if selection and not self.browser.stopping and (not move or not self.busy):
            set_clipboard_files([item.path for item in selection], move)

    def rename_selected(self):
        if self.browser.index_search.active:
            paths = self.browser.index_search.selected_paths()
            if len(paths) == 1:
                self.rename(self.browser.model.index(str(paths[0])))
            return
        selection = self.browser.views.selected_rows()
        if len(selection) == 1:
            self.rename(selection[0])

    def rename(self, index):
        if not self.busy and not self.browser.stopping and index.isValid():
            if self.browser.index_search.active:
                self.browser.index_search.show_in_browser(self.browser.model.filePath(index))
            persistent = qt.QPersistentModelIndex(index)
            qt.QTimer.singleShot(0, self.browser, lambda: self.browser.views.edit_name(qt.QModelIndex(persistent))
                                if persistent.isValid() else None)

    def paste_current(self):
        self.paste(self.browser.views.browsing_directory())

    def paste(self, directory):
        if self.busy or self.browser.stopping or directory is None:
            return
        paths, move, marker = clipboard_files()
        if not paths:
            return
        self.clipboard_request = paths, move, marker
        self.destination = Path(directory)
        self.browser.model.setReadOnly(True)
        self.task.start(lambda report, cancelled: transfer_paths(paths, directory, move=move,
                       report=report, cancelled=cancelled), message='Moving files…' if move else 'Copying files…')

    def _completed(self, result, error):
        self.browser.model.setReadOnly(False)
        self.task.hide()
        paths, move, marker = self.clipboard_request
        if result is not None and move and clipboard_files() == self.clipboard_request:
            completed = tuple(source for source, target in result.completed)
            def retained(path):
                canonical = path.parent.resolve() / path.name
                return not any(canonical == source or source in canonical.parents for source in completed)
            remaining = tuple(path for path in paths if retained(path))
            if remaining:
                set_clipboard_files(remaining, move=True)
            else:
                qt.QApplication.clipboard().clear()
        if not self.browser.stopping:
            self.browser.refresh()
            if error:
                self._error(error)
            elif result is not None and result.failures:
                self._error('\n'.join(f'{source.name}: {issue}' for source, issue in result.failures))
        self.browser._maybe_idle()

    def _renamed(self, parent, before, after):
        for name in (before, after):
            path = Path(parent) / name
            self.browser.model.invalidate(path)
            self.browser.views.covers.invalidate(path)
        self.browser.refresh()

    def _error(self, message):
        qt.QMessageBox.warning(self.browser, 'File operation could not be completed', message)

    def stop(self):
        self.task.request_cancel()
        return self.busy

    def wait(self):
        if self.task.operation is not None:
            self.task.operation.wait()
