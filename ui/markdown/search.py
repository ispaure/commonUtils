"""Scoped, transient search marks shared by reading and editing surfaces."""
from .. import pyside as qt
from collections.abc import Callable, Sequence

_SEARCH_MARK = qt.QTextFormat.Property.UserProperty + 78


class SearchHighlights:
    """Own scoped marks and their timer; receive surfaces and controls explicitly."""
    def __init__(self, parent: qt.QWidget, widgets: Sequence[qt.QTextEdit | qt.QPlainTextEdit],
                 pages: qt.QStackedWidget, query: qt.QLineEdit, bar: qt.QWidget, count: qt.QLabel,
                 *, library_query: Callable[[], str], path_changed):
        self.widgets = tuple(widgets)
        self.pages = pages
        self.query = query
        self.bar = bar
        self.count = count
        self.library_query = library_query
        self.parent = parent
        self._connect()
        path_changed.connect(lambda: self.refresh())

    def _connect(self):
        self.selections = {}
        self.timer = qt.QTimer(self.parent)
        self.timer.setSingleShot(True)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.refresh)
        self.query.textChanged.connect(self.query_changed)
        for widget in self.widgets:
            widget.textChanged.connect(lambda: self.timer.start())
        self.pages.currentChanged.connect(lambda: self.timer.start())

    def query_changed(self):
        self.clear_selection('page')
        self.refresh()
        if self.query.text():
            target = self.pages.currentWidget()
            match = target.document().find(self.query.text())
            if not match.isNull():
                self.select(target, match, 'page')

    def refresh(self):
        page_query = self.query.text() if not self.bar.isHidden() else ''
        library_query = self.library_query()
        queries = list(dict.fromkeys(q for q in (library_query, page_query) if q))
        count = 0
        limited = False
        target = self.pages.currentWidget()
        for widget in self.widgets:
            marks = [entry for entry in widget.extraSelections()
                     if not entry.format.property(_SEARCH_MARK)]
            if widget is target:
                for query in queries:
                    cursor = qt.QTextCursor(widget.document())
                    matches = 0
                    while matches < 5000:
                        cursor = widget.document().find(query, cursor)
                        if cursor.isNull():
                            break
                        selection = qt.QTextEdit.ExtraSelection()
                        selection.cursor = cursor
                        color = widget.palette().color(qt.QPalette.ColorRole.Highlight)
                        color.setAlpha(95 if query == page_query else 55)
                        selection.format.setBackground(color)
                        selection.format.setProperty(_SEARCH_MARK, True)
                        marks.append(selection)
                        matches += 1
                    if query == page_query:
                        count = matches
                        limited = matches == 5000
            widget.setExtraSelections(marks)
        self.count.setText(f'{count}{"+" if limited else ""} match' + ('' if count == 1 else 'es') if page_query else '')

    def reveal_library_match(self):
        self.refresh()
        query = self.library_query()
        if query:
            target = self.pages.currentWidget()
            match = target.document().find(query)
            if not match.isNull():
                self.select(target, match, 'library')

    def select(self, target, cursor, scope):
        target.setTextCursor(cursor)
        target.ensureCursorVisible()
        self.selections[target] = (scope, cursor.position(), cursor.anchor())

    def clear_selection(self, scope):
        for target, (owner, position, anchor) in list(self.selections.items()):
            if owner != scope:
                continue
            cursor = target.textCursor()
            if (cursor.position(), cursor.anchor()) == (position, anchor):
                cursor.clearSelection()
                target.setTextCursor(cursor)
            del self.selections[target]
