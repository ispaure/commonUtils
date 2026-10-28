"""Reusable speech cancellation and range contracts without any UI toolkit."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from commonUtils.runtime.speech import SpeechSession, utterances, PlaybackTimer


class SpeechCoreTests(unittest.TestCase):
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
