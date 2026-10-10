"""Keyword/phrase matching stays identical for SQL and detached snapshots."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.directory import DirectoryCache, Snapshot
from commonUtils.operations import OperationCancelled


class SearchTermTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        root = base / 'files'
        root.mkdir()
        names = ('this_that.txt', 'That THIS.txt', 'this---that.png',
                 'THIS   THAT.txt', 'this something that.txt', 'this-only.txt',
                 'Straße_Two.txt', 'this%_that.txt')
        for number, name in enumerate(names):
            (root / name).write_bytes(b'x' * (number + 1))
        indexed = DirectoryCache(database=base / 'cache' / 'index.sqlite3').get(root)
        self.addCleanup(indexed.close)
        detached = Snapshot(root, True, tuple(indexed.entries), (), indexed.scanned_at)
        self.snapshots = (indexed, detached)

    def assertMatches(self, query, expected):
        for snapshot in self.snapshots:
            self.assertEqual({entry.path.name for entry in snapshot.search(query)}, set(expected))
            page, count = snapshot.search_page(query)
            self.assertEqual(count, len(expected))
            self.assertEqual({entry.path.name for entry in page}, set(expected))

    def test_keywords_match_in_any_order_ignoring_case(self):
        self.assertMatches('THAT this', ('this_that.txt', 'That THIS.txt', 'this---that.png',
                           'THIS   THAT.txt', 'this something that.txt', 'this%_that.txt'))

    def test_phrases_keep_adjacent_order_with_equivalent_separators(self):
        expected = ('this_that.txt', 'this---that.png', 'THIS   THAT.txt')
        self.assertMatches('"THIS that"', expected)
        self.assertMatches('"this_that"', expected)
        self.assertMatches('"this that', expected)
        self.assertMatches('"this that" TXT', ('this_that.txt', 'THIS   THAT.txt'))

    def test_unicode_casefold_and_literal_punctuation(self):
        self.assertMatches('STRASSE two', ('Straße_Two.txt',))
        self.assertMatches('"strasse two"', ('Straße_Two.txt',))
        self.assertMatches('this%_that', ('this%_that.txt',))
        self.assertMatches('this*', ())

    def test_paging_sorts_filtered_results_and_cancellation_remains_available(self):
        for snapshot in self.snapshots:
            first, count = snapshot.search_page('this that', limit=2, sort='size', descending=True)
            second, count2 = snapshot.search_page('this that', offset=2, limit=2, sort='size', descending=True)
            self.assertEqual((count, count2), (6, 6))
            self.assertTrue(first[-1].size > second[0].size)
            with self.assertRaises(OperationCancelled):
                snapshot.search('"this that"', cancelled=lambda: True)
