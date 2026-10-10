"""Speech queue/lifetime tests use a silent engine, never the user's speakers."""
import unittest
from commonUtils.ui import pyside as qt
from commonUtils.ui.read_aloud import ReadAloud, reader_text, speech_chunks, visible_text_start
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

    def test_speech_starts_at_visible_text_and_highlights_one_word(self):
        widget = qt.QTextBrowser(self.owner)
        widget.resize(240, 120)
        widget.setPlainText('\n'.join(f'Line {number} words here' for number in range(80)))
        widget.show(); self.app.processEvents()
        widget.verticalScrollBar().setValue(widget.verticalScrollBar().maximum() // 2)
        base = visible_text_start(widget)
        self.assertGreater(base, 0)
        speech = ReadAloud(self.owner, lambda: reader_text(widget), text_widget=widget, engine_factory=SilentEngine)
        speech.show(); speech.start()
        self.assertTrue(speech.engine.spoken[0].startswith(reader_text(widget, start=base).strip()[:20]))
        selections = widget.extraSelections()
        self.assertLess(len(selections[0].cursor.selectedText()), 15)
        self.assertGreaterEqual(selections[0].cursor.selectionStart(), base)
        speech._estimated_word()
        selections = widget.extraSelections()
        self.assertLess(len(selections[0].cursor.selectedText()), 15)

    def test_skip_moves_both_directions_and_preserves_pause_and_unicode_offsets(self):
        widget = qt.QTextBrowser(self.owner)
        widget.setPlainText(' '.join(f'word{number}😀' for number in range(200)))
        speech = ReadAloud(self.owner, lambda: reader_text(widget), text_widget=widget, engine_factory=SilentEngine)
        speech.show(); speech.start()
        speech.skip(15)
        self.assertTrue(speech.engine.spoken[-1].startswith('word45😀'))
        selections = widget.extraSelections()
        self.assertEqual(selections[0].cursor.selectedText(), 'word45😀')
        speech.toggle_pause(); speech.skip(-15)
        self.assertEqual(speech.engine.state(), Speech.State.Paused)
        self.assertTrue(speech.engine.spoken[-1].startswith('word0😀'))
        speech.stop()
        self.assertFalse(speech.word_timer.isActive())
        self.assertFalse(speech.back.isEnabled())
        self.assertFalse(speech.forward.isEnabled())

    def test_native_word_progress_never_highlights_the_entire_utterance(self):
        widget = qt.QTextBrowser(self.owner)
        widget.setPlainText('A long paragraph. ' * 200)
        speech = ReadAloud(self.owner, lambda: reader_text(widget), text_widget=widget, engine_factory=SilentEngine)
        speech.show()
        speech.engine.engineCapabilities = lambda: Speech.Capability.WordByWordProgress
        speech.start()
        self.assertGreater(len(speech.engine.spoken[0]), 1000)
        selections = widget.extraSelections()
        self.assertEqual(selections[0].cursor.selectedText(), 'A')
        speech.engine.sayingWord.emit('paragraph', 0, 7, 9)
        selections = widget.extraSelections()
        self.assertEqual(selections[0].cursor.selectedText(), 'paragraph')
        self.assertFalse(speech.word_timer.isActive())

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

    def test_dismissing_controls_keeps_playback_until_reader_hides(self):
        speech = self.speech('Some text')
        speech.start()
        speech.panel.close()
        self.assertEqual(speech.engine.state(), Speech.State.Speaking)
        self.assertTrue(speech._speaking)
        for control in (speech.read, speech.pause, speech.stop_button):
            self.assertEqual(control.toolButtonStyle(), qt.Qt.ToolButtonStyle.ToolButtonIconOnly)
            self.assertFalse(control.icon().isNull())
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
