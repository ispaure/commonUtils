"""Bounded multi-cursor editing with Qt-owned UTF-16 positions and grouped undo."""
from .. import pyside as qt

MAX_CURSORS = 1000


class MultiCursorCommands:
    def initialize_multicursor(self):
        self.extra_cursors = []
        self._multi_editing = False
        self._rectangle_anchor = None
        self.document().contentsChange.connect(self._external_multicursor_change)

    def _external_multicursor_change(self, *args):
        if not self._multi_editing:
            self.extra_cursors = []
            self.viewport().update()

    def clear_extra_cursors(self):
        self.extra_cursors = []
        if hasattr(self, "gutter"):
            self.highlight_cursor()
        self.viewport().update()

    def set_cursors(self, cursors):
        ordered = sorted((qt.QTextCursor(cursor) for cursor in cursors),
                         key=lambda cursor: (cursor.selectionStart(), cursor.selectionEnd()))
        accepted = []
        for cursor in ordered:
            if accepted and (cursor.selectionStart(), cursor.selectionEnd()) == (accepted[-1].selectionStart(), accepted[-1].selectionEnd()):
                continue
            if accepted and cursor.selectionStart() < accepted[-1].selectionEnd():
                previous = accepted[-1]
                start = previous.selectionStart()
                end = max(previous.selectionEnd(), cursor.selectionEnd())
                previous.setPosition(start)
                previous.setPosition(end, qt.QTextCursor.MoveMode.KeepAnchor)
                continue
            accepted.append(cursor)
            if len(accepted) == MAX_CURSORS:
                break
        if accepted:
            self.setTextCursor(accepted[0])
            self.extra_cursors = accepted[1:]
        else:
            self.extra_cursors = []
        self.highlight_cursor()
        self.viewport().update()

    def add_next_occurrence(self):
        cursor = self.textCursor()
        if not cursor.hasSelection():
            cursor.select(qt.QTextCursor.SelectionType.WordUnderCursor)
            self.setTextCursor(cursor)
        word = cursor.selectedText()
        if not word or "\u2029" in word or len(self.extra_cursors) >= MAX_CURSORS - 1:
            return
        cursors = [cursor] + self.extra_cursors
        occupied = {(c.selectionStart(), c.selectionEnd()) for c in cursors}
        start = max(c.selectionEnd() for c in cursors)
        for origin in (start, 0):
            match = self.document().find(word, origin)
            budget = MAX_CURSORS
            while not match.isNull() and budget:
                if (match.selectionStart(), match.selectionEnd()) not in occupied:
                    self.set_cursors(cursors + [match])
                    return
                match = self.document().find(word, match.selectionEnd())
                budget -= 1

    def rectangular_selection(self, anchor=None, end=None):
        anchor = anchor if anchor is not None else self.textCursor()
        end = end if end is not None else anchor
        first, last = sorted((self.document().findBlock(anchor.anchor()).blockNumber(), end.blockNumber()))
        # Convert UTF-16 cursor columns to Unicode character columns.
        def column(cursor, start=False):
            position = cursor.anchor() if start else cursor.position()
            block = self.document().findBlock(position)
            return len(block.text().encode("utf-16-le")[:(position - block.position()) * 2].decode("utf-16-le"))
        left, right = sorted((column(anchor, True), column(end)))
        if anchor is end:
            first = self.document().findBlock(anchor.selectionStart()).blockNumber()
            last = self.document().findBlock(anchor.selectionEnd()).blockNumber()
        cursors = []
        for line in range(first, min(last + 1, first + MAX_CURSORS)):
            block = self.document().findBlockByNumber(line)
            text = block.text()
            cursor = qt.QTextCursor(block)
            cursor.setPosition(block.position() + len(text[:left].encode("utf-16-le")) // 2)
            cursor.setPosition(block.position() + len(text[:right].encode("utf-16-le")) // 2,
                               qt.QTextCursor.MoveMode.KeepAnchor)
            cursors.append(cursor)
        self.set_cursors(cursors)

    def multicursor_selections(self):
        result = []
        for cursor in self.extra_cursors:
            if cursor.hasSelection():
                selection = qt.QTextEdit.ExtraSelection()
                selection.cursor = cursor
                selection.format.setBackground(self.palette().brush(qt.QPalette.ColorRole.Highlight))
                selection.format.setForeground(self.palette().brush(qt.QPalette.ColorRole.HighlightedText))
                result.append(selection)
        return result

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.extra_cursors and self.hasFocus():
            painter = qt.QPainter(self.viewport())
            painter.setPen(self.palette().color(qt.QPalette.ColorRole.Text))
            for cursor in self.extra_cursors:
                rect = self.cursorRect(cursor)
                painter.drawLine(rect.topLeft(), rect.bottomLeft())

    def mousePressEvent(self, event):
        if event.button() == qt.Qt.MouseButton.LeftButton and event.modifiers() & qt.Qt.KeyboardModifier.AltModifier:
            cursor = self.cursorForPosition(event.position().toPoint())
            if event.modifiers() & qt.Qt.KeyboardModifier.ShiftModifier:
                self._rectangle_anchor = cursor
                self.set_cursors([cursor])
            else:
                self.set_cursors([self.textCursor()] + self.extra_cursors + [cursor])
            self.setFocus()
            event.accept()
            return
        self.clear_extra_cursors()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._rectangle_anchor is not None:
            self.rectangular_selection(self._rectangle_anchor, self.cursorForPosition(event.position().toPoint()))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._rectangle_anchor is not None:
            self._rectangle_anchor = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def multi_edit(self, operation, values=None):
        if self.isReadOnly():
            return
        cursors = [qt.QTextCursor(self.textCursor())] + [qt.QTextCursor(c) for c in self.extra_cursors]
        if operation in ("backspace", "delete"):
            for cursor in cursors:
                if not cursor.hasSelection():
                    cursor.movePosition(qt.QTextCursor.MoveOperation.PreviousCharacter if operation == "backspace"
                                        else qt.QTextCursor.MoveOperation.NextCharacter, qt.QTextCursor.MoveMode.KeepAnchor)
            # Expanding deletion ranges can overlap; deduplicate before mutating.
            self.set_cursors(cursors)
            cursors = [self.textCursor()] + self.extra_cursors
        self._multi_editing = True
        group = qt.QTextCursor(self.document())
        group.beginEditBlock()
        try:
            for index in sorted(range(len(cursors)), key=lambda i: cursors[i].selectionStart(), reverse=True):
                cursor = cursors[index]
                if operation in ("backspace", "delete", "cut"):
                    cursor.removeSelectedText()
                elif operation == "insert":
                    cursor.insertText(values[index] if isinstance(values, list) else values)
                elif operation == "pair":
                    closing = {"(": ")", "[": "]", "{": "}", '"': '"', "'": "'"}[values]
                    selected = cursor.selectedText().replace("\u2029", "\n")
                    cursor.insertText(values + selected + closing)
                    cursor.movePosition(qt.QTextCursor.MoveOperation.PreviousCharacter)
                elif operation == "tab":
                    count = self.indent_width - cursor.positionInBlock() % self.indent_width
                    cursor.insertText("\t" if self.use_tabs else " " * count)
                elif operation == "newline":
                    text = cursor.block().text()
                    padding = text[:len(text) - len(text.lstrip())] if self.auto_indent else ""
                    preceding = text.encode("utf-16-le")[:cursor.positionInBlock() * 2].decode("utf-16-le")
                    if self.auto_indent and preceding.rstrip().endswith((":", "{", "[", "(")):
                        padding += "\t" if self.use_tabs else " " * self.indent_width
                    cursor.insertText("\n" + padding)
        finally:
            group.endEditBlock()
            self._multi_editing = False
        self.set_cursors(cursors)

    def multi_key(self, event):
        if not self.extra_cursors:
            return False
        key, modifiers = event.key(), event.modifiers()
        if key in (qt.Qt.Key.Key_Control, qt.Qt.Key.Key_Meta, qt.Qt.Key.Key_Shift, qt.Qt.Key.Key_Alt):
            return False
        for standard, callback in ((qt.QKeySequence.StandardKey.Copy, self.copy),
                                   (qt.QKeySequence.StandardKey.Cut, self.cut),
                                   (qt.QKeySequence.StandardKey.Paste, self.paste)):
            if event.matches(standard):
                callback()
                return True
        if key == qt.Qt.Key.Key_Escape:
            self.clear_extra_cursors()
            return True
        if event.matches(qt.QKeySequence.StandardKey.Undo) or event.matches(qt.QKeySequence.StandardKey.Redo):
            self.clear_extra_cursors()
            return False
        movements = {qt.Qt.Key.Key_Left: qt.QTextCursor.MoveOperation.PreviousCharacter,
                     qt.Qt.Key.Key_Right: qt.QTextCursor.MoveOperation.NextCharacter,
                     qt.Qt.Key.Key_Up: qt.QTextCursor.MoveOperation.Up,
                     qt.Qt.Key.Key_Down: qt.QTextCursor.MoveOperation.Down,
                     qt.Qt.Key.Key_Home: qt.QTextCursor.MoveOperation.StartOfBlock,
                     qt.Qt.Key.Key_End: qt.QTextCursor.MoveOperation.EndOfBlock}
        if key in movements and not modifiers & (qt.Qt.KeyboardModifier.ControlModifier | qt.Qt.KeyboardModifier.MetaModifier):
            cursors = [self.textCursor()] + self.extra_cursors
            for cursor in cursors:
                cursor.movePosition(movements[key], qt.QTextCursor.MoveMode.KeepAnchor
                                    if modifiers & qt.Qt.KeyboardModifier.ShiftModifier else qt.QTextCursor.MoveMode.MoveAnchor)
            self.set_cursors(cursors)
            return True
        if self.isReadOnly():
            return key in (qt.Qt.Key.Key_Backspace, qt.Qt.Key.Key_Delete, qt.Qt.Key.Key_Return,
                           qt.Qt.Key.Key_Enter, qt.Qt.Key.Key_Tab) or bool(event.text())
        if key in (qt.Qt.Key.Key_Backspace, qt.Qt.Key.Key_Delete):
            self.multi_edit("backspace" if key == qt.Qt.Key.Key_Backspace else "delete")
        elif key in (qt.Qt.Key.Key_Return, qt.Qt.Key.Key_Enter):
            self.multi_edit("newline")
        elif key == qt.Qt.Key.Key_Tab:
            self.multi_edit("tab")
        elif event.text() and not modifiers & (qt.Qt.KeyboardModifier.ControlModifier | qt.Qt.KeyboardModifier.MetaModifier):
            self.multi_edit("pair" if self.auto_pairs and event.text() in ("(", "[", "{", '"', "'") else "insert", event.text())
        else:
            self.clear_extra_cursors()
            return False
        return True

    def insertFromMimeData(self, source):
        if self.extra_cursors and source.hasText():
            text = source.text().replace("\r\n", "\n").replace("\r", "\n")
            lines = text.split("\n")
            values = lines if len(lines) == len(self.extra_cursors) + 1 else text
            self.multi_edit("insert", values)
        else:
            super().insertFromMimeData(source)

    def copy(self):
        if self.extra_cursors:
            qt.QApplication.clipboard().setText("\n".join(c.selectedText().replace("\u2029", "\n")
                for c in [self.textCursor()] + self.extra_cursors))
        else:
            super().copy()

    def cut(self):
        if self.extra_cursors:
            if not self.isReadOnly():
                self.copy()
                self.multi_edit("cut")
        else:
            super().cut()

    def inputMethodEvent(self, event):
        if self.extra_cursors and event.commitString() and not event.replacementStart() and not event.replacementLength():
            # Retire the primary preedit, then commit once at every cursor.
            super().inputMethodEvent(qt.QInputMethodEvent())
            self.multi_edit("insert", event.commitString())
            event.accept()
        else:
            super().inputMethodEvent(event)

    def contextMenuEvent(self, event):
        if not self.extra_cursors:
            super().contextMenuEvent(event)
            return
        menu = qt.QMenu(self)
        for label, callback, enabled in (("Undo", self.undo, not self.isReadOnly() and self.document().isUndoAvailable()),
                ("Redo", self.redo, not self.isReadOnly() and self.document().isRedoAvailable()),
                ("Cut", self.cut, not self.isReadOnly()), ("Copy", self.copy, True),
                ("Paste", self.paste, not self.isReadOnly()), ("Clear Extra Cursors", self.clear_extra_cursors, True)):
            action = menu.addAction(label)
            action.setEnabled(enabled)
            action.triggered.connect(callback)
        menu.exec(event.globalPos())
        menu.deleteLater()
