"""Shared native-style filename editors for lists, tiles and folder columns."""

from ...dirUtils import Directory
from .. import pyside as qt


class FilenameEditorMixin:
    def createEditor(self, parent, option, index):
        return super().createEditor(parent, option, index) if index.column() == 0 else None

    def setEditorData(self, editor, index):
        super().setEditorData(editor, index)
        source = index
        while isinstance(source.model(), qt.QAbstractProxyModel):
            source = source.model().mapToSource(source)
        if isinstance(editor, qt.QLineEdit):
            item = source.model().item(source)
            suffix = '' if isinstance(item, Directory) else item.path.suffix
            basename = editor.text()[:-len(suffix)] if suffix else editor.text()
            # QLineEdit positions use UTF-16 units, including two units per emoji.
            length = len(basename.encode('utf-16-le')) // 2
            editor.setSelection(0, length)
            # The view selects all text when it focuses its new editor; restore
            # basename selection after that native setup has completed.
            qt.QTimer.singleShot(0, editor, lambda: editor.setSelection(0, length))


class FilenameDelegate(FilenameEditorMixin, qt.QStyledItemDelegate):
    pass
