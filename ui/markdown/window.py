"""Standalone Markdown window menus, title and lifetime management."""
from .. import pyside as qt
from .viewer import MarkdownViewer


class MarkdownWindow(qt.QMainWindow):
    def __init__(self, path, parent=None, *, allow_edit=False):
        super().__init__(parent)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        allow_edit = bool(allow_edit or qt.QApplication.keyboardModifiers() & qt.Qt.KeyboardModifier.AltModifier)
        self.viewer = MarkdownViewer(parent=self, allow_edit=allow_edit)
        self.setCentralWidget(self.viewer)
        self.viewer.path_changed.connect(lambda path: self._update_title())
        self.viewer.modified_changed.connect(lambda modified: self._update_title())
        self._file_menu = file_menu = self.menuBar().addMenu('File')
        for action in (self.viewer.new_action, self.viewer.open_action, self.viewer.save_action, self.viewer.save_as_action):
            file_menu.addAction(action)
        file_menu.addSeparator()
        file_menu.addAction('Close', self.close, qt.QKeySequence(qt.QKeySequence.StandardKey.Close))
        self._edit_menu = edit_menu = self.menuBar().addMenu('Edit')
        for action in (self.viewer.undo_action, self.viewer.redo_action, self.viewer.cut_action,
                       self.viewer.copy_action, self.viewer.paste_action, self.viewer.select_all_action,
                       self.viewer.find_action):
            edit_menu.addAction(action)
        self._view_menu = view_menu = self.menuBar().addMenu('View')
        if self.viewer.allow_edit:
            view_menu.addAction('Edit / Read', self.viewer.edit_button.click)
        view_menu.addAction('Table of contents', self.viewer.show_contents)
        self.setWindowTitle('Documentation')
        self.resize(900, 700)
        self.viewer.open_document(path)

    def _update_title(self):
        path = self.viewer.current_path
        title = path.name if path else 'Markdown'
        self.setWindowTitle(f'{title}{" *" if self.viewer.is_modified else ""} — Markdown')

    def closeEvent(self, event):
        if self.viewer.can_close():
            super().closeEvent(event)
        else:
            event.ignore()


_windows = set()


def open_markdown(path, *, parent=None, allow_edit=False):
    """Open a preview window; allow_edit=True or holding Alt starts editing. Requires Qt app."""
    window = MarkdownWindow(path, parent, allow_edit=allow_edit)
    _windows.add(window)
    window.destroyed.connect(lambda: _windows.discard(window))
    window.show()
    return window
