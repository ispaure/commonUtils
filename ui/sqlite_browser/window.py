"""Local SQLite inspection, staged row edits and cooperative Qt retirement."""

from collections.abc import Mapping
from html import escape
import os
from pathlib import Path

from ...integrations.sqlite import (
    CancelledError, Database, Filter, SQLiteError, Sort, ValidationError, parse_value,
)
from .. import pyside as qt
from ..appearance.status_line import StatusLine
from ..tasks.operation_progress import OperationProgress
from .values import RowEditor, typed_input, value_text


PAGE_SIZE = 100
_CANCELLED = object()
_OMITTED = object()
_OPERATORS = (
    ('Equals', 'eq'), ('Does not equal', 'ne'), ('Less than', 'lt'),
    ('At most', 'le'), ('Greater than', 'gt'), ('At least', 'ge'),
    ('Contains', 'contains'), ('Starts with', 'starts_with'),
    ('Is NULL', 'is_null'), ('Is not NULL', 'not_null'),
)
_NULL_OPERATORS = ('is_null', 'not_null')
_TEXT_OPERATORS = ('contains', 'starts_with')


def _choice(items, *, label, minimum=0):
    combo = qt.QComboBox()
    combo.setAccessibleName(label)
    combo.setSizeAdjustPolicy(qt.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(minimum)
    for text, value in items:
        combo.addItem(text, value)
    return combo


def _button(text, callback):
    button = qt.QPushButton(text)
    button.setAutoDefault(False)
    button.clicked.connect(callback)
    return button


def _select(combo, value):
    index = combo.findData(value)
    combo.setCurrentIndex(index if index >= 0 else 0)


def _check_access(check, *, writable=False):
    if check is not None and check(writable=writable) is False:
        operation = 'editing' if writable else 'inspection'
        raise PermissionError(f'The host denied SQLite {operation}.')


def _check_write_access(path, check):
    _check_access(check, writable=True)
    if not path.stat().st_mode & 0o222 or not all(
        os.access(item, os.W_OK) for item in (path, path.parent)
    ):
        raise PermissionError('The database and its folder must be writable for SQLite journals.')


def _read_page(database, table, filters, sort, offset):
    try:
        page = database.page(table, filters=filters, sort=sort, limit=PAGE_SIZE, offset=offset)
    except CancelledError:
        raise
    except SQLiteError as error:
        return None, str(error)
    return page, ''


def _same_value(before, after):
    if type(before) is not type(after):
        return False
    if isinstance(before, float):
        return before.hex() == after.hex()
    return before == after


class _Rows(qt.QAbstractTableModel):
    def __init__(self, browser):
        super().__init__(browser)
        self.browser = browser

    def rowCount(self, parent=qt.QModelIndex()):
        page = self.browser.page
        return 0 if parent.isValid() or page is None else len(page.rows) + len(self.browser._inserts)

    def columnCount(self, parent=qt.QModelIndex()):
        page = self.browser.page
        return 0 if parent.isValid() or page is None else len(page.columns)

    def _row_state(self, index):
        if index >= len(self.browser.page.rows):
            return 'Inserted'
        if index in self.browser._deletions:
            return 'Delete'
        if index in self.browser._updates:
            return 'Edited'
        return ''

    def headerData(self, section, orientation, role=qt.Qt.ItemDataRole.DisplayRole):
        page = self.browser.page
        if page is None or role != qt.Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == qt.Qt.Orientation.Horizontal:
            return page.columns[section] if 0 <= section < len(page.columns) else None
        if not 0 <= section < self.rowCount():
            return None
        state = self._row_state(section)
        if state == 'Inserted':
            return 'New'
        position = str(page.offset + section + 1)
        return f'{position} · {state}' if state else position

    def data(self, index, role=qt.Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role not in (
            qt.Qt.ItemDataRole.DisplayRole, qt.Qt.ItemDataRole.ToolTipRole,
            qt.Qt.ItemDataRole.AccessibleTextRole,
        ):
            return None
        browser = self.browser
        page = browser.page
        row, column = index.row(), index.column()
        if page is None or row >= self.rowCount() or column >= len(page.columns):
            return None
        name = page.columns[column]
        if row < len(page.rows):
            value = browser._updates.get(row, {}).get(name, page.rows[row].values[column])
        else:
            value = browser._inserts[row - len(page.rows)].get(name, _OMITTED)
        tooltip = role == qt.Qt.ItemDataRole.ToolTipRole
        text = '(default)' if value is _OMITTED else value_text(value, 500 if tooltip else 160)
        return f'<qt>{escape(text)}</qt>' if tooltip else text


class SQLiteBrowser(qt.QDialog):
    """Inspect an existing SQLite file. A host must opt in to offering edits.

    An optional access check runs on the worker before a read or write opens.
    A permission check for editing alone never opens a writable connection.
    """

    idle = qt.Signal()
    saved = qt.Signal()

    def __init__(self, path, parent=None, *, writable=False, access_check=None):
        super().__init__(parent)
        self.path = Path(path).absolute()
        self.setWindowTitle(f'SQLite — {self.path.name}')
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(940, 590)
        self._writable = writable
        self._access_check = access_check
        self._write_reason = '' if writable else 'This host permits SQLite inspection only.'
        self._write_allowed = False
        self.editing = False
        self.tables = ()
        self.table = None
        self.page = None
        self._filters = None
        self._sort = ()
        self._updates = {}
        self._inserts = []
        self._deletions = set()
        self._row_editor = None
        self._prompting = False
        self._close_vetoed = False
        self._accepting_close = False
        self._close_pending = False
        self._completion = None
        self._layout_columns = None
        self.operation = OperationProgress(self)
        self.operation.completed.connect(self._completed)
        self._build_ui()
        self.refresh()

    @property
    def busy(self):
        return self.operation.busy

    @property
    def dirty(self):
        return bool(self._updates or self._inserts or self._deletions)

    @property
    def can_retire(self):
        return not (self.dirty or self._prompting or self._row_editor is not None)

    @property
    def close_pending(self):
        return self._close_pending

    def _build_ui(self):
        layout = qt.QVBoxLayout(self)
        controls = qt.QHBoxLayout()
        self.table_selector = _choice((), label='Table or view', minimum=20)
        self.table_selector.currentIndexChanged.connect(self._table_selected)
        self.refresh_button = _button('Refresh', self.refresh)
        self.editing_button = _button('Enable editing', self.enable_editing)
        table_label = qt.QLabel('Table or view')
        table_label.setBuddy(self.table_selector)
        for widget in (table_label, self.table_selector, self.refresh_button, self.editing_button):
            controls.addWidget(widget)
        controls.addStretch()
        layout.addLayout(controls)

        self.tabs = qt.QTabWidget()
        layout.addWidget(self.tabs, 1)
        rows = qt.QWidget()
        self.tabs.addTab(rows, 'Rows')
        row_layout = qt.QVBoxLayout(rows)
        query = qt.QGridLayout()
        self.filter_column = _choice((('No filter', None),), label='Filter column', minimum=12)
        self.filter_operator = _choice(_OPERATORS, label='Filter operator', minimum=10)
        self.filter_type = _choice(tuple((name.upper(), name) for name in
                                        ('text', 'integer', 'real', 'blob')),
                                   label='Filter value type', minimum=7)
        self.filter_value = qt.QLineEdit()
        self.filter_value.setMaxLength(2 ** 31 - 1)
        self.filter_value.setAccessibleName('Filter value')
        self.filter_value.setPlaceholderText('Filter value')
        self.filter_value.returnPressed.connect(self.apply_query)
        self.sort_column = _choice((('Default order', None),), label='Sort column', minimum=12)
        self.sort_direction = _choice((('Ascending', False), ('Descending', True)),
                                      label='Sort direction', minimum=10)
        self.apply_button = _button('Apply', self.apply_query)
        for combo in (self.filter_column, self.filter_operator, self.filter_type, self.sort_column):
            combo.currentIndexChanged.connect(self._sync_query)
        query.addWidget(qt.QLabel('Filter'), 0, 0)
        for column, widget in enumerate((self.filter_column, self.filter_operator,
                                         self.filter_type, self.filter_value), 1):
            query.addWidget(widget, 0, column)
        query.addWidget(qt.QLabel('Sort'), 1, 0)
        query.addWidget(self.sort_column, 1, 1)
        query.addWidget(self.sort_direction, 1, 2)
        query.addWidget(self.apply_button, 1, 4, qt.Qt.AlignmentFlag.AlignRight)
        query.setColumnStretch(4, 1)
        row_layout.addLayout(query)

        self.rows_view = qt.QTableView()
        self._rows = _Rows(self)
        self.rows_view.setModel(self._rows)
        self.rows_view.setSelectionBehavior(qt.QAbstractItemView.SelectionBehavior.SelectRows)
        self.rows_view.setSelectionMode(qt.QAbstractItemView.SelectionMode.SingleSelection)
        self.rows_view.setWordWrap(False)
        self.rows_view.horizontalHeader().setStretchLastSection(True)
        self.rows_view.selectionModel().selectionChanged.connect(self._sync)
        row_layout.addWidget(self.rows_view, 1)
        pagination = qt.QHBoxLayout()
        self.previous_button = _button('Previous', self.previous_page)
        self.next_button = _button('Next', self.next_page)
        self.page_label = qt.QLabel()
        for widget in (self.previous_button, self.next_button, self.page_label):
            pagination.addWidget(widget)
        pagination.addStretch()
        row_layout.addLayout(pagination)

        self.schema_view = qt.QTableWidget(0, 6)
        self.schema_view.setHorizontalHeaderLabels(
            ('Column', 'Declared type', 'NOT NULL', 'Primary key order', 'Default', 'Storage'))
        self.schema_view.setEditTriggers(qt.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.schema_view.horizontalHeader().setStretchLastSection(True)
        schema = qt.QWidget()
        schema_layout = qt.QVBoxLayout(schema)
        self.schema_label = StatusLine(parent=schema)
        schema_layout.addWidget(self.schema_label)
        schema_layout.addWidget(self.schema_view, 1)
        self.tabs.addTab(schema, 'Schema')
        self.tabs.currentChanged.connect(self._sync)

        changes = qt.QHBoxLayout()
        self.edit_button = _button('Edit row…', self._edit_row)
        self.insert_button = _button('Insert row…', lambda: self._open_editor(None))
        self.delete_button = _button('Stage delete', self._delete_selected)
        self.discard_button = _button('Discard changes', self.discard)
        self.save_button = _button('Save changes', self.save)
        for widget in (self.edit_button, self.insert_button, self.delete_button):
            changes.addWidget(widget)
        changes.addStretch()
        changes.addWidget(self.discard_button)
        changes.addWidget(self.save_button)
        layout.addLayout(changes)
        self.mode = StatusLine(parent=self)
        self.status = StatusLine(parent=self)
        layout.addWidget(self.mode)
        layout.addWidget(self.status)
        layout.addWidget(self.operation)

    def _can_browse(self):
        return not (self.busy or self.dirty or self._close_pending or self._row_editor is not None)

    def _can_stage(self):
        return (self.editing and not self.busy and not self._close_pending
                and self._row_editor is None and self.page is not None and self.table.editable)

    def _selected_row(self):
        indexes = self.rows_view.selectionModel().selectedRows()
        return indexes[0].row() if indexes else -1

    def _editable_row(self, index):
        return (self._can_stage() and 0 <= index < len(self.page.rows)
                and self.page.rows[index].token is not None and index not in self._deletions)

    def _sync(self):
        browse = self._can_browse()
        self.table_selector.setEnabled(browse and bool(self.tables))
        self.refresh_button.setEnabled(browse)
        self.editing_button.setEnabled(browse and self._write_allowed and self.table is not None
                                       and self.table.editable and self.page is not None)
        self.editing_button.setText('Disable editing' if self.editing else 'Enable editing')
        self._sync_query()
        page = self.page
        self.previous_button.setEnabled(browse and page is not None and page.offset > 0)
        self.next_button.setEnabled(browse and page is not None and page.has_more)
        if page is None:
            self.page_label.clear()
        elif page.rows:
            self.page_label.setText(f'Rows {page.offset + 1:,}–{page.offset + len(page.rows):,}')
        else:
            self.page_label.setText('No rows on this page' if page.offset else 'No rows')
        rows_visible = self.tabs.currentIndex() == 0
        can_edit_row = rows_visible and self._editable_row(self._selected_row())
        self.edit_button.setEnabled(can_edit_row)
        self.delete_button.setEnabled(can_edit_row)
        self.insert_button.setEnabled(rows_visible and self._can_stage())
        self.save_button.setEnabled(self.dirty and not self.busy and not self._close_pending
                                    and self._row_editor is None)
        self.discard_button.setEnabled(self.save_button.isEnabled())
        if self.dirty:
            changes = len(self._updates) + len(self._inserts) + len(self._deletions)
            self.mode.setText(f'{changes} staged row {"change" if changes == 1 else "changes"}')
        elif self.editing:
            self.mode.setText('Editing enabled. Use Save changes to write to the database.')
        else:
            reason = self._write_reason or (self.table.read_only_reason if self.table else '')
            self.mode.setText(f'Read-only · {reason}' if reason else 'Read-only')

    def _sync_query(self):
        enabled = self._can_browse() and self.table is not None
        operator = self.filter_operator.currentData()
        has_filter = enabled and self.filter_column.currentData() is not None
        has_value = has_filter and operator not in _NULL_OPERATORS
        self.filter_column.setEnabled(enabled)
        self.filter_operator.setEnabled(has_filter)
        self.filter_type.setEnabled(has_value and operator not in _TEXT_OPERATORS)
        self.filter_value.setEnabled(has_value)
        self.sort_column.setEnabled(enabled)
        self.sort_direction.setEnabled(enabled and self.sort_column.currentData() is not None)
        self.apply_button.setEnabled(enabled)

    def _reset_rows(self, page, *, preserve_selection=False):
        selected = self._selected_row() if preserve_selection else -1
        if page is None and self.page is not None:
            self._retained_widths = (self._layout_columns, tuple(
                self.rows_view.columnWidth(index) for index in range(len(self.page.columns))))
        self._rows.beginResetModel()
        self.page = page
        self._rows.endResetModel()
        if page is not None:
            columns = self.table.name, page.columns
            if columns != self._layout_columns:
                self._layout_columns = columns
                font = self.rows_view.fontMetrics()
                heading_font = self.rows_view.horizontalHeader().fontMetrics()
                for index, name in enumerate(page.columns):
                    width = max((heading_font.horizontalAdvance(name), *(
                        font.horizontalAdvance(value_text(row.values[index]))
                        for row in page.rows[:12])))
                    self.rows_view.setColumnWidth(index, min(320, max(70, width + 22)))
            else:
                retained = getattr(self, '_retained_widths', None)
                if retained is not None and retained[0] == columns:
                    for index, width in enumerate(retained[1]):
                        self.rows_view.setColumnWidth(index, width)
            self._retained_widths = None
        if 0 <= selected < self._rows.rowCount():
            self.rows_view.selectRow(selected)
        self._sync()

    def _show_schema(self):
        table = self.table
        columns = table.columns if table is not None else ()
        self.schema_view.setRowCount(len(columns))
        if table is None:
            self.schema_label.clear()
            return
        kind = table.kind.capitalize()
        self.schema_label.setText(f'{kind} · {table.name}')
        for index, column in enumerate(columns):
            storage = {0: 'Stored', 1: 'Hidden', 2: 'Virtual generated',
                       3: 'Stored generated'}.get(column.hidden, 'Hidden')
            values = (column.name, column.declared_type or '—',
                      'Yes' if column.not_null else '—', str(column.pk_order or '—'),
                      column.default if column.default is not None else '—', storage)
            for position, value in enumerate(values):
                item = qt.QTableWidgetItem(value)
                item.setToolTip(f'<qt>{escape(value)}</qt>')
                self.schema_view.setItem(index, position, item)

    def _set_query_controls(self):
        columns = (column.name for column in self.table.columns if column.hidden != 1) if self.table else ()
        names = tuple(columns)
        for combo, label in ((self.filter_column, 'No filter'), (self.sort_column, 'Default order')):
            with qt.QSignalBlocker(combo):
                combo.clear()
                combo.addItem(label, None)
                for name in names:
                    combo.addItem(name, name)
        _select(self.filter_operator, 'eq')
        _select(self.filter_type, 'text')
        self.filter_value.clear()
        _select(self.sort_direction, False)
        if self._filters is not None:
            filter_ = self._filters
            _select(self.filter_column, filter_.column)
            _select(self.filter_operator, filter_.operator)
            if filter_.value is not None:
                kind, text = typed_input(filter_.value)
                _select(self.filter_type, kind)
                self.filter_value.setText(text)
        if self._sort:
            _select(self.sort_column, self._sort[0].column)
            _select(self.sort_direction, self._sort[0].descending)

    def _start(self, work, completed, message, *, reload_after_save=False):
        def run(_report, cancelled):
            try:
                return work(cancelled)
            except CancelledError:
                return _CANCELLED

        self._completion = completed, reload_after_save
        self.status.clear()
        self.operation.start(run, message=message)
        self._sync()

    def _completed(self, result, error):
        completed, reload_after_save = self._completion
        self._completion = None
        self.operation.hide()
        success = not error and result is not _CANCELLED
        if success and (not self._close_pending or self.dirty):
            completed(result)
        elif error:
            self.status.setText(f'Changes saved. Reload failed. {error}' if reload_after_save else error)
        elif result is _CANCELLED:
            if reload_after_save:
                self.status.setText('Changes saved. Reload cancelled.')
            else:
                self.status.setText('Cancelled. Staged changes were kept.' if self.dirty else 'Cancelled.')
        if self._close_pending:
            self._close_pending = False
            if not self.dirty:
                self.close()
            else:
                self._close_vetoed = True
        self._sync()
        if not self.busy:
            self.idle.emit()

    def refresh(self):
        if not self._can_browse():
            return
        self._refresh()

    def _refresh(self, message='Loading SQLite schema and rows…', after_save=False):
        path, check, writable = self.path, self._access_check, self._writable
        selected = self.table.name if self.table else None
        filters, sort = self._filters, self._sort
        offset = self.page.offset if self.page else 0
        # A saved page was invalidated before this job. Resume at its query's
        # first page so changed sort/filter values can move between pages.
        def work(cancelled):
            _check_access(check)
            reason = 'This host permits SQLite inspection only.'
            if writable:
                try:
                    _check_write_access(path, check)
                except Exception as error:
                    reason = str(error) or type(error).__name__
                else:
                    reason = ''
            with Database(path, cancelled=cancelled) as database:
                tables = database.tables()
                table = next((item for item in tables if item.name == selected), None)
                same_table = table is not None
                table = table or next(iter(tables), None)
                active_filter, active_sort = (filters, sort) if same_table else (None, ())
                page, page_error = None, ''
                if table is not None:
                    names = {column.name for column in table.columns if column.hidden != 1}
                    if active_filter is not None and active_filter.column not in names:
                        active_filter = None
                    active_sort = tuple(item for item in active_sort if item.column in names)
                    page, page_error = _read_page(database, table, active_filter, active_sort,
                                                  offset if same_table else 0)
                return tables, table, page, reason, page_error, active_filter, active_sort

        def finished(result):
            tables, table, page, reason, error, active_filter, active_sort = result
            self._write_reason = reason
            self._write_allowed = not reason
            self._set_table(tables, table, page, active_filter, active_sort)
            if after_save:
                self.status.setText(f'Changes saved. Reload failed. {error}' if error else 'Changes saved.')
            else:
                self.status.setText(error or ('No tables or views.' if not tables else ''))

        self._start(work, finished, message, reload_after_save=after_save)

    def _set_table(self, tables, table, page, filters, sort):
        same_table = table is not None and self.table is not None and table.name == self.table.name
        self.tables, self.table = tables, table
        self._filters, self._sort = filters, sort
        if not self._write_allowed or table is None or not table.editable:
            self.editing = False
        with qt.QSignalBlocker(self.table_selector):
            self.table_selector.clear()
            for item in tables:
                self.table_selector.addItem(item.name, item.name)
            _select(self.table_selector, table.name if table is not None else None)
        if not same_table or self.page is None or page is None or page.columns != self.page.columns:
            self._set_query_controls()
        self._show_schema()
        self._reset_rows(page)

    def _table_selected(self):
        if not self._can_browse():
            return
        name = self.table_selector.currentData()
        if name is None or (self.table is not None and name == self.table.name):
            return
        table = next(item for item in self.tables if item.name == name)
        # Leave the current selection and rows aligned while the worker loads.
        with qt.QSignalBlocker(self.table_selector):
            _select(self.table_selector, self.table.name if self.table is not None else None)
        self._load_page(table, None, (), 0, show_schema_on_error=True)

    def _load_page(self, table, filters, sort, offset, *, show_schema_on_error=False):
        if not self._can_browse():
            return
        path, check = self.path, self._access_check

        def work(cancelled):
            _check_access(check)
            with Database(path, cancelled=cancelled) as database:
                return _read_page(database, table, filters, sort, offset)

        def finished(result):
            page, error = result
            if not error or show_schema_on_error:
                self._set_table(self.tables, table, page, filters, sort)
            self.status.setText(error)

        self._start(work, finished, 'Loading rows…')

    def apply_query(self):
        if not self._can_browse() or self.table is None:
            return
        column = self.filter_column.currentData()
        operator = self.filter_operator.currentData()
        filters = None
        if column is not None:
            value = None
            if operator not in _NULL_OPERATORS:
                kind = 'text' if operator in _TEXT_OPERATORS else self.filter_type.currentData()
                try:
                    value = parse_value(kind, self.filter_value.text())
                except ValidationError as error:
                    self.status.setText(str(error))
                    return
            filters = Filter(column, operator, value)
        column = self.sort_column.currentData()
        sort = () if column is None else (Sort(column, self.sort_direction.currentData()),)
        self._load_page(self.table, filters, sort, 0)

    def next_page(self):
        if self.page is not None and self.page.has_more:
            self._load_page(self.table, self._filters, self._sort, self.page.offset + PAGE_SIZE)

    def previous_page(self):
        if self.page is not None and self.page.offset:
            self._load_page(self.table, self._filters, self._sort, max(0, self.page.offset - PAGE_SIZE))

    def enable_editing(self):
        if not self.editing_button.isEnabled():
            return
        if self.editing:
            self.editing = False
            self._sync()
            return
        path, check = self.path, self._access_check

        def work(cancelled):
            try:
                _check_write_access(path, check)
            except Exception as error:
                return str(error) or type(error).__name__
            if cancelled():
                raise CancelledError()
            return ''

        def finished(reason):
            self._write_reason = reason
            self._write_allowed = self.editing = not reason
            self.status.setText(reason)

        self._start(work, finished, 'Checking edit access…')

    def _edit_row(self):
        self._open_editor(self._selected_row())

    def _open_editor(self, index):
        if not self._can_stage() or (index is not None and not self._editable_row(index)):
            return
        values = None
        if index is not None:
            row = self.page.rows[index]
            values = dict(zip(row.columns, row.values)) | self._updates.get(index, {})
        editor = self._row_editor = RowEditor(self.table, values, self)

        def finished(result):
            self._row_editor = None
            if result == qt.QDialog.DialogCode.Accepted:
                if index is None:
                    self.stage_insert(editor.changes)
                else:
                    self.stage_update(index, editor.changes)
            self._sync()
            editor.deleteLater()

        editor.finished.connect(finished)
        editor.open()
        self._sync()

    def _fields_valid(self, values):
        names = {column.name for column in self.table.columns if not column.hidden}
        return isinstance(values, Mapping) and values.keys() <= names

    def stage_update(self, row_index, changes):
        if not self._editable_row(row_index) or not self._fields_valid(changes):
            return False
        row = self.page.rows[row_index]
        combined = self._updates.get(row_index, {}) | dict(changes)
        replacement = {}
        for name, value in combined.items():
            original = row[name]
            # SQLite may store different types or real representations for
            # values Python would otherwise compare as equal.
            if not _same_value(value, original):
                replacement[name] = value
        if replacement:
            self._updates[row_index] = replacement
        else:
            self._updates.pop(row_index, None)
        self._stage_changed()
        return True

    def stage_insert(self, values):
        if not self._can_stage() or not self._fields_valid(values):
            return False
        self._inserts.append(dict(values))
        self._stage_changed()
        return True

    def _delete_selected(self):
        self.stage_delete(self._selected_row())

    def stage_delete(self, row_index):
        if not self._editable_row(row_index):
            return False
        self._updates.pop(row_index, None)
        self._deletions.add(row_index)
        self._stage_changed()
        return True

    def _stage_changed(self):
        self.status.clear()
        self._reset_rows(self.page, preserve_selection=True)

    def _clear_staging(self):
        self._updates.clear()
        self._inserts.clear()
        self._deletions.clear()

    def discard(self):
        if self.busy or self._row_editor is not None:
            return
        self._clear_staging()
        self._stage_changed()
        self.status.setText('Staged changes discarded.')

    def save(self):
        if not self.dirty or self.busy or self._row_editor is not None:
            return
        path, check, table = self.path, self._access_check, self.table
        deletes = tuple(self.page.rows[index].token for index in sorted(self._deletions))
        updates = tuple((self.page.rows[index].token, values.copy()) for index, values in self._updates.items())
        inserts = tuple(values.copy() for values in self._inserts)

        def work(cancelled):
            _check_write_access(path, check)
            with Database(path, writable=True, cancelled=cancelled) as database:
                with database.transaction() as transaction:
                    for token in deletes:
                        transaction.delete(token)
                    for token, changes in updates:
                        transaction.update(token, changes)
                    for values in inserts:
                        transaction.insert(table, values, schema_token=table.schema_token)

        def finished(_result):
            self._clear_staging()
            self._reset_rows(None)
            self.status.setText('Changes saved.')
            self.saved.emit()
            if not self._close_pending:
                self._refresh(message='Changes saved. Reloading rows…', after_save=True)

        self._start(work, finished, 'Saving SQLite changes…')

    def prepare_close(self):
        if self._prompting or self._row_editor is not None:
            return False
        if self._close_pending:
            return not self.busy and not self.dirty
        if self.busy:
            self._close_pending = not self.dirty
            self._close_vetoed = self.dirty
            self.operation.request_cancel()
            return False
        if not self.dirty:
            return True
        if self._close_vetoed:
            return False
        choices = qt.QMessageBox.StandardButton
        self._prompting = True
        try:
            answer = qt.QMessageBox.question(
                self, 'Unsaved SQLite changes', 'Save the staged changes before closing?',
                choices.Save | choices.Discard | choices.Cancel, choices.Cancel)
        finally:
            self._prompting = False
        if answer == choices.Discard:
            self._clear_staging()
            return True
        if answer == choices.Save:
            self._close_pending = True
            self.save()
        else:
            self._close_vetoed = True
        return False

    def closeEvent(self, event):
        if not self._close_pending and not self._prompting:
            self._close_vetoed = False
        if not self.prepare_close():
            event.ignore()
            return
        self._accepting_close = True
        try:
            super().closeEvent(event)
        finally:
            self._accepting_close = False

    def reject(self):
        if self._accepting_close:
            super().reject()
        else:
            self.close()
