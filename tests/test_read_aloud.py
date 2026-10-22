"""Speech queue/lifetime tests use a silent engine, never the user's speakers."""
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.readers.read_aloud import ReadAloud, reader_text, speech_chunks, visible_text_start
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


class SpeechTests(QtTestCase):
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

    def test_speed_detents_and_timer_follow_play_pause_reset_and_expiry(self):
        from unittest.mock import patch
        speech = self.speech('word ' * 200)
        self.assertEqual(speech.speed.value(), 100)
        speech.speed.setValue(138)
        self.assertEqual(speech.speed.value(), 150)
        self.assertEqual(speech.speed_value.text(), '150%')
        self.assertEqual([speech.playback_row.itemAt(i).widget().accessibleName() for i in range(4)],
                         ['Back 15 seconds', 'Play', 'Forward 15 seconds', 'Stop'])
        with patch('commonUtils.ui.readers.read_aloud.monotonic') as clock:
            clock.return_value = 100
            speech.timer_choice.setCurrentIndex(1)
            self.assertEqual(speech.timer_label.text(), 'Time remaining: 15:00')
            self.assertFalse(speech.playback.handle is not None)
            speech.start()
            clock.return_value = 110
            speech.playback._tick()
            self.assertEqual(speech.timer_label.text(), 'Time remaining: 14:50')
            speech.toggle_pause()
            clock.return_value = 500
            speech.playback._tick()
            self.assertEqual(speech.timer_label.text(), 'Time remaining: 14:50')
            speech.reset_timer_button.click()
            self.assertEqual(speech.timer_label.text(), 'Time remaining: 15:00')
            self.assertEqual(speech.engine.state(), Speech.State.Paused)
            speech.toggle_pause()
            clock.return_value = 1401
            speech.playback._tick()
            self.assertEqual(speech.engine.state(), Speech.State.Paused)
            self.assertEqual(speech.timer_label.text(), 'Time remaining: 00:00')
            self.assertIn('Timer finished', speech.message.text())
            speech.toggle_pause()
            self.assertEqual(speech.timer_label.text(), 'Time remaining: 15:00')
            speech.timer_choice.setCurrentIndex(0)
            self.assertEqual(speech.timer_label.text(), 'Timer off')
            self.assertFalse(speech.reset_timer_button.isEnabled())

    def test_skip_clears_mirrored_ranges_before_replacement_and_preserves_other_marks(self):
        widget = qt.QTextBrowser(self.owner)
        widget.setPlainText(' '.join(f'word{i}' for i in range(200)))
        mark = qt.QTextEdit.ExtraSelection()
        mark.cursor = widget.textCursor()
        mark.format.setProperty(qt.QTextFormat.Property.UserProperty + 78, True)
        widget.setExtraSelections([mark])
        speech = ReadAloud(self.owner, lambda: reader_text(widget), text_widget=widget, engine_factory=SilentEngine)
        speech.show(); speech.start()
        changes = []
        speech.positionChanged.connect(lambda *value: changes.append(value))
        speech.skip(15)
        self.assertEqual(changes[0], (-1, -1))
        self.assertEqual(changes[-1][0], speech._position)
        selections = widget.extraSelections()
        self.assertEqual(len(selections), 2)
        self.assertTrue(selections[0].format.property(qt.QTextFormat.Property.UserProperty + 78))
        self.assertEqual(selections[1].cursor.selectedText(), 'word45')
        speech.stop()
        self.assertEqual(len(widget.extraSelections()), 1)

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
        speech.session.estimated_word(speech.session.token, 1)
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
        self.assertEqual(speech.session.state, 'paused')
        self.assertTrue(speech.session.ranges[0][0].startswith('word0😀'))
        speech.stop()
        self.assertFalse(speech.session.word_timer is not None)
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
        self.assertFalse(speech.session.word_timer is not None)

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
        self.assertFalse(speech.session.ranges)

    def test_single_playback_button_starts_pauses_resumes_and_resets(self):
        speech = self.speech('A sentence. ' * 800)
        controls = speech.playback_row
        self.assertEqual(controls.count(), 4)
        self.assertIs(speech.pause, speech.read)
        self.assertEqual(speech.read.accessibleName(), 'Play')
        speech.read.click()
        pending = list(speech.session.ranges)
        self.assertEqual(speech.engine.state(), Speech.State.Speaking)
        self.assertEqual(speech.read.accessibleName(), 'Pause')
        speech.read.click()
        self.assertEqual(speech.engine.state(), Speech.State.Paused)
        self.assertEqual(speech.read.toolTip(), 'Resume')
        speech.read.click()
        self.assertEqual(speech.engine.state(), Speech.State.Speaking)
        self.assertEqual(len(speech.engine.spoken), 1)
        self.assertEqual(list(speech.session.ranges), pending)
        speech.stop_button.click()
        self.assertEqual(speech.read.accessibleName(), 'Play')
        self.assertTrue(speech.read.isEnabled())
        speech.read.click()
        self.assertEqual(len(speech.engine.spoken), 2)
        del speech.session.ranges[speech.session.index + 1:]
        speech.engine.change(Speech.State.Ready)
        self.app.processEvents()
        self.assertEqual(speech.read.accessibleName(), 'Play')
        speech.engine.change(Speech.State.Error)
        self.assertFalse(speech.read.isEnabled())

    def test_dismissing_controls_keeps_playback_until_reader_hides(self):
        speech = self.speech('Some text')
        self.assertFalse(any(button.text() == '×' or button.accessibleName() == 'Close read aloud'
                             for button in speech.panel.findChildren(qt.QToolButton)))
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
        speech.stop_button.click()
        self.assertTrue(speech.read.isEnabled())
        self.assertEqual(speech.read.accessibleName(), 'Play')

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
