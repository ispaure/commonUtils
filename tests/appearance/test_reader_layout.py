"""Safe-edge placement without duplicating native insets or guessing devices."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest
from commonUtils.ui.readers.layout import remaining_clearance, rounded_clearance, overlay_insets


class ReaderLayoutTests(unittest.TestCase):
    def test_already_consumed_home_inset_is_not_reserved_twice(self):
        self.assertEqual(remaining_clearance(800, 766), 34)
        self.assertEqual(remaining_clearance(766, 766), 0)
        self.assertEqual(remaining_clearance(600, 766), 0)

    def test_round_corners_trim_only_the_intersecting_row(self):
        corners = [(False, True, 40, 760, 40), (True, True, 360, 760, 40)]
        self.assertEqual(rounded_clearance(700, 740, corners), (0, 400))
        self.assertEqual(rounded_clearance(752, 800, corners), (40, 360))
        left, right = rounded_clearance(740, 784, corners)
        self.assertAlmostEqual(left, 8)
        self.assertAlmostEqual(right, 392)

    def test_vertical_progress_uses_the_same_corner_rule(self):
        corners = [(False, True, 360, 40, 40), (True, True, 360, 760, 40)]
        self.assertEqual(rounded_clearance(352, 400, corners, vertical=True), (40, 760))

    def test_system_safe_insets_and_round_corners_merge_instead_of_adding(self):
        corners = [(False, True, 40, 760, 40), (True, True, 360, 760, 40)]
        self.assertEqual(overlay_insets(400, 800, (0, 24, 0, 0), corners), (52, 36, 52, 0))
        self.assertEqual(overlay_insets(400, 800, (48, 24, 48, 0), corners), (60, 36, 60, 0))
        self.assertEqual(overlay_insets(400, 800, (0, 24, 0, 40), corners), (12, 36, 12, 40))

    def test_missing_corner_metadata_keeps_system_geometry(self):
        self.assertEqual(overlay_insets(400, 800, (0, 24, 0, 34)), (12, 36, 12, 34))
