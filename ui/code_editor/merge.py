"""Host-independent three-pane merge UI. Callers own loading and saving."""
from difflib import SequenceMatcher
from bisect import bisect_right
from .. import pyside as qt
from .widget import CodeEdit
from .syntax import SyntaxHighlighter, detect_language
from ...persistence.merge import MergeSession


def colors(editor, kind):
    dark = editor.palette().base().color().lightness() < 128
    return ({'add': '#204c3d', 'remove': '#493e40', 'modify': '#29435c', 'conflict': '#582d39'} if dark else
            {'add': '#d8f2e1', 'remove': '#e8e2e4', 'modify': '#dceafa', 'conflict': '#fce0e4'})[kind]


def position(text, offset):
    return len(text[:offset].encode('utf-16-le')) // 2


def select_range(editor, start, end, color, *, full=True):
    selection = qt.QTextEdit.ExtraSelection()
    cursor = qt.QTextCursor(editor.document())
    cursor.setPosition(position(editor.toPlainText(), start))
    cursor.setPosition(position(editor.toPlainText(), end), qt.QTextCursor.MoveMode.KeepAnchor)
    selection.cursor = cursor
    selection.format.setBackground(qt.QColor(color))
    if full:
        selection.format.setProperty(qt.QTextFormat.Property.FullWidthSelection, True)
    return selection


def line_offsets(text):
    result = [0]
    for line in text.splitlines(keepends=True):
        result.append(result[-1] + len(line))
    return result


def decorate(editor, ranges):
    text = editor.toPlainText()
    offsets = line_offsets(text)
    selections = []
    for start, end, kind in ranges:
        first = bisect_right(offsets, start)-1
        last = bisect_right(offsets, max(start, end-1))-1
        for line in range(first, last+1):
            block = editor.document().findBlockByNumber(line)
            if not block.isValid():
                continue
            selection = qt.QTextEdit.ExtraSelection()
            selection.cursor = qt.QTextCursor(block)
            selection.format.setBackground(qt.QColor(colors(editor, kind)))
            selection.format.setProperty(qt.QTextFormat.Property.FullWidthSelection, True)
            selections.append(selection)
    editor.search_selections = selections
    editor.highlight_cursor()


def emphasize(editor, offset, old, new):
    """Stronger character emphasis within short changed hunks; never unbounded."""
    if max(len(old), len(new)) > 8192 or old == new:
        return
    shade = qt.QColor(colors(editor, 'modify'))
    shade = shade.lighter(150) if editor.palette().base().color().lightness() < 128 else shade.darker(115)
    selections = []
    for tag, a, b, c, d in SequenceMatcher(None, old, new, autojunk=True).get_opcodes():
        if tag != 'equal' and c != d:
            selections.append(select_range(editor, offset+c, offset+d, shade.name(), full=False))
    editor.search_selections.extend(selections)
    editor.highlight_cursor()


class ChangeBridge(qt.QWidget):
    """Connecting bands with per-hunk arrow controls, without altering file text."""
    picked = qt.Signal(int)

    def __init__(self, left, right, parent=None):
        super().__init__(parent)
        self.left, self.right = left, right
        self.rows = []
        self.targets = []
        self.setFixedWidth(38)
        self.setToolTip('Click an arrow to accept this change')
        for editor in (left, right):
            editor.updateRequest.connect(lambda *args: self.update())
        self.setAccessibleName('Accept individual changes')
        self.active = -1
        self.setCursor(qt.Qt.CursorShape.PointingHandCursor)

    def bounds(self, editor, start, end):
        text = editor.toPlainText()
        a = editor.document().findBlockByNumber(text[:start].count('\n'))
        b = editor.document().findBlockByNumber(text[:max(start, end-1)].count('\n'))
        origin = self.mapFromGlobal(editor.viewport().mapToGlobal(qt.QPoint(0, 0))).y()
        top = editor.blockBoundingGeometry(a).translated(editor.contentOffset()).top() + origin
        bottom = editor.blockBoundingGeometry(b).translated(editor.contentOffset()).bottom() + origin
        return top, max(top+3, bottom)

    def paintEvent(self, event):
        painter = qt.QPainter(self)
        painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
        self.targets = []
        for index, (a, b, kind, arrow) in enumerate(self.rows):
            at, ab = self.bounds(self.left, *a)
            bt, bb = self.bounds(self.right, *b)
            if max(ab, bb) < 0 or min(at, bt) > self.height():
                continue
            path = qt.QPainterPath(qt.QPointF(0, at))
            path.cubicTo(18, at, 20, bt, self.width(), bt)
            path.lineTo(self.width(), bb)
            path.cubicTo(20, bb, 18, ab, 0, ab)
            path.closeSubpath()
            painter.fillPath(path, qt.QColor(colors(self.left, kind)))
            center = ((at+ab)/2 + (bt+bb)/2)/2
            rect = qt.QRect(5, round(center)-11, 28, 22)
            painter.setPen(self.palette().color(qt.QPalette.ColorRole.Text))
            if index == self.active:
                painter.setPen(self.palette().color(qt.QPalette.ColorRole.Link))
                painter.drawRoundedRect(rect.adjusted(0, 1, 0, -1), 3, 3)
            painter.drawText(rect, qt.Qt.AlignmentFlag.AlignCenter, arrow)
            self.targets.append((rect, index))

    def mousePressEvent(self, event):
        if event.button() == qt.Qt.MouseButton.LeftButton:
            for rect, index in self.targets:
                if rect.contains(event.position().toPoint()):
                    self.picked.emit(index)
                    return
        super().mousePressEvent(event)


class PaneSplitter(qt.QSplitter):
    """Resizable code panes with connecting bands inside splitter handles."""
    def __init__(self, parent=None):
        super().__init__(qt.Qt.Orientation.Horizontal, parent)
        self.setChildrenCollapsible(False)
        self.setHandleWidth(42)

    def connect_editors(self, editors):
        bridges = []
        for i in range(1, len(editors)):
            handle = self.handle(i)
            layout = qt.QVBoxLayout(handle)
            layout.setContentsMargins(2, 0, 2, 0)
            layout.setSpacing(0)
            bridge = ChangeBridge(editors[i-1], editors[i], handle)
            layout.addWidget(bridge)
            bridges.append(bridge)
        self.setSizes([400] * len(editors))
        return bridges


class LinkedScroll:
    def __init__(self, editors):
        self.editors, self.busy, self.maps = editors, False, {}
        for editor in editors:
            editor.verticalScrollBar().valueChanged.connect(lambda value, source=editor: self.sync(source))
        self.texts = None
        self.rebuild()

    def rebuild(self):
        texts = tuple(editor.toPlainText() for editor in self.editors)
        if texts == self.texts:
            return
        self.texts = texts
        self.maps = {(a, b): SequenceMatcher(None, a.toPlainText().splitlines(), b.toPlainText().splitlines(),
                                            autojunk=True).get_opcodes()
                     for a in self.editors for b in self.editors if a is not b}

    def sync(self, source):
        if self.busy:
            return
        self.busy = True
        try:
            line = source.firstVisibleBlock().blockNumber()
            for target in self.editors:
                if target is source:
                    continue
                mapped = line
                for tag, a, b, c, d in self.maps[source, target]:
                    if a <= line < b or a == b == line:
                        mapped = c + min(line-a, max(0, d-c-1))
                        break
                target.verticalScrollBar().setValue(mapped)
        finally:
            self.busy = False


class ResultEdit(CodeEdit):
    undo_requested = qt.Signal()
    redo_requested = qt.Signal()

    def undo(self):
        self.undo_requested.emit()

    def redo(self):
        self.redo_requested.emit()

    def keyPressEvent(self, event):
        if event.matches(qt.QKeySequence.StandardKey.Undo):
            self.undo()
            return
        if event.matches(qt.QKeySequence.StandardKey.Redo):
            self.redo()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        # Qt's document history is disabled; replace its disabled native entries.
        for action in menu.actions()[:2]:
            menu.removeAction(action)
        anchor = menu.actions()[0]
        undo = menu.addAction('Undo merge edit', self.undo)
        redo = menu.addAction('Redo merge edit', self.redo)
        undo.setEnabled(self.can_undo)
        redo.setEnabled(self.can_redo)
        menu.insertAction(anchor, undo)
        menu.insertAction(anchor, redo)
        menu.exec(event.globalPos())
        menu.deleteLater()


class MergeWidget(qt.QWidget):
    changed = qt.Signal()

    def __init__(self, model, parent=None, *, left_name='Left', right_name='Right', path=None):
        super().__init__(parent)
        self.session = MergeSession(model)
        self.index = 0 if model.regions else -1
        self.updating = False
        layout = qt.QVBoxLayout(self)
        toolbar = qt.QHBoxLayout()
        self.status = qt.QLabel()
        toolbar.addWidget(self.status, 1)
        self.search = qt.QLineEdit()
        self.search.setPlaceholderText("Find in focused pane")
        self.search.setAccessibleName("Find in merge pane")
        self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(self.find_next)
        toolbar.addWidget(self.search)
        self.buttons = []
        for label, action in [('Previous', lambda: self.navigate(-1)), ('Next', lambda: self.navigate(1)),
                              ('Apply non-conflicting', self.apply_nonconflicting), ('Undo', self.undo), ('Redo', self.redo)]:
            button = qt.QPushButton(label)
            button.clicked.connect(action)
            toolbar.addWidget(button)
            self.buttons.append(button)
        layout.addLayout(toolbar)
        self.splitter = PaneSplitter()
        self.editors = []
        self.highlighters = []
        for label, text, editable in [(left_name, model.left, False), ('Result', model.base, True), (right_name, model.right, False)]:
            host = qt.QWidget()
            column = qt.QVBoxLayout(host)
            column.setContentsMargins(0, 0, 0, 0)
            title = qt.QLabel(label)
            title.setTextFormat(qt.Qt.TextFormat.PlainText)
            column.addWidget(title)
            editor = ResultEdit() if editable else CodeEdit()
            editor.setReadOnly(not editable)
            editor.setPlainText(text)
            editor.setAccessibleName(label)
            editor.indent_guides = False
            column.addWidget(editor, 1)
            self.editors.append(editor)
            editor.focused.connect(lambda editor=editor: setattr(self, "active_editor", editor))
            self.highlighters.append(SyntaxHighlighter(editor, detect_language(path, text)))
            self.splitter.addWidget(host)
        self.left_bridge, self.right_bridge = self.splitter.connect_editors(self.editors)
        self.left_bridge.picked.connect(lambda index: self.choose(index, 'left'))
        self.right_bridge.picked.connect(lambda index: self.choose(index, 'right'))
        layout.addWidget(self.splitter, 1)
        self.result = self.editors[1]
        self.active_editor = self.result
        self.find_shortcut = qt.QShortcut(qt.QKeySequence(qt.QKeySequence.StandardKey.Find), self)
        self.find_shortcut.setContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.find_shortcut.activated.connect(lambda: (self.search.setFocus(), self.search.selectAll()))
        self.result.document().setUndoRedoEnabled(False)
        self.result.undo_requested.connect(self.undo)
        self.result.redo_requested.connect(self.redo)
        self.history_actions = []
        for key, callback in ((qt.QKeySequence.StandardKey.Undo, self.undo),
                              (qt.QKeySequence.StandardKey.Redo, self.redo)):
            action = qt.QAction(self)
            action.setShortcuts(qt.QKeySequence.keyBindings(key))
            action.setShortcutContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            action.triggered.connect(callback)
            self.addAction(action)
            self.history_actions.append(action)
        self.result.textChanged.connect(self._edited)
        self.scroll = LinkedScroll(self.editors)
        actions = qt.QHBoxLayout()
        for label, side in [('Use left', 'left'), ('Use right', 'right'), ('Use both (left then right)', 'both'), ('Keep base', 'base')]:
            button = qt.QPushButton(label)
            button.clicked.connect(lambda checked=False, side=side: self.choose(self.index, side))
            button.setEnabled(bool(model.regions))
            actions.addWidget(button)
        manual = qt.QPushButton('Mark selected change resolved')
        manual.clicked.connect(self.mark_manual)
        manual.setEnabled(bool(model.regions))
        actions.addWidget(manual)
        manual.setToolTip('Confirm the selected result after editing it by hand. Undo also reverses this decision.')
        self.base_toggle = qt.QCheckBox('Show common ancestor')
        actions.addWidget(self.base_toggle)
        layout.addLayout(actions)
        self.base_view = CodeEdit()
        self.base_view.setReadOnly(True)
        self.base_view.setPlainText(model.base)
        self.base_view.setAccessibleName('Common ancestor')
        self.base_view.hide()
        self.base_toggle.toggled.connect(self.base_view.setVisible)
        layout.addWidget(self.base_view)
        legend = qt.QLabel("Blue: modified · Green: added · Gray: deleted · Red: unresolved conflict")
        layout.addWidget(legend)
        self.refresh_timer = qt.QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.setInterval(180)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == qt.QEvent.Type.PaletteChange and hasattr(self, 'refresh_timer'):
            self.refresh_timer.start(0)

    def find_next(self):
        if not self.search.text():
            return
        if not self.active_editor.find(self.search.text()):
            cursor = self.active_editor.textCursor()
            cursor.movePosition(qt.QTextCursor.MoveOperation.Start)
            self.active_editor.setTextCursor(cursor)
            self.active_editor.find(self.search.text())

    def _edited(self):
        if self.updating:
            return
        try:
            self.session.edit(self.result.toPlainText())
        except ValueError as error:
            self.render()
            self.status.setText(str(error))
            return
        self.changed.emit()
        self._history_availability()
        self.refresh_timer.start()

    def render(self):
        cursor = self.result.textCursor().position()
        self.updating = True
        try:
            self.result.setPlainText(self.session.text)
            target = self.result.textCursor()
            target.setPosition(min(cursor, self.result.document().characterCount()-1))
            self.result.setTextCursor(target)
        finally:
            self.updating = False
        self.refresh()

    def refresh(self):
        self.refresh_timer.stop()
        model = self.session.model
        left_offsets, right_offsets = line_offsets(model.left), line_offsets(model.right)
        left, middle, right, lb, rb = [], [], [], [], []
        for i, region in enumerate(model.regions):
            kind = 'conflict' if region.conflict and not self.session.resolved[i] else 'add' if not region.base else 'remove' if not region.left or not region.right else 'modify'
            a = tuple(left_offsets[n] for n in region.left_lines)
            b = self.session.ranges[i]
            c = tuple(right_offsets[n] for n in region.right_lines)
            left.append((*a, kind))
            middle.append((*b, kind))
            right.append((*c, kind))
            lb.append((a, b, kind, '›'))
            rb.append((b, c, kind, '‹'))
        for editor, ranges in zip(self.editors, (left, middle, right)):
            decorate(editor, ranges)
        for i, region in enumerate(model.regions):
            emphasize(self.editors[0], lb[i][0][0], region.right, region.left)
            emphasize(self.editors[2], rb[i][1][0], region.left, region.right)
        self.left_bridge.active = self.right_bridge.active = self.index
        self.left_bridge.rows, self.right_bridge.rows = lb, rb
        self.left_bridge.update()
        self.right_bridge.update()
        self.scroll.rebuild()
        self.status.setText(f'{self.session.unresolved} unresolved · Change {self.index+1} of {len(model.regions)}')
        self.buttons[0].setEnabled(bool(model.regions))
        self.buttons[1].setEnabled(bool(model.regions))
        self._history_availability()
        self.changed.emit()

    def _history_availability(self):
        self.result.can_undo = bool(self.session.history)
        self.result.can_redo = bool(self.session.future)
        for available, button, action in zip((self.result.can_undo, self.result.can_redo), self.buttons[3:5], self.history_actions):
            button.setEnabled(available)
            action.setEnabled(available)

    def choose(self, index, side):
        if index < 0:
            return
        try:
            self.session.choose(index, side)
        except ValueError as error:
            self.status.setText(str(error))
            return
        self.index = index
        self.render()

    def apply_nonconflicting(self):
        try:
            self.session.apply_nonconflicting()
        except ValueError as error:
            self.status.setText(str(error))
            return
        self.render()

    def mark_manual(self):
        if self.index >= 0:
            self.session.mark_manual(self.index)
            self.refresh()

    def undo(self):
        self.session.undo()
        self.render()

    def redo(self):
        self.session.redo()
        self.render()

    def navigate(self, step):
        if not self.session.model.regions:
            return
        self.index = (self.index + step) % len(self.session.model.regions)
        region = self.session.model.regions[self.index]
        offsets = [line_offsets(self.session.model.left)[region.left_lines[0]],
                   self.session.ranges[self.index][0], line_offsets(self.session.model.right)[region.right_lines[0]]]
        self.scroll.busy = True
        try:
            for editor, offset in zip(self.editors, offsets):
                cursor = qt.QTextCursor(editor.document())
                cursor.setPosition(position(editor.toPlainText(), offset))
                editor.setTextCursor(cursor)
                editor.centerCursor()
        finally:
            self.scroll.busy = False
        self.refresh()


class MergeDialog(qt.QDialog):
    def __init__(self, model, parent=None, *, apply=None, left_name='Left', right_name='Right', path=None):
        super().__init__(parent)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle('Merge — ' + str(path or 'Text'))
        self.resize(1400, 800)
        self.widget = MergeWidget(model, self, left_name=left_name, right_name=right_name, path=path)
        self.apply_callback = apply
        self.applying = False
        layout = qt.QVBoxLayout(self)
        layout.addWidget(self.widget)
        row = qt.QHBoxLayout()
        row.addStretch()
        cancel = qt.QPushButton('Cancel')
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        self.apply_button = qt.QPushButton('Apply result')
        self.apply_button.clicked.connect(self.apply_result)
        row.addWidget(self.apply_button)
        layout.addLayout(row)
        self.widget.changed.connect(self._ready)
        self._ready()

    def reject(self):
        if not self.applying:
            super().reject()

    def closeEvent(self, event):
        if self.applying:
            event.ignore()
        else:
            super().closeEvent(event)

    def _ready(self):
        self.apply_button.setEnabled(not self.applying and self.apply_callback is not None and self.widget.session.unresolved == 0)

    def apply_result(self):
        if self.widget.session.unresolved or self.apply_callback is None:
            return
        try:
            accepted = self.apply_callback(self.widget.session.text)
        except (OSError, ValueError, RuntimeError) as error:
            self.widget.status.setText(str(error))
            return
        if accepted is not False:
            self.accept()
