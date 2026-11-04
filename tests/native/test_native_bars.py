"""Toolbar title clearance stays symmetric across phone and tablet layouts."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest
from commonUtils.ui.native.bars import centered_title_width, android_title_insets


class NativeBarTests(unittest.TestCase):
    def test_group_in_another_row_does_not_constrain_title(self):
        self.assertEqual(centered_title_width(500, 1024), 500)

    def test_same_row_group_reserves_equal_clearance_on_both_sides(self):
        self.assertEqual(centered_title_width(300, 400, group_left=330), 212)
        self.assertEqual(centered_title_width(80, 400, group_left=330), 80)
        self.assertEqual(centered_title_width(300, 400, group_left=190), 44)

    def test_android_title_uses_asymmetric_visible_controls(self):
        for width in (320, 390, 600, 840, 1200):
            self.assertEqual(android_title_insets(width, 2, 1), (96, 48))
        self.assertEqual(android_title_insets(320, 2, 5), (96, 176))
        self.assertEqual(android_title_insets(800, 2, 5), (96, 240))
