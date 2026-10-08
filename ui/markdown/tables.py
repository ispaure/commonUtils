"""Markdown table actions using Qt's existing document and undo stack."""
from .. import pyside as qt


class MarkdownTablesMixin:
    def _build_table_actions(self):
        self.table_button = qt.QToolButton()
        self.table_button.setText('Table')
        self.table_button.setPopupMode(qt.QToolButton.ToolButtonPopupMode.InstantPopup)
        self._table_menu = qt.QMenu(self.table_button)
        self.table_button.setMenu(self._table_menu)
        self.table_insert_action = self._action('Insert table…', self._insert_table_dialog)
        self._table_menu.addAction(self.table_insert_action)
        self._table_menu.addSeparator()
        self._table_actions = {}
        for key, title in (('row_above', 'Add row above'), ('row_below', 'Add row below'),
                           ('column_before', 'Add column before'), ('column_after', 'Add column after'),
                           ('delete_row', 'Delete row'), ('delete_column', 'Delete column'),
                           ('delete_table', 'Delete table')):
            action = self._action(title, lambda key=key: self._edit_table(key))
            self._table_actions[key] = action
            self._table_menu.addAction(action)
        self.editor_toolbar.addWidget(self.table_button)
        self.formatted_editor.table_actions = (self.table_insert_action, *self._table_actions.values())
        self.formatted_editor.cursorPositionChanged.connect(self._update_table_actions)
        self.formatted_editor.selectionChanged.connect(self._update_table_actions)
        self.formatted_editor.textChanged.connect(self._update_table_actions)
        self._update_table_actions()

    def _update_table_actions(self):
        if not hasattr(self, '_table_actions'):
            return
        enabled = self.allow_edit and self.edit_button.isChecked() and self.active_editor() is self.formatted_editor
        cursor = self.formatted_editor.textCursor()
        # Rectangular selections are ambiguous; require a caret in one cell.
        in_table = enabled and cursor.currentTable() is not None and not cursor.hasSelection()
        self.table_button.setEnabled(enabled)
        self.table_insert_action.setEnabled(enabled and cursor.currentTable() is None)
        for action in self._table_actions.values():
            action.setEnabled(in_table)

    def _insert_table_dialog(self):
        self._update_table_actions()
        if not self.table_insert_action.isEnabled():
            return False
        rows, accepted = qt.QInputDialog.getInt(self, 'Insert table', 'Rows (including header):', 3, 1, 100)
        if not accepted:
            return False
        columns, accepted = qt.QInputDialog.getInt(self, 'Insert table', 'Columns:', 2, 1, 100)
        if not accepted:
            return False
        cursor = self.formatted_editor.textCursor()
        cursor.beginEditBlock()
        fmt = qt.QTextTableFormat()
        fmt.setHeaderRowCount(1)
        fmt.setCellPadding(4)
        table = cursor.insertTable(rows, columns, fmt)
        cursor.endEditBlock()
        self.formatted_editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
        self.formatted_editor.setFocus()
        return True

    def _edit_table(self, operation):
        self._update_table_actions()
        action = self._table_actions.get(operation)
        if action is None or not action.isEnabled():
            return False
        cursor = self.formatted_editor.textCursor()
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
            fmt = table.format()
            fmt.setHeaderRowCount(1)
            table.setFormat(fmt)
        cursor.endEditBlock()
        if remove:
            cursor = qt.QTextCursor(self.formatted_editor.document())
            cursor.setPosition(min(start, self.formatted_editor.document().characterCount() - 1))
        else:
            cursor = table.cellAt(row, column).firstCursorPosition()
        self.formatted_editor.setTextCursor(cursor)
        self.formatted_editor.setFocus()
        self._update_table_actions()
        return True
