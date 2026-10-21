"""Toolbar title clearance stays symmetric across phone and tablet layouts."""
import unittest
from commonUtils.ui.native.bars import centered_title_width


class NativeBarTests(unittest.TestCase):
    def test_group_in_another_row_does_not_constrain_title(self):
        self.assertEqual(centered_title_width(500, 1024), 500)

    def test_same_row_group_reserves_equal_clearance_on_both_sides(self):
        self.assertEqual(centered_title_width(300, 400, group_left=330), 212)
        self.assertEqual(centered_title_width(80, 400, group_left=330), 80)
        self.assertEqual(centered_title_width(300, 400, group_left=190), 44)
