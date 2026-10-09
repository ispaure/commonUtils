"""Same-pane Markdown syntax, paired selections and cursor-sensitive preview."""
from .. import pyside as qt
from .syntax import _units
from .links import link_spans
from .document import LiveMarkdownDocument, materialize_formats, protect_escapes, restore_escapes
from .preview import LivePreviewHighlighter
from .syntax import HEADING, fenced_regions


class SourceMarkdownEdit(qt.QPlainTextEdit):
    """Source editor with paired delimiters around the current selection."""
    def keyPressEvent(self, event):
        cursor = self.textCursor()
        if (not self.isReadOnly() and cursor.hasSelection() and event.text() in ('*', '_', '`')
                and not event.modifiers() & (qt.Qt.KeyboardModifier.ControlModifier |
                                            qt.Qt.KeyboardModifier.MetaModifier |
                                            qt.Qt.KeyboardModifier.AltModifier)):
            marker = event.text()
            start = cursor.selectionStart()
            text = cursor.selectedText().replace('\u2029', '\n')
            cursor.beginEditBlock()
            cursor.insertText(marker + text + marker)
            cursor.setPosition(start + 1)
            cursor.setPosition(start + 1 + _units(text), qt.QTextCursor.MoveMode.KeepAnchor)
            cursor.endEditBlock()
            self.setTextCursor(cursor)
            event.accept()
            return
        super().keyPressEvent(event)


class FormattedMarkdownEdit(qt.QTextEdit):
    linkActivated = qt.Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._live_document = LiveMarkdownDocument(self)
        self.setDocument(self._live_document)
        self._highlighter = LivePreviewHighlighter(self)
        self._wrapped_selection = None
        self.table_actions = ()
        self.cursorPositionChanged.connect(self._highlighter.refresh_cursor)
        self.selectionChanged.connect(self._highlighter.refresh_cursor)

    def setMarkdown(self, markdown):
        self._highlighter.setDocument(None)
        protected, tokens = protect_escapes(markdown)
        self.document().setMarkdown(protected,
            qt.QTextDocument.MarkdownFeature.MarkdownDialectGitHub | qt.QTextDocument.MarkdownFeature.MarkdownNoHTML)
        materialize_formats(self)
        restore_escapes(self.document(), tokens)
        self.document().clearUndoRedoStacks()
        self.document().setModified(False)
        self._highlighter.setDocument(self.document())
        self._highlighter.refresh_cursor()

    def _wrap_selection(self, marker):
        cursor = self.textCursor()
        start = cursor.selectionStart()
        text = cursor.selectedText().replace('\u2029', '\n')
        cursor.beginEditBlock()
        cursor.insertText(marker + text + marker, qt.QTextCharFormat())
        cursor.setPosition(start + len(marker))
        cursor.setPosition(start + len(marker) + _units(text), qt.QTextCursor.MoveMode.KeepAnchor)
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def apply_inline_format(self, marker):
        cursor = self.textCursor()
        if cursor.hasSelection():
            text = cursor.selectedText()
            if text.startswith(marker) and text.endswith(marker) and len(text) > 2 * len(marker):
                start = cursor.selectionStart()
                cursor.beginEditBlock()
                cursor.insertText(text[len(marker):-len(marker)], qt.QTextCharFormat())
                cursor.setPosition(start)
                cursor.setPosition(start + _units(text[len(marker):-len(marker)]), qt.QTextCursor.MoveMode.KeepAnchor)
                cursor.endEditBlock()
                self.setTextCursor(cursor)
            else:
                self._wrap_selection(marker)
        else:
            cursor.beginEditBlock()
            start = cursor.position()
            cursor.insertText(marker + 'text' + marker, qt.QTextCharFormat())
            cursor.setPosition(start + len(marker))
            cursor.setPosition(start + len(marker) + 4, qt.QTextCursor.MoveMode.KeepAnchor)
            cursor.endEditBlock()
            self.setTextCursor(cursor)

    def keyPressEvent(self, event):
        if self.isReadOnly():
            return super().keyPressEvent(event)
        cursor = self.textCursor()
        plain = not event.modifiers() & (qt.Qt.KeyboardModifier.ControlModifier |
                                         qt.Qt.KeyboardModifier.MetaModifier |
                                         qt.Qt.KeyboardModifier.AltModifier)
        if plain and cursor.hasSelection() and event.text() in ('*', '_', '`'):
            self._wrap_selection(event.text())
            event.accept()
            return
        if not plain or event.key() in (qt.Qt.Key.Key_Left, qt.Qt.Key.Key_Right,
                                      qt.Qt.Key.Key_Up, qt.Qt.Key.Key_Down):
            return super().keyPressEvent(event)
        cursor.beginEditBlock()
        super().keyPressEvent(event)
        self._render_typed_markup()
        cursor.endEditBlock()

    def insertFromMimeData(self, source):
        if self.isReadOnly():
            return
        cursor = self.textCursor()
        cursor.beginEditBlock()
        super().insertFromMimeData(source)
        self._render_typed_markup()
        cursor.endEditBlock()

    def inputMethodEvent(self, event):
        cursor = self.textCursor()
        cursor.beginEditBlock()
        super().inputMethodEvent(event)
        if event.commitString() and not self.isReadOnly():
            self._render_typed_markup()
        cursor.endEditBlock()

    def _render_typed_markup(self, start=None):
        cursor = self.textCursor()
        block = cursor.block()
        in_code = any(opening.position() <= block.position() <= (closing.position() if closing else self.document().characterCount())
                      for opening, closing, _, _ in fenced_regions(self.document()))
        heading = HEADING.match(block.text()) if not in_code else None
        level = len(heading.group(1)) if heading else 0
        fmt = block.blockFormat()
        if fmt.headingLevel() != level:
            fmt.setHeadingLevel(level)
            cursor.setBlockFormat(fmt)
            chars = qt.QTextCharFormat()
            chars.setFontWeight(qt.QFont.Weight.Bold if level else qt.QFont.Weight.Normal)
            size = self.font().pointSizeF()
            chars.setFontPointSize((size if size > 0 else 12) * ((1.9, 1.6, 1.35, 1.2, 1.1, 1)[level - 1] if level else 1))
            if block.text():
                format_cursor = qt.QTextCursor(block)
                format_cursor.select(qt.QTextCursor.SelectionType.BlockUnderCursor)
                format_cursor.mergeCharFormat(chars)
            self.setCurrentCharFormat(chars)
        self._highlighter.refresh_cursor()

    def mousePressEvent(self, event):
        if (event.button() == qt.Qt.MouseButton.LeftButton and event.modifiers() &
                (qt.Qt.KeyboardModifier.ControlModifier | qt.Qt.KeyboardModifier.MetaModifier)):
            cursor = self.cursorForPosition(event.position().toPoint())
            block = cursor.block()
            in_code = any(first.position() <= block.position() <=
                          (last.position() if last else self.document().characterCount())
                          for first, last, _, _ in fenced_regions(self.document()))
            if not in_code:
                offset = cursor.positionInBlock()
                for span in link_spans(block.text()):
                    if _units(block.text()[:span.start]) <= offset < _units(block.text()[:span.end]):
                        self.linkActivated.emit(qt.QUrl(span.target))
                        event.accept()
                        return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        if not self.isReadOnly() and not self.textCursor().hasSelection():
            self.setTextCursor(self.cursorForPosition(event.pos()))
        menu = self.createStandardContextMenu()
        if not self.isReadOnly() and self.table_actions:
            menu.addSeparator()
            for action in self.table_actions:
                menu.addAction(action)
        menu.exec(event.globalPos())
        menu.deleteLater()
