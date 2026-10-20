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
