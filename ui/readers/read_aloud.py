"""Reusable, opt-in reader speech using Qt's installed platform speech engine.

No engine is created until the panel is opened. Readers provide plain text and
stop playback when replacing content. Long documents are split into bounded
utterances; stopping clears the queue before asking the native engine to stop.
"""
import math
from time import monotonic
from ...runtime.speech import SpeechSession, PlaybackTimer, utterances
from .qt_speech import QtScheduler, QtSpeechEngine
from ...runtime.speech_language import passage_language, matching_locale
from .. import pyside as qt
from ..appearance.icons import set_painted_icon
from .reader_chrome import ReaderIcon, reader_button, prevent_reader_popup_replay


def speech_chunks(text, limit=3000):
    """Bound utterances, preferring paragraph/sentence/word boundaries."""
    for chunk, _, _ in utterances(text.replace('\u2029', '\n'), limit=limit, sentence_breaks=False):
        yield chunk.strip()


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


class ReadAloud(qt.QObject):
    positionChanged = qt.Signal(int, int)

    def __init__(self, owner, text_provider, *, engine_factory=None, scope='the current document',
                 text_widget=None, start_provider=None, language_provider=lambda: '', on_finished=lambda: None):
        super().__init__(owner)
        self.owner = owner
        self.text_provider = text_provider
        self.scope = scope
        self.engine_factory = engine_factory
        self.text_widget = text_widget
        self.start_provider = start_provider
        self.language_provider = language_provider
        self.on_finished = on_finished
        self._selected_passage = False
        self._highlight_widget = None
        self.anchor = None
        self.engine = None
        self.panel = None
        self.session = None
        self._source_base = 0
        self.scheduler = QtScheduler(self)
        self.playback = PlaybackTimer(self.scheduler, changed=self._timer_changed,
                                      expired=self._timer_expired, clock=lambda: monotonic())
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
            if self.panel.isVisible():
                self.panel.hide()
                return
            self._position_panel()
            self.panel.show()
            self.panel.raise_()
            return
        self.panel = qt.QDialog(self.owner, qt.Qt.WindowType.Popup)
        prevent_reader_popup_replay(self.panel)
        self.panel.setWindowTitle('Read aloud')
        self.panel.setModal(False)
        layout = qt.QVBoxLayout(self.panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        self.message = qt.QLabel('Reads selected text, or ' + self.scope + '.')
        self.message.setWordWrap(True)
        header = qt.QHBoxLayout()
        header.addWidget(qt.QLabel('Speed'))
        header.addStretch()
        self.speed_value = qt.QLabel('100%')
        font = self.speed_value.font(); font.setBold(True); self.speed_value.setFont(font)
        header.addWidget(self.speed_value)
        layout.addLayout(header)
        speed_row = qt.QHBoxLayout()
        self.speed = qt.QSlider(qt.Qt.Orientation.Horizontal)
        self.speed.setRange(50, 200)
        self.speed.setSingleStep(25); self.speed.setPageStep(25)
        self.speed.setTickInterval(25)
        self.speed.setTickPosition(qt.QSlider.TickPosition.TicksBelow)
        self.speed.setValue(100)
        self.speed.setAccessibleName('Reading speed')
        for label, widget in (('50%', self.speed), ('200%', None)):
            limit = qt.QLabel(label)
            limit.setForegroundRole(qt.QPalette.ColorRole.PlaceholderText)
            font = limit.font(); font.setPointSizeF(max(8, font.pointSizeF() - 2)); limit.setFont(font)
            speed_row.addWidget(limit)
            if widget is not None: speed_row.addWidget(widget, 1)
        layout.addLayout(speed_row)
        timer_row = qt.QHBoxLayout()
        timer_row.addWidget(qt.QLabel('Sleep timer'))
        self.timer_choice = qt.QComboBox()
        for label, seconds in (('Off', 0), ('15 min', 900), ('30 min', 1800), ('45 min', 2700), ('1 hr', 3600)):
            self.timer_choice.addItem(label, seconds)
        self.timer_choice.setAccessibleName('Sleep timer duration')
        timer_row.addWidget(self.timer_choice, 1)
        self.reset_timer_button = reader_button(self.panel, 'Reset timer', icon='reset')
        self.reset_timer_button.setEnabled(False)
        timer_row.addWidget(self.reset_timer_button)
        layout.addLayout(timer_row)
        self.timer_label = qt.QLabel('Timer off')
        font = self.timer_label.font(); font.setBold(True); self.timer_label.setFont(font)
        layout.addWidget(self.timer_label)
        self.timer_choice.currentIndexChanged.connect(self._select_timer)
        self.reset_timer_button.clicked.connect(self.reset_timer)
        self.speed.valueChanged.connect(self._speed_changed)
        self.speed.sliderReleased.connect(lambda: self._speed_changed(self.speed.value()))
        row = self.playback_row = qt.QHBoxLayout()
        self.back = reader_button(self.panel, 'Back 15 seconds', icon='back15')
        self.forward = reader_button(self.panel, 'Forward 15 seconds', icon='forward15')
        for button in (self.back, self.forward):
            button.setToolTip(button.accessibleName() + ' (approximate text position)')
        self.read = reader_button(self.panel, 'Play', icon='play')
        self.pause = self.read  # Preserve the existing handle for shared consumers.
        self.stop_button = reader_button(self.panel, 'Stop', icon='stop')
        for button, callback in ((self.back, lambda: self.skip(-15)), (self.read, self.toggle_playback),
                                 (self.forward, lambda: self.skip(15)), (self.stop_button, self.stop)):
            button.setMinimumSize(44, 44)
            row.addWidget(button, 1)
            button.clicked.connect(callback)
        layout.addLayout(row)
        layout.addWidget(self.message)
        form = qt.QFormLayout()
        self.language, self.voice = qt.QComboBox(), qt.QComboBox()
        for label, widget in (('Language', self.language), ('Voice', self.voice)):
            widget.setMinimumHeight(32)
            form.addRow(label, widget)
        layout.addLayout(form)
        try:
            from PySide6.QtTextToSpeech import QTextToSpeech
            self.speech_type = QTextToSpeech
            if self.engine_factory is None and not QTextToSpeech.availableEngines():
                raise RuntimeError('No system speech engine is installed.')
            self.engine = (self.engine_factory or QTextToSpeech)(self)
            self.adapter = QtSpeechEngine(self.engine, QTextToSpeech, self.scheduler)
            self.session = SpeechSession(self.adapter, on_range=self._range_changed,
                                         on_state=self._session_state, clock=lambda: monotonic())
            self.session.on_finished = lambda: self.on_finished() if not self._selected_passage else None
            self.engine.errorOccurred.connect(lambda *args: self._error())
            self.engine.stateChanged.connect(lambda state: self._error() if state == QTextToSpeech.State.Error else None)
            self.language.addItem('Automatic (detect text)', None)
            self._default_locale = self.engine.locale()
            for locale in self.engine.availableLocales():
                self.language.addItem(locale.nativeLanguageName() + ' — ' + locale.name(), locale)
            self.language.currentIndexChanged.connect(self._language_changed)
            self._voices()
            self.voice.currentIndexChanged.connect(self._voice_changed)
            self.engine.setRate(0)
            self._session_state(self.session.state, 'Ready — select text to read just that selection.')
        except (ImportError, RuntimeError) as error:
            self.message.setText(f'Read aloud is unavailable: {error}')
            self.read.setEnabled(False)
            self.pause.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.back.setEnabled(False); self.forward.setEnabled(False)
        self.panel.resize(380, self.panel.sizeHint().height())
        self._position_panel()
        self.panel.show()

    def _speed_changed(self, value):
        value = max(50, min(200, 50 + round((value - 50) / 25) * 25))
        self.speed.blockSignals(True)
        self.speed.setValue(value)
        self.speed.blockSignals(False)
        self.speed_value.setText(f'{value}%')
        if self.session is not None:
            self.session.set_speed(value / 100)
            self.adapter.set_speed(value / 100)

    def _select_timer(self):
        duration = self.timer_choice.currentData()
        self.reset_timer_button.setEnabled(bool(duration))
        self.playback.select(duration)

    def reset_timer(self):
        self.playback.reset()

    def _timer_changed(self, remaining):
        if self.panel is None:
            return
        minutes, seconds = divmod(math.ceil(remaining), 60)
        self.timer_label.setText(f'Time remaining: {minutes:02d}:{seconds:02d}' if self.playback.duration else 'Timer off')

    def _timer_expired(self):
        if self.session is not None:
            self.session.pause()
        self.message.setText('Timer finished · Play to start a new timer.')

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
        self.voice.setEnabled(self.language.currentData() is not None)

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
        self._selected_passage = cursor is not None and cursor.hasSelection()
        base = cursor.selectionStart() if cursor is not None and cursor.hasSelection() else (
            self.start_provider() if self.start_provider else visible_text_start(widget) if widget is not None else 0)
        text = reader_text(widget, start=0) if widget is not None and not cursor.hasSelection() else self.text_provider()
        source_base = 0 if widget is not None and not cursor.hasSelection() else base
        self.stop()
        self._source_base = source_base
        self._highlight_widget = widget
        if self.language.currentData() is None:
            start = max(0, base - source_base)
            sample = text.encode('utf-16-le')[start * 2:].decode('utf-16-le')
            language = passage_language(sample, self.language_provider())
            locales = {locale.name(): locale for locale in self.engine.availableLocales()}
            tag = matching_locale(language, locales, self._default_locale.name())
            if language and not tag:
                self.message.setText(f'No installed voice for {language}. Install a system voice or choose a language manually.')
                return
            self.engine.setLocale(locales[tag] if tag else self._default_locale)
            self._voices()
        self.session.play(text, max(0, base - source_base), speed=self.speed.value() / 100)

    @property
    def _position(self):
        return self._source_base + getattr(self.session, 'position', 0)

    @property
    def _speaking(self):
        return self.session is not None and self.session.state in {'speaking', 'paused'}

    def _range_changed(self, start, end):
        if start < 0:
            widget = self._highlight_widget
            self._clear_highlight()
            self._highlight_widget = widget
        else:
            self._highlight(self._source_base + start, end - start)

    def skip(self, seconds):
        if self.session is not None:
            self.session.skip(seconds)

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

    def _session_state(self, state, message):
        speaking, paused = state == 'speaking', state == 'paused'
        self.playback.set_running(speaking)
        if self.panel is None:
            return
        label = 'Pause' if speaking else 'Resume' if paused else 'Play'
        self.pause.setText(label)
        self.pause.setToolTip(label)
        self.pause.setAccessibleName(label)
        set_painted_icon(self.pause, ReaderIcon, 'pause' if speaking else 'play')
        capable = bool(self.engine.engineCapabilities() & self.speech_type.Capability.PauseResume)
        self.read.setEnabled(state != 'unavailable' and (capable or not (speaking or paused)))
        self.stop_button.setEnabled(speaking or paused)
        for button in (self.back, self.forward):
            button.setEnabled(speaking or paused)
        for control in (self.language, self.voice):
            control.setEnabled(not speaking and not paused)
        self.voice.setEnabled(not speaking and not paused and self.language.currentData() is not None)
        self.message.setText(message)

    def _error(self):
        if self.session is not None:
            self.session.stop()
        self._session_state('unavailable', 'Read aloud is unavailable: ' +
                            (self.engine.errorString() or 'The system speech engine failed.'))

    def toggle_playback(self):
        if self.session is not None:
            if self.session.state in {'speaking', 'paused'}:
                self.toggle_pause()
            else:
                self.start()

    def toggle_pause(self):
        if self.session is not None:
            if self.session.state == 'paused':
                self.session.resume()
            else:
                self.session.pause()

    def stop(self):
        if self.session is not None:
            self.session.stop()
        self.playback.set_running(False)
        self._clear_highlight()
