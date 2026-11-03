"""Shared document-history controls for Markdown readers and their hosts."""
from .. import pyside as qt
from ..readers.reader_chrome import READER_SPACING, reader_button


class MarkdownNavigation(qt.QWidget):
    def __init__(self, parent=None, *, up=False):
        super().__init__(parent)
        layout = qt.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(READER_SPACING)
        self.back_button = reader_button(self, 'Back', icon='previous')
        self.forward_button = reader_button(self, 'Forward', icon='next')
        self.up_button = reader_button(self, 'Up', icon='up')
        for button in (self.back_button, self.forward_button, self.up_button):
            layout.addWidget(button)
        self.up_button.setVisible(up)
        # Scope keys to the document host, even when this group moves between
        # Markdown and other document toolbars. Button clicks respect enabled
        # states and use exactly the same history owner as pointer navigation.
        self.back_shortcut = qt.QShortcut(qt.QKeySequence('Alt+Left'), parent or self)
        self.forward_shortcut = qt.QShortcut(qt.QKeySequence('Alt+Right'), parent or self)
        for shortcut, button in ((self.back_shortcut, self.back_button),
                                 (self.forward_shortcut, self.forward_button)):
            shortcut.setContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(button.click)

    def set_shortcuts_enabled(self, enabled):
        for shortcut in (self.back_shortcut, self.forward_shortcut):
            shortcut.setEnabled(enabled)
