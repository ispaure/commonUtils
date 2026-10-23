"""The browsing core uses opaque identities and needs no filesystem or UI."""
import unittest
from commonUtils.runtime.browsing import BrowseEntry, BrowseTree


class BrowsingTests(unittest.TestCase):
    def test_json_style_tree_preserves_identity_and_invalidates_changed_children(self):
        root = ('taxonomy', 'root')
        tree = BrowseTree(BrowseEntry(root, 'Animal kingdom', True))
        tree.set_children(root, [BrowseEntry(42, 'Mammals', True, revision=1)])
        tree.set_children(42, [BrowseEntry('species:lion', 'Lion', properties={'habitat': 'Savanna'})])
        self.assertTrue(tree.within('species:lion', root))
        tree.set_children(root, [BrowseEntry(42, 'Mammals', True, revision=1)])
        self.assertIn('species:lion', tree.entries)
        tree.set_children(root, [BrowseEntry(42, 'Mammals', True, revision=2)])
        self.assertNotIn('species:lion', tree.entries)
        self.assertNotIn(42, tree.children)

    def test_invalid_snapshot_keeps_existing_tree(self):
        tree = BrowseTree(BrowseEntry('root', 'Root', True), max_entries=3)
        tree.set_children('root', [BrowseEntry('a', 'A', True)])
        for entries in ([BrowseEntry('a', 'A'), BrowseEntry('a', 'Duplicate')],
                        [BrowseEntry('root', 'Cycle')],
                        [BrowseEntry('a', 'A'), BrowseEntry('b', 'B'), BrowseEntry('c', 'C')]):
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                tree.set_children('root', entries)
            self.assertEqual(tree.children['root'], ('a',))


class RangeValidationTests(unittest.TestCase):
    def test_cached_ranges_still_check_source_lease(self):
        from commonUtils.runtime.resources.range_reader import RangeReader
        locked = False
        def validate():
            if locked:
                raise ValueError('locked')
        with RangeReader(4, lambda offset, count: b'data'[offset:offset + count], validate=validate) as stream:
            self.assertEqual(stream.read(1), b'd')
            locked = True
            with self.assertRaisesRegex(ValueError, 'locked'):
                stream.read(1)
            with self.assertRaisesRegex(ValueError, 'locked'):
                stream.seek(0)


class NavigationTests(unittest.TestCase):
    def test_history_and_snapshot_query_do_not_touch_storage(self):
        from commonUtils.runtime.browsing import BrowseHistory, query_entries
        history = BrowseHistory(max_locations=3)
        history.visit(('Local', ''))
        history.visit(('Local', 'books'))
        history.visit(('Local', 'books'))
        history.visit(('Crypt', ''))
        self.assertEqual(history.previous(), ('Local', 'books'))
        history.visit(('Crypt', 'comics'))
        self.assertEqual(len(history.locations), 3)
        rows = [BrowseEntry(1, 'page10.png', properties={'size': 2}),
                BrowseEntry(2, 'page2.png', properties={'size': 9}),
                BrowseEntry(3, 'Z folder', True)]
        self.assertEqual([entry.identity for entry in query_entries(rows)], [3, 2, 1])
        self.assertEqual([entry.identity for entry in query_entries(rows, 'PAGE', sort='size', descending=True)], [2, 1])
        self.assertEqual([entry.identity for entry in query_entries(rows, sort='name', descending=True)], [3, 1, 2])
        self.assertEqual(query_entries(rows, 'missing'), [])
        self.assertEqual(len(rows), 3)
        history.clear()
        self.assertIsNone(history.current)


class ResourceSearchTests(unittest.TestCase):
    def test_keywords_and_phrases_match_the_folder_projection_and_recursive_scan(self):
        from types import SimpleNamespace
        from commonUtils.runtime.browsing import query_entries
        from commonUtils.search.providers import search_resources
        names = ('The End of Eternityla.epub', 'END_ETERNITY.pdf', 'Eternity End.md', 'Straße.md')
        provider = SimpleNamespace(relative=lambda value: value,
            list=lambda folder, cancelled: [dict(path=name, name=name, directory=False) for name in names])
        entries = [BrowseEntry(name, name) for name in names]
        for query, expected in (
                ('end ETERNITY', set(names[:3])),
                ('"end eternity"', {'END_ETERNITY.pdf'}),
                ('"end of eternity"', {names[0]}),
                ('"end eternity', {'END_ETERNITY.pdf'}),
                ('STRASSE', {'Straße.md'})):
            with self.subTest(query=query):
                self.assertEqual({entry.label for entry in query_entries(entries, query)}, expected)
                self.assertEqual({row['name'] for row in search_resources(provider, '', query).rows}, expected)

    def test_recursive_matches_are_scoped_bounded_and_cancellable(self):
        from types import SimpleNamespace
        from commonUtils.search.providers import search_resources
        from commonUtils.runtime.operations import OperationCancelled
        def listing(path, *, cancelled):
            if path == 'books':
                return [dict(path='books/sub', name='sub', directory=True),
                        dict(path='books/note.txt', name='note.txt', directory=False)]
            return [dict(path='books/sub/Note.md', name='Note.md', directory=False)]
        provider = SimpleNamespace(relative=lambda value: value, list=listing)
        result = search_resources(provider, 'books', 'NOTE')
        self.assertEqual([row['name'] for row in result.rows], ['note.txt', 'sub/Note.md'])
        self.assertTrue(result.complete)
        result = search_resources(provider, 'books', 'note', max_entries=2)
        self.assertFalse(result.complete)
        with self.assertRaises(OperationCancelled):
            search_resources(provider, 'books', 'note', cancelled=lambda: True)


class ProgressiveResourceSearchTests(unittest.TestCase):
    def test_progress_publishes_nested_folder_before_descending_and_detaches_rows(self):
        from types import SimpleNamespace
        from commonUtils.search.providers import search_resources
        reports = []
        def listing(path, *, cancelled):
            if not path:
                return [dict(path='Books', name='Books', directory=True)]
            if path == 'Books':
                return [dict(path='Books/Murakami', name='Murakami', directory=True)]
            self.assertEqual(reports[0].rows[0]['path'], 'Books/Murakami')
            self.assertFalse(reports[0].complete)
            return [dict(path='Books/Murakami/Murakami.epub', name='Murakami.epub', directory=False)]
        provider = SimpleNamespace(relative=lambda value: value, list=listing)
        result = search_resources(provider, '', 'murakami', progress=reports.append)
        self.assertTrue(result.complete)
        self.assertEqual(len(result.rows), 2)
        self.assertEqual(len(reports[0].rows), 1)


class LargeResourceSearchTests(unittest.TestCase):
    def test_default_search_reaches_matches_beyond_ten_thousand_entries(self):
        from types import SimpleNamespace
        from commonUtils.search.providers import search_resources
        def listing(path, *, cancelled):
            if not path:
                return [dict(path=f'file-{i}', name=f'file-{i}', directory=False) for i in range(10001)] + [
                    dict(path='nested', name='nested', directory=True)]
            return [dict(path='nested/needle.pdf', name='needle.pdf', directory=False)]
        provider = SimpleNamespace(relative=lambda value: value, list=listing)
        result = search_resources(provider, '', 'needle')
        self.assertTrue(result.complete)
        self.assertEqual(result.scanned, 10003)
        self.assertEqual(result.rows[0]['path'], 'nested/needle.pdf')
