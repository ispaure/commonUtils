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
    """Two-way comparison with reusable bands and optional undoable host edits.

    Undo/redo callbacks receive the current model for stale-buffer validation,
    operate on the host's edit history, and return its resulting text.
    """
    def __init__(self, model, parent=None, *, left_name="Original", right_name="Buffer", apply=None, path=None,
                 undo=None, redo=None):
        super().__init__(parent)
        from .merge import PaneSplitter, LinkedScroll
        from .syntax import SyntaxHighlighter, detect_language
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("Compare — " + left_name + " / " + right_name)
        self.resize(1200, 750)
        self.model, self.apply_callback, self.index = model, apply, -1
        self.undo_callback, self.redo_callback = undo, redo
        self.history, self.future = [], []
        self.names = left_name, right_name
        self.editors, self.highlighters = [], []
        layout = qt.QVBoxLayout(self)
        tabs = qt.QTabWidget(); sides = qt.QWidget(); row = qt.QVBoxLayout(sides)
        self.splitter = PaneSplitter(); row.addWidget(self.splitter)
        for name, text in ((left_name, model.left), (right_name, model.right)):
            host = qt.QWidget(); column = qt.QVBoxLayout(host)
            label = qt.QLabel(name); label.setTextFormat(qt.Qt.TextFormat.PlainText); column.addWidget(label)
            editor = CodeEdit(); editor.setReadOnly(True); editor.setPlainText(text)
            editor.setAccessibleName(name); column.addWidget(editor)
            self.editors.append(editor)
            self.highlighters.append(SyntaxHighlighter(editor, detect_language(path, text)))
            self.splitter.addWidget(host)
        self.bridge = self.splitter.connect_editors(self.editors)[0]
        self.bridge.picked.connect(self._pick)
        tabs.addTab(sides, "Side by Side")
        self.unified = qt.QPlainTextEdit(); self.unified.setReadOnly(True)
        self.unified.setFont(self.editors[0].font()); tabs.addTab(self.unified, "Unified Diff")
        layout.addWidget(tabs)
        buttons = qt.QHBoxLayout(); self.status = qt.QLabel(); buttons.addWidget(self.status, 1)
        self.navigation = []
        for label, direction in (("Previous", -1), ("Next", 1)):
            button = qt.QPushButton(label)
            button.clicked.connect(lambda checked=False, direction=direction: self.navigate(direction))
            buttons.addWidget(button); self.navigation.append(button)
        self.use_left = qt.QPushButton("Use Left Change"); self.use_left.clicked.connect(self.apply_current)
        buttons.addWidget(self.use_left)
        self.history_actions = []
        for label, key, callback in (("Undo", qt.QKeySequence.StandardKey.Undo, self.undo),
                                     ("Redo", qt.QKeySequence.StandardKey.Redo, self.redo)):
            action = qt.QAction(label, self)
            action.setShortcuts(qt.QKeySequence.keyBindings(key))
            action.setShortcutContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            action.triggered.connect(callback); self.addAction(action)
            button = qt.QPushButton(label); button.clicked.connect(callback)
            action.changed.connect(lambda action=action, button=button: button.setEnabled(action.isEnabled()))
            buttons.addWidget(button); self.history_actions.append(action)
        close = qt.QPushButton("Close"); close.clicked.connect(self.close); buttons.addWidget(close)
        layout.addLayout(buttons)
        self.scroll = LinkedScroll(self.editors)
        self._render(); self.navigate(1)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == qt.QEvent.Type.PaletteChange and hasattr(self, 'scroll'):
            self._render()

    def _render(self):
        from .merge import line_offsets, decorate, emphasize
        left, right = line_offsets(self.model.left), line_offsets(self.model.right)
        bands = [[], []]; self.bridge.rows = []
        for change in self.model.changes:
            a = left[change.left_start], left[change.left_end]
            b = right[change.right_start], right[change.right_end]
            kind = 'add' if a[0] == a[1] else 'remove' if b[0] == b[1] else 'modify'
            bands[0].append((*a, kind)); bands[1].append((*b, kind))
            self.bridge.rows.append((a, b, kind, '›' if self.apply_callback else '·'))
        for editor, text, ranges in zip(self.editors, (self.model.left, self.model.right), bands):
            editor.setPlainText(text); decorate(editor, ranges)
        for change in self.model.changes:
            a = left[change.left_start], left[change.left_end]
            b = right[change.right_start], right[change.right_end]
            emphasize(self.editors[0], a[0], self.model.right[b[0]:b[1]], self.model.left[a[0]:a[1]])
            emphasize(self.editors[1], b[0], self.model.left[a[0]:a[1]], self.model.right[b[0]:b[1]])
        self.unified.setPlainText(self.model.unified or "No differences")
        self.bridge.update(); self.scroll.rebuild()
        self.use_left.setEnabled(self.apply_callback is not None and bool(self.model.changes))
        for button in self.navigation:
            button.setEnabled(bool(self.model.changes))
        self.history_actions[0].setEnabled(self.undo_callback is not None and bool(self.history))
        self.history_actions[1].setEnabled(self.redo_callback is not None and bool(self.future))

    def _pick(self, index):
        self.index = index
        self.apply_current() if self.apply_callback else self.navigate(0)

    def navigate(self, direction):
        if not self.model.changes:
            self.index = -1; self.status.setText("No differences"); return
        self.index = (self.index + direction) % len(self.model.changes)
        change = self.model.changes[self.index]
        self.status.setText(f"Change {self.index + 1} of {len(self.model.changes)}")
        self.bridge.active = self.index; self.bridge.update()
        self.scroll.busy = True
        try:
            for editor, start in zip(self.editors, (change.left_start, change.right_start)):
                block = editor.document().findBlockByNumber(min(start, editor.blockCount()-1))
                editor.setTextCursor(qt.QTextCursor(block)); editor.centerCursor()
        finally:
            self.scroll.busy = False

    def apply_current(self):
        if self.apply_callback and self.index >= 0:
            try:
                current = self.apply_callback(self.model, self.index)
                if current is None:
                    self.use_left.setEnabled(False)
                    self.status.setText("Change applied. Reopen comparison to review the updated buffer.")
                    return
                updated = compare_text(self.model.left, current, *self.names)
                self.history.append(self.model)
                while len(self.history) > 100 or sum(len(state.right) for state in self.history) > 16 * 1024 * 1024:
                    self.history.pop(0)
                self.future.clear()
                self.model = updated
            except (ValueError, OSError) as error:
                self.status.setText(str(error)); return
            self._render(); self.index = min(self.index, len(self.model.changes)-1); self.navigate(0)

    def _restore(self, source, target, callback):
        if not source or callback is None:
            return
        try:
            current = callback(self.model)
            if current != source[-1].right:
                raise ValueError("The buffer history changed. Reopen the diff before undoing or redoing changes.")
        except (ValueError, OSError, RuntimeError) as error:
            self.status.setText(str(error)); return
        target.append(self.model)
        self.model = source.pop()
        self._render(); self.index = min(max(self.index, 0), len(self.model.changes)-1); self.navigate(0)

    def undo(self):
        self._restore(self.history, self.future, self.undo_callback)

    def redo(self):
        self._restore(self.future, self.history, self.redo_callback)
