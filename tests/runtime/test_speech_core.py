"""Reusable speech cancellation and range contracts without any UI toolkit."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from commonUtils.runtime.speech import SpeechSession, utterances, PlaybackTimer


class SpeechCoreTests(unittest.TestCase):
    def test_prose_dash_payload_and_native_ranges_use_original_utf16_positions(self):
        from commonUtils.runtime.speech_text import utf16_length
        engine = SimpleNamespace(ready=True, error='', speak=Mock(), stop=Mock(), close=Mock())
        ranges = Mock()
        session = SpeechSession(engine, on_range=ranges, on_state=Mock())
        source = '😀 café Sumire—Never–again―today.'
        session.play(source)
        spoken = engine.speak.call_args.args[0]
        self.assertEqual(spoken, '😀 café Sumire — Never – again ― today.')
        for word in ('Sumire', 'Never', 'again', 'today'):
            start = utf16_length(spoken[:spoken.index(word)])
            engine.progress(session.token, start, start + len(word))
            original = utf16_length(source[:source.index(word)])
            self.assertEqual(ranges.call_args.args, (original, original + len(word)))
        # Generated spaces and dash-only events must not become cursor words.
        previous = ranges.call_count
        start = utf16_length(spoken[:spoken.index('—')])
        engine.progress(session.token, start - 1, start)
        engine.progress(session.token, start, start + 1)
        self.assertEqual(ranges.call_count, previous)
        engine.progress(session.token, 0, 10000)
        self.assertEqual(ranges.call_count, previous)
        session.play('Intro. Sumire—Never', breaks=(7,))
        engine.completed(session.token)
        self.assertEqual(engine.speak.call_args.args[0], 'Sumire — Never')
        engine.progress(session.token, 9, 14)
        self.assertEqual(ranges.call_args.args, (14, 19))
        engine.progress(session.token, 0, 14)
        self.assertEqual(ranges.call_args.args, (7, 13))
        session.dispose()
        self.assertIsNone(session.spoken)
        self.assertEqual(session.text, '')

    def test_dash_fallback_pause_resume_selection_and_limits_keep_source_anchors(self):
        from commonUtils.runtime.speech_text import SpeechText, word_ranges
        engine = SimpleNamespace(ready=True, error='', speak=Mock(), stop=Mock(), close=Mock())
        ranges = Mock()
        session = SpeechSession(engine, on_range=ranges, on_state=Mock())
        session.play('Sumire—Never again')
        engine.started(session.token)
        self.assertEqual(session.utterance_words, [(0, 6), (7, 12), (13, 18)])
        session.estimated_word(session.token, 1)
        self.assertEqual(ranges.call_args.args, (7, 12))
        session.pause()
        session.resume()
        self.assertEqual(engine.speak.call_args.args[0], 'Never again')
        session.play('😀 Sumire—Never again', 10, 15)
        self.assertEqual(engine.speak.call_args.args[0], 'Never')
        source = 'Sumire—Never–again―today ' * 20
        chunks = list(utterances(source, limit=24))
        self.assertTrue(all(len(SpeechText(text).text) <= 24 for text, _, _ in chunks))
        self.assertEqual(''.join(text for text, _, _ in chunks).replace(' ', ''), source.replace(' ', ''))
        unchanged = "well-known non‑breaking don't l’amour 10–12 −5 3.14 https://a-b.test"
        self.assertEqual(SpeechText(unchanged).text, unchanged)
        self.assertEqual(len(list(word_ranges(unchanged))), 8)
        session.dispose()

    def test_natural_finish_can_chain_but_stop_failure_and_stale_callbacks_cannot(self):
        engine = SimpleNamespace(ready=True, error='', speak=Mock(), stop=Mock(), close=Mock())
        session = SpeechSession(engine, on_range=Mock(), on_state=Mock())
        finished = session.on_finished = Mock()
        session.play('First chapter')
        old = session.token
        session.completed(old)
        finished.assert_called_once_with()
        session.completed(old)
        session.stop()
        session.play('Second chapter')
        session.failed(session.token)
        self.assertEqual(finished.call_count, 1)
        session.play('   ')
        self.assertEqual(finished.call_count, 2)
        session.dispose()

    def test_utf16_selection_and_bounds_preserve_astral_offsets(self):
        self.assertEqual(list(utterances("A😀 B", 1, 3)), [("😀", 1, 3)])
        chunks = list(utterances("one two three four", limit=7))
        self.assertTrue(all(end - start <= 7 for _, start, end in chunks))
        self.assertEqual(
            "".join(part for part, _, _ in chunks).replace(" ", ""), "onetwothreefour"
        )

    def test_cancelled_generation_and_disposed_engine_cannot_publish(self):
        engine = SimpleNamespace(
            ready=True, error="", speak=Mock(), stop=Mock(), close=Mock()
        )
        ranges, states = Mock(), Mock()
        session = SpeechSession(
            engine, on_range=ranges, on_state=states, clock=lambda: 100
        )
        session.play("First passage", voice="offline")
        token = session.token
        session.play("Replacement", voice="offline")
        ranges.reset_mock()
        engine.progress(token, 0, 5)
        engine.completed(token)
        ranges.assert_not_called()
        session.dispose()
        ranges.reset_mock()
        engine.progress(session.token, 0, 4)
        ranges.assert_not_called()
        engine.close.assert_called_once()

    def test_sleep_budget_uses_the_injected_clock_and_stops_scheduling(self):
        now = [100]
        loop = SimpleNamespace(call_later=Mock(return_value=Mock()))
        expired = Mock()
        timer = PlaybackTimer(
            loop, changed=Mock(), expired=expired, clock=lambda: now[0]
        )
        timer.select(10)
        timer.set_running(True)
        now[0] = 111
        timer._tick()
        expired.assert_called_once()
        self.assertFalse(timer.running)
        timer.dispose()
        self.assertIsNone(timer.handle)

    def test_pause_speed_skip_and_late_completion_use_one_transition_owner(self):
        now = [100]
        engine = SimpleNamespace(ready=True, error='', speak=Mock(), stop=Mock(), close=Mock())
        ranges, states = Mock(), Mock()
        session = SpeechSession(engine, on_range=ranges, on_state=states, clock=lambda: now[0])
        session.play(' '.join(f'word{i}😀' for i in range(100)))
        first = session.token
        engine.started(first)
        engine.progress(first, 0, 7)
        session.pause()
        session.skip(15)
        self.assertEqual(session.state, 'paused')
        self.assertTrue(session.ranges[0][0].startswith('word45😀'))
        session.set_speed(1.5)
        session.resume()
        current = session.token
        self.assertNotEqual(current, first)
        count = engine.speak.call_count
        engine.completed(first)
        self.assertEqual(engine.speak.call_count, count)
        session.can_speak = lambda: False
        engine.completed(current)
        self.assertEqual(session.state, 'stopped')
        session.dispose()

    def test_media_preparation_pause_or_revocation_prevents_utterance_submission(self):
        for mode in ('pause', 'revoke'):
            engine = SimpleNamespace(ready=True, error='', speak=Mock(), stop=Mock(), close=Mock())
            allowed = [True]
            def changed(state, message):
                if state == 'speaking':
                    if mode == 'pause':
                        session.pause()
                    else:
                        allowed[0] = False
            session = SpeechSession(engine, on_range=Mock(), on_state=changed)
            session.can_speak = lambda: allowed[0]
            session.play('Never submit this after route revocation.')
            engine.speak.assert_not_called()
            self.assertIn(session.state, {'paused', 'stopped'})
            session.dispose()

    def test_native_paused_utterance_rechecks_permission_before_resume(self):
        engine = SimpleNamespace(ready=True, error='', speak=Mock(), stop=Mock(), close=Mock(),
                                 pause_utterance=lambda: True, resume_utterance=Mock())
        session = SpeechSession(engine, on_range=Mock(), on_state=Mock())
        session.play('A paused native utterance remains subject to permission.')
        session.pause()
        self.assertTrue(session.native_paused)
        session.can_speak = lambda: False
        session.resume()
        engine.resume_utterance.assert_not_called()
        self.assertEqual(session.state, 'paused')
        session.dispose()
