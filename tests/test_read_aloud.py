"""Speech queue/lifetime tests use a silent engine, never the user's speakers."""
import unittest
from commonUtils.ui import pyside as qt
from commonUtils.ui.read_aloud import ReadAloud, reader_text, speech_chunks
from PySide6.QtTextToSpeech import QTextToSpeech as Speech


class SilentEngine(qt.QObject):
    stateChanged = qt.Signal(object)
    errorOccurred = qt.Signal(object)
    sayingWord = qt.Signal(str, int, int, int)

    def __init__(self, parent):
        super().__init__(parent)
        self.current = Speech.State.Ready
        self.spoken = []
    def state(self): return self.current
    def availableLocales(self): return []
    def availableVoices(self): return []
    def locale(self): return qt.QLocale()
    def voice(self): return None
    def setRate(self, value): pass
    def engineCapabilities(self): return Speech.Capability.PauseResume
    def errorString(self): return 'Test backend unavailable'
    def change(self, state):
        self.current = state
        self.stateChanged.emit(state)
    def say(self, text):
        self.spoken.append(text)
        self.change(Speech.State.Speaking)
    def stop(self): self.change(Speech.State.Ready)
    def pause(self): self.change(Speech.State.Paused)
    def resume(self): self.change(Speech.State.Speaking)


class SpeechTests(unittest.TestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.owner = qt.QWidget()
        self.owner.show()
        self.addCleanup(self.owner.close)
        self.addCleanup(self.owner.deleteLater)

    def speech(self, text):
        speech = ReadAloud(self.owner, lambda: text, engine_factory=SilentEngine)
        self.assertIsNone(speech.engine)
        speech.show()
        return speech

    def test_queue_pause_and_stop_cancel_scheduled_next_utterance(self):
        speech = self.speech('A sentence. ' * 800)
        speech.start()
        self.assertEqual(len(speech.engine.spoken), 1)
        speech.toggle_pause()
        self.assertEqual(speech.engine.state(), Speech.State.Paused)
        self.assertEqual(speech.pause.text(), 'Resume')
        speech.toggle_pause()
        speech.engine.change(Speech.State.Ready)
        self.app.processEvents()
        self.assertEqual(len(speech.engine.spoken), 2)
        speech.engine.change(Speech.State.Ready)
        speech.stop()
        self.app.processEvents()
        self.assertEqual(len(speech.engine.spoken), 2)
        self.assertFalse(speech.pending)

    def test_close_panel_or_reader_stops_and_backend_errors_are_visible(self):
        speech = self.speech('Some text')
        speech.start()
        speech.panel.close()
        self.assertEqual(speech.engine.state(), Speech.State.Ready)
        speech.show()
        speech.start()
        self.owner.hide()
        self.assertEqual(speech.engine.state(), Speech.State.Ready)
        speech.engine.change(Speech.State.Error)
        self.assertIn('Test backend unavailable', speech.message.text())
        self.assertFalse(speech.read.isEnabled())

    def test_missing_engine_and_no_pause_capability_keep_panel_usable(self):
        def unavailable(parent):
            raise RuntimeError('No speech service')
        missing = ReadAloud(self.owner, lambda: 'hello', engine_factory=unavailable)
        missing.show()
        self.assertIn('No speech service', missing.message.text())
        self.assertFalse(missing.read.isEnabled())
        speech = self.speech('hello')
        speech.engine.engineCapabilities = lambda: Speech.Capability(0)
        speech.start()
        self.assertFalse(speech.pause.isEnabled())
        self.assertTrue(speech.stop_button.isEnabled())

    def test_chunks_and_selected_text_preserve_unicode_and_words(self):
        text = ('paragraph café\n' * 300) + '😀 done'
        chunks = list(speech_chunks(text))
        self.assertTrue(all(len(chunk) <= 3000 for chunk in chunks))
        self.assertEqual(' '.join(' '.join(chunk.split()) for chunk in chunks), ' '.join(text.split()))
        widget = qt.QTextBrowser()
        widget.setPlainText('First\nSecond')
        self.assertEqual(reader_text(widget, start=6), 'Second')
        cursor = widget.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(5, qt.QTextCursor.MoveMode.KeepAnchor)
        widget.setTextCursor(cursor)
        self.assertEqual(reader_text(widget, start=6), 'First')

    def test_popup_word_highlighting_preserves_selection_and_unicode_offsets(self):
        widget = qt.QTextBrowser(self.owner)
        widget.setPlainText('Before 😀\nRead café here.')
        cursor = widget.textCursor()
        start = len('Before 😀\n'.encode('utf-16-le')) // 2
        cursor.setPosition(start)
        cursor.movePosition(qt.QTextCursor.MoveOperation.End, qt.QTextCursor.MoveMode.KeepAnchor)
        widget.setTextCursor(cursor)
        speech = ReadAloud(self.owner, lambda: reader_text(widget), text_widget=widget, engine_factory=SilentEngine)
        speech.show()
        self.assertTrue(speech.panel.windowFlags() & qt.Qt.WindowType.Popup)
        speech.engine.engineCapabilities = lambda: Speech.Capability.WordByWordProgress
        speech.start()
        speech.engine.sayingWord.emit('café', 0, 5, 4)
        selections = widget.extraSelections()
        highlight = selections[0].cursor
        self.assertEqual(highlight.selectedText(), 'café')
        self.assertEqual(highlight.selectionStart(), start + 5)
        self.assertEqual(widget.textCursor().selectedText(), 'Read café here.')
        speech.stop()
        self.assertEqual(widget.extraSelections(), [])

    def test_later_utterance_highlight_tracks_source_after_trimmed_whitespace(self):
        widget = qt.QTextBrowser(self.owner)
        widget.setPlainText('  😀 paragraph.\n' * 400 + 'Last word.')
        speech = ReadAloud(self.owner, lambda: reader_text(widget), text_widget=widget, engine_factory=SilentEngine)
        speech.show(); speech.start()
        speech.engine.change(Speech.State.Ready); self.app.processEvents()
        speech.engine.sayingWord.emit('😀', 0, 0, 2)
        selections = widget.extraSelections()
        cursor = selections[0].cursor
        self.assertEqual(cursor.selectedText(), '😀')
        self.assertGreater(cursor.selectionStart(), 300)
