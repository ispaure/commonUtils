"""Two independently navigable CodeEdit views sharing one QTextDocument."""
from .. import pyside as qt
from .widget import CodeEdit


class EditorViews(qt.QWidget):
    active_changed = qt.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.splitter = qt.QSplitter()
        layout.addWidget(self.splitter)
        self.primary = CodeEdit()
        self.secondary = None
        self.active = self.primary
        self.splitter.addWidget(self.primary)
        self._connect(self.primary)

    def _connect(self, editor):
        editor.focused.connect(lambda: self.activate(editor))
        editor.read_only_changed.connect(lambda value: self._readonly(value))

    def activate(self, editor):
        if editor in (self.primary, self.secondary) and editor is not self.active:
            self.active = editor
            self.active_changed.emit()

    def _readonly(self, value):
        for editor in (self.primary, self.secondary):
            if editor is not None and editor.isReadOnly() != value:
                editor.setReadOnly(value)

    def set_split(self, orientation=None):
        if orientation is None:
            if self.secondary is not None:
                if self.active is self.secondary:
                    self.primary.setTextCursor(self.secondary.textCursor())
                    self.activate(self.primary)
                secondary, self.secondary = self.secondary, None
                secondary.setParent(None)
                secondary.deleteLater()
            self.primary.setFocus()
            return
        self.splitter.setOrientation(orientation)
        if self.secondary is None:
            source = self.active
            self.secondary = CodeEdit()
            self.secondary.setDocument(self.primary.document())
            self.primary.document().contentsChange.connect(self.secondary._external_multicursor_change)
            self.secondary.setFont(source.font())
            for name in ("indent_width", "use_tabs", "auto_indent", "auto_pairs", "line_numbers", "comment_prefix"):
                setattr(self.secondary, name, getattr(source, name))
            self.secondary.setLineWrapMode(source.lineWrapMode())
            self.secondary.setReadOnly(source.isReadOnly())
            self.secondary.update_tab_width()
            self.secondary.update_gutter()
            self.secondary.setTextCursor(source.textCursor())
            self.splitter.addWidget(self.secondary)
            self._connect(self.secondary)
        self.splitter.setSizes([1, 1])
        self.secondary.setFocus()
        self.activate(self.secondary)
