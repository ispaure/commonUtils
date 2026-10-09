"""Shared reader wheel gesture policy, including live INI changes."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from commonUtils.ui import pyside as qt
from commonUtils.ui.page_wheel import PageWheel


def wheel(delta, *, pixels=False):
    return qt.QWheelEvent(qt.QPointF(), qt.QPointF(), qt.QPoint(0,delta) if pixels else qt.QPoint(),
                         qt.QPoint() if pixels else qt.QPoint(0,delta), qt.Qt.MouseButton.NoButton,
                         qt.Qt.KeyboardModifier.NoModifier,
                         qt.Qt.ScrollPhase.ScrollUpdate if pixels else qt.Qt.ScrollPhase.NoScrollPhase, False)


class WheelTests(unittest.TestCase):
    def test_sensitivity_reloads_and_touchpad_cooldown_prevents_bursts(self):
        with TemporaryDirectory() as folder:
            path = Path(folder)/'settings.ini'
            path.write_text('[WheelNavigation]\nsensitivity=1\ncooldown_ms=250\n')
            policy = PageWheel()
            with patch('commonUtils.settings.settings_path', return_value=path):
                self.assertEqual(policy.direction(wheel(-3,pixels=True),now=10), 0)
                path.write_text('[WheelNavigation]\nsensitivity=20\ncooldown_ms=250\n')
                self.assertEqual(policy.direction(wheel(-3,pixels=True),now=10.1), 1)
                self.assertEqual(policy.direction(wheel(-100,pixels=True),now=10.2), 0)
                self.assertEqual(policy.direction(wheel(3,pixels=True),now=11), -1)

    def test_snapped_wheel_always_turns_once_per_event(self):
        policy = PageWheel()
        self.assertEqual(policy.direction(wheel(-1),now=10), 1)
        self.assertEqual(policy.direction(wheel(-1200),now=10), 1)
        self.assertEqual(policy.direction(wheel(1),now=10), -1)
