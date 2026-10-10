"""Reusable, opt-in reader speech using Qt's installed platform speech engine.

No engine is created until the panel is opened. Readers provide plain text and
stop playback when replacing content. Long documents are split into bounded
utterances; stopping clears the queue before asking the native engine to stop.
"""
from collections import deque
from bisect import bisect_right
import re
from time import monotonic
from . import pyside as qt
from .icons import set_painted_icon
from .reader_chrome import ReaderIcon, reader_button


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


def visible_text_start(widget):
    """Text offset at the top of the visible reading area, independent of caret."""
    return widget.cursorForPosition(qt.QPoint(1, 1)).position()


def _word_ranges(text, base=0):
    offset, previous = base, 0
    for word in re.finditer(r'\S+', text):
        offset += len(text[previous:word.start()].encode('utf-16-le')) // 2
        end = offset + len(word.group().encode('utf-16-le')) // 2
        yield offset, end
        offset, previous = end, word.end()


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
        self._source_text = ''
        self._source_base = 0
        self._word_starts = []
        self._position = 0
        self._word_events = deque(maxlen=30)
        self._utterance_words = []
        self._utterance_word_index = 0
        self._native_words = False
        self.word_timer = qt.QTimer(self)
        self.word_timer.setSingleShot(True)
        self.word_timer.timeout.connect(self._estimated_word)
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
        self.back = reader_button(self.panel, 'Back 15 seconds', icon='back15')
        self.forward = reader_button(self.panel, 'Forward 15 seconds', icon='forward15')
        for button in (self.back, self.forward):
            button.setToolTip(button.accessibleName() + ' (approximate text position)')
        self.read = reader_button(self.panel, 'Play', icon='play')
        self.pause = reader_button(self.panel, 'Pause', icon='pause')
        self.stop_button = reader_button(self.panel, 'Stop', icon='stop')
        for button, callback in ((self.back, lambda: self.skip(-15)), (self.read, self.start),
                                 (self.pause, self.toggle_pause), (self.stop_button, self.stop),
                                 (self.forward, lambda: self.skip(15))):
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
            self.back.setEnabled(False); self.forward.setEnabled(False)
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
        widget = self.text_widget() if callable(self.text_widget) else self.text_widget
        cursor = widget.textCursor() if widget is not None else None
        base = cursor.selectionStart() if cursor is not None and cursor.hasSelection() else (
            self.start_provider() if self.start_provider else visible_text_start(widget) if widget is not None else 0)
        text = reader_text(widget, start=0) if widget is not None and not cursor.hasSelection() else self.text_provider()
        source_base = 0 if widget is not None and not cursor.hasSelection() else base
        self.stop()
        self._source_text, self._source_base = text, source_base
        self._word_starts = [start for start, end in _word_ranges(text, source_base)]
        self._word_events.clear()
        self._highlight_widget = widget
        self._queue_from(base)

    def _queue_from(self, position):
        self.advance.stop(); self.word_timer.stop()
        self.pending.clear()
        self._speaking = False
        self.engine.stop()
        self._position = position
        relative = max(0, position - self._source_base)
        prefix = self._source_text.encode('utf-16-le')[:relative * 2].decode('utf-16-le', errors='ignore')
        text = self._source_text[len(prefix):]
        search = 0
        self._native_words = bool(self.engine.engineCapabilities() & self.speech_type.Capability.WordByWordProgress)
        for chunk in speech_chunks(text, 3000 if self._native_words else 350):
            start = text.find(chunk, search)
            if start < 0: start = search
            offset = position + len(text[:start].encode('utf-16-le')) // 2
            self.pending.append((chunk, offset))
            search = start + len(chunk)
        if not self.pending:
            self.message.setText('There is no text to read here.')
            self._clear_highlight()
            return
        self._next()

    def _next(self):
        if self.pending:
            text, self._utterance_offset = self.pending.popleft()
            self._utterance_words = list(_word_ranges(text, self._utterance_offset))
            self._utterance_word_index = 0
            if self._utterance_words:
                start, end = self._utterance_words[0]
                self._position = start
                self._highlight(start, end - start)
            self.engine.say(text)

    def _word(self, word, utterance, start, length):
        if self._speaking:
            self._native_words = True
            self.word_timer.stop()
            self._position = self._utterance_offset + start
            self._word_events.append((monotonic(), bisect_right(self._word_starts, self._position) - 1))
            self._highlight(self._position, length)

    def _words_per_second(self):
        if len(self._word_events) > 3:
            first, last = self._word_events[0], self._word_events[-1]
            if last[0] - first[0] > 1 and last[1] > first[1]:
                return max(1, min(8, (last[1] - first[1]) / (last[0] - first[0])))
        return max(1, 3 * (1 + self.speed.value()))

    def _estimated_word(self):
        if not self._speaking or self._native_words:
            return
        self._utterance_word_index = min(self._utterance_word_index + 1, len(self._utterance_words) - 1)
        if self._utterance_words:
            start, end = self._utterance_words[self._utterance_word_index]
            self._position = start
            self._highlight(start, end - start)
            if self._utterance_word_index + 1 < len(self._utterance_words):
                self.word_timer.start(round(1000 / self._words_per_second()))

    def skip(self, seconds):
        """Seek approximately by speech time; native Qt engines expose text, not audio seeking."""
        if not self._word_starts or self.engine is None:
            return
        paused = self.engine.state() == self.speech_type.State.Paused
        current = max(0, bisect_right(self._word_starts, self._position) - 1)
        target = max(0, min(len(self._word_starts) - 1, current + round(seconds * self._words_per_second())))
        self._word_events.clear()
        self._queue_from(self._word_starts[target])
        if paused: self.engine.pause()

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
        if paused: self._word_events.clear()
        label = 'Resume' if paused else 'Pause'
        self.pause.setText(label)
        self.pause.setToolTip(label)
        self.pause.setAccessibleName(label)
        set_painted_icon(self.pause, ReaderIcon, 'play' if paused else 'pause')
        capable = bool(self.engine.engineCapabilities() & self.speech_type.Capability.PauseResume)
        self.pause.setEnabled(capable and (speaking or paused))
        self.stop_button.setEnabled(speaking or paused or bool(self.pending))
        for button in (self.back, self.forward):
            button.setEnabled(bool(self._word_starts) and (speaking or paused))
        if speaking and not self._native_words and self._utterance_words:
            self.word_timer.start(round(1000 / self._words_per_second()))
        elif not speaking:
            self.word_timer.stop()
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
        self.word_timer.stop()
        self.advance.stop()
        self.pending.clear()
        self._speaking = False
        self._clear_highlight()
        if self.engine:
            self.engine.stop()
