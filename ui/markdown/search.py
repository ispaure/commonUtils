"""Scoped, transient search marks shared by reading and editing surfaces."""
from .. import pyside as qt

_SEARCH_MARK = qt.QTextFormat.Property.UserProperty + 78


class MarkdownSearchMixin:
    def _init_search_highlights(self):
        self._search_selections = {}
        self._search_timer = qt.QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(100)
        self._search_timer.timeout.connect(self._refresh_search_highlights)
        self.find_text.textChanged.connect(self._page_query_changed)
        for widget in (self.browser, self.editor, self.formatted_editor):
            widget.textChanged.connect(lambda: self._search_timer.start())
        self.pages.currentChanged.connect(lambda: self._search_timer.start())
        self.path_changed.connect(lambda: self._refresh_search_highlights())

    def _page_query_changed(self):
        self._clear_search_selection('page')
        self._refresh_search_highlights()
        if self.find_text.text():
            target = self.pages.currentWidget()
            match = target.document().find(self.find_text.text())
            if not match.isNull():
                self._select_search_match(target, match, 'page')

    def _refresh_search_highlights(self):
        if not hasattr(self, 'find_count'):
            return
        page_query = self.find_text.text() if not self.find_bar.isHidden() else ''
        library_query = self.wiki.search.text().strip() if self.wiki is not None else ''
        queries = list(dict.fromkeys(q for q in (library_query, page_query) if q))
        count = 0
        limited = False
        target = self.pages.currentWidget()
        for widget in (self.browser, self.editor, self.formatted_editor):
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
        self.find_count.setText(f'{count}{"+" if limited else ""} match' + ('' if count == 1 else 'es') if page_query else '')

    def _reveal_library_match(self):
        self._refresh_search_highlights()
        if self.wiki is None:
            return
        query = self.wiki.search.text().strip()
        if query:
            target = self.pages.currentWidget()
            match = target.document().find(query)
            if not match.isNull():
                self._select_search_match(target, match, 'library')

    def _select_search_match(self, target, cursor, scope):
        target.setTextCursor(cursor)
        target.ensureCursorVisible()
        self._search_selections[target] = (scope, cursor.position(), cursor.anchor())

    def _clear_search_selection(self, scope):
        for target, (owner, position, anchor) in list(self._search_selections.items()):
            if owner != scope:
                continue
            cursor = target.textCursor()
            if (cursor.position(), cursor.anchor()) == (position, anchor):
                cursor.clearSelection()
                target.setTextCursor(cursor)
            del self._search_selections[target]
