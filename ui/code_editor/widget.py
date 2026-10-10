"""Reusable QPlainTextEdit with a gutter and focused code-editing conveniences."""

from .. import pyside as qt
from ..text_commands import wrap_selection
from .transforms import TransformCommands
from .multicursor import MultiCursorCommands
from .folding import FoldingCommands


def monospace_font():
    font = qt.QFontDatabase.systemFont(qt.QFontDatabase.SystemFont.FixedFont)
    if not qt.QFontInfo(font).fixedPitch():
        available = set(qt.QFontDatabase.families())
        for family in (
            "Menlo",
            "Consolas",
            "DejaVu Sans Mono",
            "Liberation Mono",
            "Monaco",
            "Courier New",
            "Courier",
        ):
            if family in available:
                font = qt.QFont(family)
                break
    font.setStyleHint(qt.QFont.StyleHint.Monospace)
    font.setFixedPitch(True)
    return font


class LineNumbers(qt.QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return qt.QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_gutter(event)

    def mousePressEvent(self, event):
        self.editor.gutter_click(event.position().toPoint())


class CodeEdit(FoldingCommands, MultiCursorCommands, TransformCommands, qt.QPlainTextEdit):
    focused = qt.Signal()
    read_only_changed = qt.Signal(bool)
    preferences_changed = qt.Signal()
    zoom_changed = qt.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLineWrapMode(qt.QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFont(monospace_font())
        self.indent_width = 4
        self.use_tabs = False
        self.auto_indent = True
        self.auto_pairs = False
        self.line_numbers = True
        self.comment_prefix = "#"
        self.search_selections = []
        self.initialize_multicursor()
        self.gutter = LineNumbers(self)
        self.bind_folding()
        self.blockCountChanged.connect(self.update_gutter)
        self.updateRequest.connect(self._update_request)
        self.cursorPositionChanged.connect(self.highlight_cursor)
        self.textChanged.connect(self.highlight_cursor)
        self.update_gutter()
        self.highlight_cursor()
        self.update_tab_width()

    def gutter_width(self):
        return (
            28
            + self.fontMetrics().horizontalAdvance("9")
            * len(str(max(1, self.blockCount())))
            if self.line_numbers
            else 0
        )

    def update_gutter(self, *args):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)
        self.gutter.setVisible(self.line_numbers)
        self.gutter.update()

    def _update_request(self, rect, dy):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_gutter()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        area = self.contentsRect()
        self.gutter.setGeometry(
            area.left(), area.top(), self.gutter_width(), area.height()
        )

    def paint_gutter(self, event):
        painter = qt.QPainter(self.gutter)
        painter.fillRect(
            event.rect(), self.palette().brush(qt.QPalette.ColorRole.AlternateBase)
        )
        block = self.firstVisibleBlock()
        top = round(
            self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        )
        while block.isValid() and top <= event.rect().bottom():
            height = round(self.blockBoundingRect(block).height())
            if block.isVisible() and top + height >= event.rect().top():
                role = (
                    qt.QPalette.ColorRole.Text
                    if block == self.textCursor().block()
                    else qt.QPalette.ColorRole.PlaceholderText
                )
                painter.setPen(self.palette().color(role))
                self.draw_fold_marker(painter, block, top)
                painter.drawText(
                    0,
                    top,
                    self.gutter.width() - 6,
                    self.fontMetrics().height(),
                    qt.Qt.AlignmentFlag.AlignRight,
                    str(block.blockNumber() + 1),
                )
            top += height
            block = block.next()

    def highlight_cursor(self):
        selection = qt.QTextEdit.ExtraSelection()
        selection.format.setBackground(
            self.palette().color(qt.QPalette.ColorRole.AlternateBase)
        )
        selection.format.setProperty(qt.QTextFormat.Property.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self.setExtraSelections(
            [selection] + self.search_selections + self._matching_brackets() + self.multicursor_selections()
        )
        self.gutter.update()

    def _matching_brackets(self):
        cursor = self.textCursor()
        if cursor.hasSelection():
            return []
        document = self.document()
        position = cursor.position()
        pairs = {"(": ")", "[": "]", "{": "}", ")": "(", "]": "[", "}": "{"}
        for position in (position - 1, position):
            char = document.characterAt(position) if position >= 0 else ""
            if char not in pairs:
                continue
            forward = char in "([{"
            step = 1 if forward else -1
            depth = 1
            other = position + step
            budget = 10000
            while 0 <= other < document.characterCount() - 1 and budget:
                found = document.characterAt(other)
                depth += (found == char) - (found == pairs[char])
                if not depth:
                    result = []
                    for point in (position, other):
                        highlight = qt.QTextEdit.ExtraSelection()
                        highlight.cursor = qt.QTextCursor(document)
                        highlight.cursor.setPosition(point)
                        highlight.cursor.movePosition(
                            qt.QTextCursor.MoveOperation.NextCharacter,
                            qt.QTextCursor.MoveMode.KeepAnchor,
                        )
                        highlight.format.setBackground(
                            self.palette().color(qt.QPalette.ColorRole.Highlight)
                        )
                        highlight.format.setForeground(
                            self.palette().color(qt.QPalette.ColorRole.HighlightedText)
                        )
                        result.append(highlight)
                    return result
                other += step
                budget -= 1
        return []

    def update_tab_width(self):
        self.setTabStopDistance(
            self.fontMetrics().horizontalAdvance(" ") * self.indent_width
        )

    def set_font_size(self, size):
        font = self.font()
        font.setPointSizeF(max(7, min(48, size)))
        self.setFont(font)
        self.update_tab_width()
        self.update_gutter()
        self.zoom_changed.emit()

    def wheelEvent(self, event):
        if event.modifiers() & qt.Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y() or event.pixelDelta().y()
            if delta:
                self.set_font_size(self.font().pointSizeF() + (1 if delta > 0 else -1))
            event.accept()
            return
        super().wheelEvent(event)

    def changeEvent(self, event):
        super().changeEvent(event)
        if hasattr(self, "gutter") and event.type() in (
            qt.QEvent.Type.PaletteChange,
            qt.QEvent.Type.FontChange,
        ):
            self.highlight_cursor()
            self.update_gutter()
            self.update_tab_width()

    def selected_blocks(self):
        cursor = self.textCursor()
        start = self.document().findBlock(cursor.selectionStart())
        end = self.document().findBlock(cursor.selectionEnd())
        if cursor.hasSelection() and cursor.selectionEnd() == end.position():
            end = end.previous()
        blocks = []
        while start.isValid():
            blocks.append(start)
            if start == end:
                break
            start = start.next()
        return blocks

    def indent(self, backwards=False):
        if self.isReadOnly():
            return
        blocks = self.selected_blocks()
        cursor = self.textCursor()
        cursor.beginEditBlock()
        for block in reversed(blocks):
            edit = qt.QTextCursor(block)
            if backwards:
                text = block.text()
                count = (
                    1
                    if text.startswith("\t")
                    else min(self.indent_width, len(text) - len(text.lstrip(" ")))
                )
                edit.movePosition(
                    qt.QTextCursor.MoveOperation.NextCharacter,
                    qt.QTextCursor.MoveMode.KeepAnchor,
                    count,
                )
                edit.removeSelectedText()
            else:
                edit.insertText("\t" if self.use_tabs else " " * self.indent_width)
        cursor.endEditBlock()

    def toggle_comment(self):
        if self.isReadOnly():
            return
        if not self.comment_prefix:
            return
        blocks = self.selected_blocks()
        prefix = self.comment_prefix
        uncomment = all(
            not b.text().strip() or b.text().lstrip().startswith(prefix) for b in blocks
        )
        cursor = self.textCursor()
        cursor.beginEditBlock()
        for block in reversed(blocks):
            text = block.text()
            spaces = len(text) - len(text.lstrip())
            edit = qt.QTextCursor(block)
            edit.setPosition(block.position() + spaces)
            if uncomment:
                if text[spaces:].startswith(prefix):
                    count = len(prefix) + int(
                        text[spaces + len(prefix) :].startswith(" ")
                    )
                    edit.movePosition(
                        qt.QTextCursor.MoveOperation.NextCharacter,
                        qt.QTextCursor.MoveMode.KeepAnchor,
                        count,
                    )
                    edit.removeSelectedText()
            else:
                edit.insertText(prefix + " ")
        cursor.endEditBlock()

    def duplicate(self):
        if self.isReadOnly():
            return
        cursor = self.textCursor()
        cursor.beginEditBlock()
        if cursor.hasSelection():
            text = cursor.selectedText().replace("\u2029", "\n")
            cursor.setPosition(cursor.selectionEnd())
            cursor.insertText(text)
        else:
            text = cursor.block().text()
            cursor.movePosition(qt.QTextCursor.MoveOperation.EndOfBlock)
            cursor.insertText("\n" + text)
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def delete_line(self):
        if self.isReadOnly():
            return
        cursor = self.textCursor()
        cursor.beginEditBlock()
        cursor.select(qt.QTextCursor.SelectionType.LineUnderCursor)
        cursor.removeSelectedText()
        if not cursor.atEnd():
            cursor.deleteChar()
        elif cursor.position():
            cursor.deletePreviousChar()
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def move_lines(self, direction):
        if self.isReadOnly():
            return
        blocks = self.selected_blocks()
        first, last = blocks[0], blocks[-1]
        neighbor = first.previous() if direction < 0 else last.next()
        if not neighbor.isValid():
            return
        start = neighbor if direction < 0 else first
        end = last if direction < 0 else neighbor
        selected = "\n".join(b.text() for b in blocks)
        other = neighbor.text()
        replacement = (
            selected + "\n" + other if direction < 0 else other + "\n" + selected
        )
        cursor = qt.QTextCursor(self.document())
        cursor.setPosition(start.position())
        origin = cursor.position()
        cursor.setPosition(
            end.position() + end.length() - 1, qt.QTextCursor.MoveMode.KeepAnchor
        )
        cursor.beginEditBlock()
        cursor.insertText(replacement)
        cursor.endEditBlock()
        offset = 0 if direction < 0 else len(other.encode("utf-16-le")) // 2 + 1
        cursor.setPosition(origin + offset)
        cursor.setPosition(
            origin + offset + len(selected.encode("utf-16-le")) // 2,
            qt.QTextCursor.MoveMode.KeepAnchor,
        )
        self.setTextCursor(cursor)

    def keyPressEvent(self, event):
        if self.multi_key(event):
            return
        if (
            event.key() in (qt.Qt.Key.Key_Tab, qt.Qt.Key.Key_Backtab)
            and not self.isReadOnly()
        ):
            if event.key() == qt.Qt.Key.Key_Backtab or self.textCursor().hasSelection():
                self.indent(event.key() == qt.Qt.Key.Key_Backtab)
            else:
                cursor = self.textCursor()
                count = self.indent_width - cursor.positionInBlock() % self.indent_width
                cursor.insertText("\t" if self.use_tabs else " " * count)
            return
        if (
            event.key() in (qt.Qt.Key.Key_Return, qt.Qt.Key.Key_Enter)
            and self.auto_indent
            and not self.isReadOnly()
        ):
            text = self.textCursor().block().text()
            padding = text[: len(text) - len(text.lstrip())]
            cursor = self.textCursor()
            preceding = text.encode("utf-16-le")[: cursor.positionInBlock() * 2].decode(
                "utf-16-le"
            )
            if preceding.rstrip().endswith((":", "{", "[", "(")):
                padding += "\t" if self.use_tabs else " " * self.indent_width
            cursor.beginEditBlock()
            cursor.insertText("\n" + padding)
            cursor.endEditBlock()
            self.setTextCursor(cursor)
            return
        if (
            self.auto_pairs
            and not self.isReadOnly()
            and event.text() in ("(", "[", "{", '"', "'")
            and not event.modifiers()
            & (
                qt.Qt.KeyboardModifier.ControlModifier
                | qt.Qt.KeyboardModifier.AltModifier
                | qt.Qt.KeyboardModifier.MetaModifier
            )
        ):
            closing = {"(": ")", "[": "]", "{": "}", '"': '"', "'": "'"}[event.text()]
            wrap_selection(self, event.text(), closing, keep_selected=False)
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.focused.emit()

    def setReadOnly(self, value):
        super().setReadOnly(value)
        self.read_only_changed.emit(value)
