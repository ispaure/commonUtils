"""Bounded structural folding, shared by every view of a QTextDocument."""
import re
import weakref
from bisect import bisect_right
from .. import pyside as qt
from shiboken6 import isValid

MAX_FOLD_CHARS = 256 * 1024
MAX_FOLD_LINES = 10000


def fold_ranges(text, language):
    if len(text) > MAX_FOLD_CHARS or text.count("\n") >= MAX_FOLD_LINES:
        return {}
    lines = text.split("\n")
    ranges = {}
    if language in ("python", "yaml"):
        stack = []
        previous = None
        for number, line in enumerate(lines):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            indent = len(line.expandtabs(4)) - len(line.expandtabs(4).lstrip())
            while stack and indent <= stack[-1][0]:
                _, start = stack.pop()
                if number - 1 > start:
                    ranges[start] = number - 1
            if previous is not None and indent > previous[0]:
                stack.append(previous)
            previous = (indent, number)
        for _, start in stack:
            if len(lines) - 1 > start:
                ranges[start] = len(lines) - 1
        return ranges
    if language in ("xml", "html"):
        pattern = r"<!--.*?-->|<!\[CDATA\[.*?\]\]>|<(?:[^>\"']|\"[^\"]*\"|'[^']*')*>"
        stack = []
        newlines = [index for index, character in enumerate(text) if character == "\n"]
        for match in re.finditer(pattern, text, re.S):
            tag = match.group()
            if tag.startswith(("<!", "<?")):
                continue
            name = re.match(r"</?([\w:.-]+)", tag)
            if not name:
                continue
            name = name.group(1)
            line = bisect_right(newlines, match.start())
            if tag.startswith("</"):
                if stack and stack[-1][0] == name:
                    _, start = stack.pop()
                    if line > start:
                        ranges[start] = max(ranges.get(start, start), line)
            elif not tag.rstrip().endswith("/>") and not (language == "html" and name.lower() in
                    ("area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr")):
                stack.append((name, line))
        return ranges
    # Lexical tokens distinguish delimiters from strings and comments.
    try:
        from pygments import lex
        from pygments.lexers import get_lexer_by_name
        from pygments.token import Comment, String
        lexer = get_lexer_by_name(language, stripnl=False, ensurenl=False)
    except (ImportError, ValueError):
        return {}
    stack, line = [], 0
    pairs = {"}": "{", "]": "[", ")": "("}
    for token, value in lex(text, lexer):
        if token in Comment or token in String:
            line += value.count("\n")
            continue
        for character in value:
            if character in "{[(":
                stack.append((character, line))
            elif character in pairs and stack and stack[-1][0] == pairs[character]:
                _, start = stack.pop()
                if line > start:
                    ranges[start] = max(ranges.get(start, start), line)
            if character == "\n":
                line += 1
    return ranges


class FoldController(qt.QObject):
    def __init__(self, document):
        super().__init__(document)
        self.document = document
        self.language = "text"
        self.ranges = {}
        self.collapsed = set()
        self.dirty = True
        self.views = []
        self.timer = qt.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.expand_after_edit)
        document.contentsChanged.connect(self.changed)

    def changed(self):
        self.dirty = True
        # Never change layout from contentsChange, where Qt is mid-mutation.
        self.timer.start(0 if self.collapsed else 250)

    def expand_after_edit(self):
        self.collapsed.clear()
        self.rebuild()
        self.visibility()

    def configure(self, language):
        if language != self.language:
            self.language = language
            self.dirty = True
            self.expand_after_edit()

    def rebuild(self):
        if self.dirty:
            self.ranges = fold_ranges(self.document.toPlainText(), self.language) if self.language != "text" else {}
            self.dirty = False
        return self.ranges

    def toggle(self, line):
        self.rebuild()
        if line not in self.ranges:
            candidates = [start for start, end in self.ranges.items() if start <= line <= end]
            if not candidates:
                return
            line = max(candidates)
        if line in self.collapsed:
            self.collapsed.remove(line)
        else:
            self.collapsed.add(line)
        self.visibility()

    def fold_all(self):
        self.collapsed = set(self.rebuild())
        self.visibility()

    def visibility(self):
        # Sweep intervals once rather than scanning every fold for every block.
        hidden = [0] * (self.document.blockCount() + 1)
        for start in self.collapsed:
            end = self.ranges.get(start, start)
            if start + 1 < len(hidden):
                hidden[start + 1] += 1
                hidden[min(end + 1, len(hidden) - 1)] -= 1
        block, depth = self.document.firstBlock(), 0
        while block.isValid():
            depth += hidden[block.blockNumber()]
            visible = depth == 0
            block.setVisible(visible)
            block.setLineCount(1 if visible else 0)
            block = block.next()
        self.document.markContentsDirty(0, self.document.characterCount())
        for reference in self.views:
            editor = reference()
            if editor is not None and isValid(editor):
                cursor = editor.textCursor()
                if not cursor.block().isVisible():
                    starts = [start for start in self.collapsed if start < cursor.blockNumber() <= self.ranges[start]]
                    if starts:
                        editor.setTextCursor(qt.QTextCursor(self.document.findBlockByNumber(min(starts))))
                editor.viewport().update()
                editor.gutter.update()
                editor.updateGeometry()

    def reveal(self, line):
        containing = {start for start in self.collapsed if start < line <= self.ranges.get(start, start)}
        if containing:
            self.collapsed -= containing
            self.visibility()


class FoldingCommands:
    def bind_folding(self):
        document = self.document()
        if not hasattr(document, "_code_folding"):
            document._code_folding = FoldController(document)
        self.folding = document._code_folding
        self.folding.views.append(weakref.ref(self))
        self.folding_enabled = True
        self.indent_guides = True
        self.cursorPositionChanged.connect(self.reveal_cursor)

    def reveal_cursor(self):
        self.folding.reveal(self.textCursor().blockNumber())

    def fold_current(self):
        self.clear_extra_cursors()
        self.folding.toggle(self.textCursor().blockNumber())

    def fold_all(self):
        self.clear_extra_cursors()
        self.moveCursor(qt.QTextCursor.MoveOperation.Start)
        self.folding.fold_all()

    def unfold_all(self):
        self.folding.expand_after_edit()

    def gutter_click(self, point):
        if not self.folding_enabled or point.x() > 16:
            return
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        while block.isValid():
            height = round(self.blockBoundingRect(block).height())
            if block.isVisible() and top <= point.y() < top + height:
                self.folding.toggle(block.blockNumber())
                return
            top += height
            block = block.next()

    def draw_fold_marker(self, painter, block, top):
        if self.folding_enabled and block.blockNumber() in self.folding.ranges:
            painter.drawText(1, top, 14, self.fontMetrics().height(), qt.Qt.AlignmentFlag.AlignCenter,
                             "+" if block.blockNumber() in self.folding.collapsed else "−")

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.indent_guides:
            return
        painter = qt.QPainter(self.viewport())
        painter.setPen(self.palette().color(qt.QPalette.ColorRole.Mid))
        block = self.firstVisibleBlock()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        width = self.fontMetrics().horizontalAdvance(" ")
        while block.isValid() and top <= event.rect().bottom():
            height = self.blockBoundingRect(block).height()
            if block.isVisible():
                text = block.text()
                indent = len(text[:len(text) - len(text.lstrip(" \t"))].expandtabs(self.indent_width))
                origin = self.contentOffset().x() + self.document().documentMargin()
                for column in range(self.indent_width, min(indent + 1, 160), self.indent_width):
                    x = round(origin + column * width)
                    painter.drawLine(x, round(top), x, round(top + height))
            top += height
            block = block.next()
