"""Reusable, opt-in reader speech using Qt's installed platform speech engine.

No engine is created until the panel is opened. Readers provide plain text and
stop playback when replacing content. Long documents are split into bounded
utterances; stopping clears the queue before asking the native engine to stop.
"""
from collections import deque
from . import pyside as qt


def speech_chunks(text, limit=3000):
    """Bound utterances, preferring paragraph/sentence/word boundaries."""
    text = text.replace('\u2029', '\n').strip()
    while len(text) > limit:
        end = max(text.rfind('\n', 0, limit), text.rfind('. ', 0, limit))
        if end < limit // 3:
            end = text.rfind(' ', 0, limit)
        if end <= 0:
            end = limit
        yield text[:end].strip()
        text = text[end:].lstrip()
    if text:
        yield text


def reader_text(widget, *, start=None):
    """Selection takes precedence; otherwise read from a supplied text location."""
    cursor = widget.textCursor()
    if cursor.hasSelection():
        return cursor.selectedText().replace('\u2029', '\n')
    cursor = qt.QTextCursor(widget.document())
    cursor.setPosition(start or 0)
    cursor.movePosition(qt.QTextCursor.MoveOperation.End, qt.QTextCursor.MoveMode.KeepAnchor)
    return cursor.selectedText().replace('\u2029', '\n')


class ReadAloud(qt.QObject):
    positionChanged = qt.Signal(int, int)

    def __init__(self, owner, text_provider, *, engine_factory=None, scope='the current document',
                 text_widget=None, start_provider=None):
        super().__init__(owner)
        self.owner = owner
        self.text_provider = text_provider
        self.scope = scope
        self.engine_factory = engine_factory
        self.text_widget = text_widget
        self.start_provider = start_provider
        self._highlight_widget = None
        self._utterance_offset = 0
        self.anchor = None
        self.engine = None
        self.panel = None
        self.pending = deque()
        self._speaking = False
        self.advance = qt.QTimer(self)
        self.advance.setSingleShot(True)
        self.advance.timeout.connect(self._next)
        self.action = qt.QAction('Read aloud…', owner)
        self.action.setToolTip('Read selected text, or ' + scope)
        self.action.triggered.connect(self.show)
        owner.installEventFilter(self)
        owner.window().installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() in (qt.QEvent.Type.Close, qt.QEvent.Type.Hide):
            self.stop()
        return False

    def show(self):
        if self.panel is not None:
            self._position_panel()
            self.panel.show()
            self.panel.raise_()
            return
        self.panel = qt.QDialog(self.owner, qt.Qt.WindowType.Popup)
        self.panel.setWindowTitle('Read aloud')
        self.panel.setModal(False)
        self.panel.finished.connect(self.stop)
        layout = qt.QVBoxLayout(self.panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        heading = qt.QHBoxLayout()
        heading.addWidget(qt.QLabel('Read aloud'), 1)
        dismiss = qt.QToolButton(self.panel)
        dismiss.setText('×')
        dismiss.setAccessibleName('Close read aloud')
        dismiss.clicked.connect(self.panel.close)
        heading.addWidget(dismiss)
        layout.addLayout(heading)
        self.message = qt.QLabel('Reads selected text, or ' + self.scope + '.')
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        form = qt.QFormLayout()
        self.language = qt.QComboBox()
        self.voice = qt.QComboBox()
        self.speed = qt.QDoubleSpinBox()
        self.speed.setRange(-1, 1)
        self.speed.setSingleStep(.1)
        self.speed.setDecimals(1)
        self.speed.setToolTip('0 is normal speed; negative is slower, positive faster')
        for label, widget in (('Language', self.language), ('Voice', self.voice), ('Speed', self.speed)):
            widget.setMinimumHeight(32)
            form.addRow(label, widget)
        layout.addLayout(form)
        row = qt.QHBoxLayout()
        self.read = qt.QPushButton('Read')
        self.pause = qt.QPushButton('Pause')
        self.stop_button = qt.QPushButton('Stop')
        for button, callback in ((self.read, self.start), (self.pause, self.toggle_pause), (self.stop_button, self.stop)):
            row.addWidget(button)
            button.clicked.connect(callback)
        layout.addLayout(row)
        try:
            from PySide6.QtTextToSpeech import QTextToSpeech
            self.speech_type = QTextToSpeech
            if self.engine_factory is None and not QTextToSpeech.availableEngines():
                raise RuntimeError('No system speech engine is installed.')
            self.engine = (self.engine_factory or QTextToSpeech)(self)
            self.engine.stateChanged.connect(self._state_changed)
            if hasattr(self.engine, 'sayingWord'):
                self.engine.sayingWord.connect(self._word)
            self.engine.errorOccurred.connect(lambda *args: self._error())
            for locale in self.engine.availableLocales():
                self.language.addItem(locale.nativeLanguageName() + ' — ' + locale.name(), locale)
                if locale == self.engine.locale():
                    self.language.setCurrentIndex(self.language.count() - 1)
            self.language.currentIndexChanged.connect(self._language_changed)
            self._voices()
            self.voice.currentIndexChanged.connect(self._voice_changed)
            self.speed.valueChanged.connect(self.engine.setRate)
            self._state_changed(self.engine.state())
        except (ImportError, RuntimeError) as error:
            self.message.setText(f'Read aloud is unavailable: {error}')
            self.read.setEnabled(False)
            self.pause.setEnabled(False)
            self.stop_button.setEnabled(False)
        self.panel.resize(380, self.panel.sizeHint().height())
        self._position_panel()
        self.panel.show()

    def _position_panel(self):
        anchor = self.anchor or self.owner
        point = anchor.mapToGlobal(qt.QPoint(anchor.width(), anchor.height() if self.anchor else 48))
        screen = anchor.screen().availableGeometry()
        self.panel.move(max(screen.left(), min(point.x() - self.panel.width(), screen.right() - self.panel.width())),
                        max(screen.top(), min(point.y(), screen.bottom() - self.panel.height())))

    def _voices(self):
        self.voice.blockSignals(True)
        self.voice.clear()
        for voice in self.engine.availableVoices():
            self.voice.addItem(voice.name(), voice)
            if voice == self.engine.voice():
                self.voice.setCurrentIndex(self.voice.count() - 1)
        self.voice.blockSignals(False)

    def _language_changed(self):
        self.stop()
        locale = self.language.currentData()
        if locale is not None:
            self.engine.setLocale(locale)
            self._voices()

    def _voice_changed(self):
        self.stop()
        voice = self.voice.currentData()
        if voice is not None:
            self.engine.setVoice(voice)

    def start(self):
        if self.engine is None:
            return
        self.stop()
        text = self.text_provider()
        widget = self.text_widget() if callable(self.text_widget) else self.text_widget
        self._highlight_widget = widget
        cursor = widget.textCursor() if widget is not None else None
        base = cursor.selectionStart() if cursor is not None and cursor.hasSelection() else (
            self.start_provider() if self.start_provider else 0)
        search = 0
        capable = bool(self.engine.engineCapabilities() & self.speech_type.Capability.WordByWordProgress)
        for chunk in speech_chunks(text, 3000 if capable else 350):
            start = text.find(chunk, search)
            if start < 0:
                start = search
            offset = base + len(text[:start].encode('utf-16-le')) // 2
            self.pending.append((chunk, offset))
            search = start + len(chunk)
        if not self.pending:
            self.message.setText('There is no text to read here.')
            return
        self._next()

    def _next(self):
        if self.pending:
            text, self._utterance_offset = self.pending.popleft()
            self._highlight(self._utterance_offset, len(text.encode('utf-16-le')) // 2)
            self.engine.say(text)

    def _word(self, word, utterance, start, length):
        if self._speaking:
            self._highlight(self._utterance_offset + start, length)

    def _highlight(self, start, length):
        widget = self._highlight_widget
        if widget is None:
            return
        selection = qt.QTextEdit.ExtraSelection()
        cursor = qt.QTextCursor(widget.document())
        maximum = widget.document().characterCount() - 1
        cursor.setPosition(max(0, min(start, maximum)))
        cursor.setPosition(max(0, min(start + length, maximum)), qt.QTextCursor.MoveMode.KeepAnchor)
        selection.cursor = cursor
        selection.format.setBackground(widget.palette().brush(qt.QPalette.ColorRole.Highlight))
        selection.format.setForeground(widget.palette().brush(qt.QPalette.ColorRole.HighlightedText))
        selection.format.setProperty(qt.QTextFormat.Property.UserProperty + 77, True)
        others = [entry for entry in widget.extraSelections()
                  if not entry.format.property(qt.QTextFormat.Property.UserProperty + 77)]
        widget.setExtraSelections(others + [selection])
        self.positionChanged.emit(cursor.selectionStart(), cursor.selectionEnd())
        if not hasattr(widget, 'read_pointer'):
            rectangle = widget.cursorRect(cursor)
            if not widget.viewport().rect().contains(rectangle.center()):
                widget.verticalScrollBar().setValue(widget.verticalScrollBar().value() + rectangle.center().y()
                                                   - widget.viewport().height() // 2)

    def _clear_highlight(self):
        if self._highlight_widget is not None:
            widget = self._highlight_widget
            widget.setExtraSelections([entry for entry in widget.extraSelections()
                if not entry.format.property(qt.QTextFormat.Property.UserProperty + 77)])
        self._highlight_widget = None
        self.positionChanged.emit(-1, -1)

    def _state_changed(self, state):
        states = self.speech_type.State
        speaking = state == states.Speaking
        paused = state == states.Paused
        finished = state == states.Ready and self._speaking
        self._speaking = speaking or paused
        self.pause.setText('Resume' if paused else 'Pause')
        capable = bool(self.engine.engineCapabilities() & self.speech_type.Capability.PauseResume)
        self.pause.setEnabled(capable and (speaking or paused))
        self.stop_button.setEnabled(speaking or paused or bool(self.pending))
        self.read.setEnabled(state != states.Error)
        for control in (self.language, self.voice):
            control.setEnabled(not speaking and not paused)
        if state == states.Error:
            self._error()
        elif finished and self.pending:
            # Avoid starting another utterance inside a native state callback.
            self.advance.start(0)
        else:
            if finished:
                self._clear_highlight()
            self.message.setText('Reading…' if speaking else 'Paused' if paused else 'Ready — select text to read just that selection.')

    def _error(self):
        self.pending.clear()
        self._speaking = False
        self._clear_highlight()
        self.message.setText('Read aloud is unavailable: ' + (self.engine.errorString() or 'The system speech engine failed.'))
        self.read.setEnabled(False)
        self.pause.setEnabled(False)
        self.stop_button.setEnabled(False)

    def toggle_pause(self):
        if self.engine:
            if self.engine.state() == self.speech_type.State.Paused:
                self.engine.resume()
            else:
                self.engine.pause()

    def stop(self):
        self.advance.stop()
        self.pending.clear()
        self._speaking = False
        self._clear_highlight()
        if self.engine:
            self.engine.stop()
