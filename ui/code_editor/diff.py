"""Reusable bounded text diff model and side-by-side review dialog."""
from dataclasses import dataclass
from difflib import SequenceMatcher, unified_diff
from .. import pyside as qt
from .widget import CodeEdit


@dataclass(frozen=True)
class Change:
    left_start: int
    left_end: int
    right_start: int
    right_end: int


@dataclass(frozen=True)
class TextDiff:
    left: str
    right: str
    changes: tuple
    unified: str


def compare_text(left, right, left_name="Original", right_name="Buffer"):
    a, b = left.splitlines(keepends=True), right.splitlines(keepends=True)
    if max(len(left), len(right)) > 1024 * 1024 or max(len(a), len(b)) > 5000:
        raise ValueError("Diff is limited to 1 MiB and 5,000 lines per side.")
    changes = tuple(Change(i, j, k, end) for tag, i, j, k, end
                    in SequenceMatcher(None, a, b, autojunk=True).get_opcodes() if tag != "equal")
    # A visible marker makes final-newline-only changes apparent.
    unified = []
    for line in unified_diff(a, b, fromfile=left_name, tofile=right_name):
        unified.append(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n")
    return TextDiff(left, right, changes, "".join(unified))


def apply_change(model, index, current):
    if current != model.right:
        raise ValueError("The buffer changed after comparison. Reopen the diff before applying changes.")
    change = model.changes[index]
    a, b = model.left.splitlines(keepends=True), model.right.splitlines(keepends=True)
    start = len("".join(b[:change.right_start]))
    end = len("".join(b[:change.right_end]))
    return start, end, "".join(a[change.left_start:change.left_end])


class DiffDialog(qt.QDialog):
    def __init__(self, model, parent=None, *, left_name="Original", right_name="Buffer", apply=None):
        super().__init__(parent)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("Compare — " + left_name + " / " + right_name)
        self.resize(1100, 700)
        self.model, self.apply_callback, self.index = model, apply, -1
        layout = qt.QVBoxLayout(self)
        tabs = qt.QTabWidget()
        sides = qt.QWidget()
        row = qt.QHBoxLayout(sides)
        self.editors = []
        for name, text in ((left_name, model.left), (right_name, model.right)):
            column = qt.QVBoxLayout()
            column.addWidget(qt.QLabel(name))
            editor = CodeEdit()
            editor.setReadOnly(True)
            editor.setPlainText(text)
            column.addWidget(editor)
            row.addLayout(column)
            self.editors.append(editor)
        tabs.addTab(sides, "Side by Side")
        unified = qt.QPlainTextEdit()
        unified.setReadOnly(True)
        unified.setFont(self.editors[0].font())
        unified.setPlainText(model.unified or "No differences")
        tabs.addTab(unified, "Unified Diff")
        layout.addWidget(tabs)
        buttons = qt.QHBoxLayout()
        self.status = qt.QLabel()
        buttons.addWidget(self.status, 1)
        for label, direction in (("Previous", -1), ("Next", 1)):
            button = qt.QPushButton(label)
            button.setEnabled(bool(model.changes))
            button.clicked.connect(lambda checked=False, direction=direction: self.navigate(direction))
            buttons.addWidget(button)
        self.use_left = qt.QPushButton("Use Left Change")
        self.use_left.setEnabled(apply is not None and bool(model.changes))
        self.use_left.clicked.connect(self.apply_current)
        buttons.addWidget(self.use_left)
        close = qt.QPushButton("Close")
        close.clicked.connect(self.close)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.navigate(1)

    def navigate(self, direction):
        if not self.model.changes:
            self.status.setText("No differences")
            return
        self.index = (self.index + direction) % len(self.model.changes)
        change = self.model.changes[self.index]
        self.status.setText(f"Change {self.index + 1} of {len(self.model.changes)}")
        for editor, start, end in zip(self.editors,
                (change.left_start, change.right_start), (change.left_end, change.right_end)):
            block = editor.document().findBlockByNumber(min(start, editor.blockCount() - 1))
            cursor = qt.QTextCursor(block)
            editor.setTextCursor(cursor)
            editor.centerCursor()
            selections = []
            for line in range(start, max(start + 1, end)):
                block = editor.document().findBlockByNumber(line)
                if block.isValid():
                    selection = qt.QTextEdit.ExtraSelection()
                    selection.cursor = qt.QTextCursor(block)
                    selection.format.setProperty(qt.QTextFormat.Property.FullWidthSelection, True)
                    selection.format.setBackground(editor.palette().brush(qt.QPalette.ColorRole.Highlight))
                    selection.format.setForeground(editor.palette().brush(qt.QPalette.ColorRole.HighlightedText))
                    selections.append(selection)
            editor.search_selections = selections
            editor.highlight_cursor()

    def apply_current(self):
        if self.apply_callback and self.index >= 0:
            try:
                self.apply_callback(self.model, self.index)
            except (ValueError, OSError) as error:
                self.status.setText(str(error))
                return
            self.use_left.setEnabled(False)
            self.status.setText("Change applied. Reopen comparison to review the updated buffer.")
