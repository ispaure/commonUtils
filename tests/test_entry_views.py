"""Unknown byte sizes stay last in both Qt sorting directions."""
import unittest
from commonUtils.ui.entry_views import value_less, label_less


class EntrySortingTests(unittest.TestCase):
    def test_missing_size_order_and_numeric_values(self):
        self.assertTrue(value_less(10, None))
        self.assertTrue(value_less(None, 10, descending=True))
        self.assertIsNone(value_less(None, None))
        self.assertFalse(value_less(100, 20))
        self.assertIsNone(value_less(None, 0, missing_last=False))
        self.assertTrue(label_less('chapter2', 'chapter10'))
