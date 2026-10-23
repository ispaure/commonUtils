"""Markdown table actions using Qt's existing document and undo stack."""
from .. import pyside as qt
from ..appearance.icons import set_painted_icon
from ..appearance.formatting_icons import FormattingIcon
from .presentation import style_table
from collections.abc import Callable


class TableEditing:
    """Own table actions using only an editor, menu and explicit UI callbacks."""
    def __init__(self, parent: qt.QWidget, editor: qt.QTextEdit, format_menu: qt.QMenu,
                 *, action: Callable[..., qt.QAction], enabled: Callable[[], bool]):
        self.parent = parent
        self.editor = editor
        self.format_menu = format_menu
        self.action = action
        self.enabled = enabled
        self._build()

    def _build(self):
        self.button = qt.QToolButton()
        self.button.setText('Table')
        self.button.setPopupMode(qt.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu = qt.QMenu(self.button)
        self.button.setMenu(self.menu)
        self.insert_action = self.action('Insert table…', self.insert_dialog)
        set_painted_icon(self.insert_action, FormattingIcon, 'table')
        self.menu.addAction(self.insert_action)
        self.menu.addSeparator()
        self.actions = {}
        for key, title in (('row_above', 'Add row above'), ('row_below', 'Add row below'),
                           ('column_before', 'Add column before'), ('column_after', 'Add column after'),
                           ('delete_row', 'Delete row'), ('delete_column', 'Delete column'),
                           ('delete_table', 'Delete table')):
            action = self.action(title, lambda key=key: self.edit(key))
            glyph = ('row_add' if key.startswith('row_') else 'column_add' if key.startswith('column_')
                     else {'delete_row': 'row_delete', 'delete_column': 'column_delete', 'delete_table': 'table_delete'}[key])
            set_painted_icon(action, FormattingIcon, glyph)
            self.actions[key] = action
            self.menu.addAction(action)
        self.button.setParent(self.parent)
        self.button.hide()
        self.menu.setTitle('Table')
        set_painted_icon(self.menu.menuAction(), FormattingIcon, 'table')
        self.format_menu.addMenu(self.menu)
        self.editor.table_actions = (self.insert_action, *self.actions.values())
        self.editor.cursorPositionChanged.connect(self.update)
        self.editor.selectionChanged.connect(self.update)
        self.editor.textChanged.connect(self.update)
        self.update()

    def update(self):
        enabled = self.enabled()
        cursor = self.editor.textCursor()
        # Rectangular selections are ambiguous; require a caret in one cell.
        in_table = enabled and cursor.currentTable() is not None and not cursor.hasSelection()
        self.button.setEnabled(enabled)
        self.menu.menuAction().setEnabled(enabled)
        self.insert_action.setEnabled(enabled and cursor.currentTable() is None)
        for action in self.actions.values():
            action.setEnabled(in_table)

    def insert_dialog(self):
        self.update()
        if not self.insert_action.isEnabled():
            return False
        rows, accepted = qt.QInputDialog.getInt(self.parent, 'Insert table', 'Rows (including header):', 3, 1, 100)
        if not accepted:
            return False
        columns, accepted = qt.QInputDialog.getInt(self.parent, 'Insert table', 'Columns:', 2, 1, 100)
        if not accepted:
            return False
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        fmt = qt.QTextTableFormat()
        fmt.setHeaderRowCount(1)
        fmt.setCellPadding(4)
        table = cursor.insertTable(rows, columns, fmt)
        style_table(table, self.editor.palette())
        cursor.endEditBlock()
        self.editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
        self.editor.setFocus()
        return True

    def edit(self, operation):
        self.update()
        action = self.actions.get(operation)
        if action is None or not action.isEnabled():
            return False
        cursor = self.editor.textCursor()
        table = cursor.currentTable()
        cell = table.cellAt(cursor)
        row, column = cell.row(), cell.column()
        start = table.firstPosition()
        cursor.beginEditBlock()
        remove = operation == 'delete_table' or (operation == 'delete_row' and table.rows() == 1) or (
            operation == 'delete_column' and table.columns() == 1)
        if remove:
            table.removeRows(0, table.rows())
        elif operation == 'row_above':
            table.insertRows(row, 1)
        elif operation == 'row_below':
            table.insertRows(row + 1, 1)
            row += 1
        elif operation == 'column_before':
            table.insertColumns(column, 1)
        elif operation == 'column_after':
            table.insertColumns(column + 1, 1)
            column += 1
        elif operation == 'delete_row':
            table.removeRows(row, 1)
            row = min(row, table.rows() - 1)
        elif operation == 'delete_column':
            table.removeColumns(column, 1)
            column = min(column, table.columns() - 1)
        if not remove:
            style_table(table, self.editor.palette())
        cursor.endEditBlock()
        if remove:
            cursor = qt.QTextCursor(self.editor.document())
            cursor.setPosition(min(start, self.editor.document().characterCount() - 1))
        else:
            cursor = table.cellAt(row, column).firstCursorPosition()
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()
        self.update()
        return True
