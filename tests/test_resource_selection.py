import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.selection import ResourceSelection, ResourceTextSession, ResourceChoice
from commonUtils.runtime.operations import MutationIncomplete


class ResourceSelectionTests(unittest.TestCase):
    def test_navigation_validation_and_private_baseline(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'folder').mkdir()
            (root / 'folder/note.md').write_bytes(b'\xef\xbb\xbfhello\r\n')
            (root / 'skip.bin').write_bytes(b'\x00')
            provider = LocalFiles(root)
            model = ResourceSelection(provider, extensions=('.md',))
            self.assertEqual([row['name'] for row in model.list()], ['folder'])
            self.assertEqual(model.resolve('folder', 'note.md'), 'folder/note.md')
            for bad in ('../note.md', '/note.md', 'a//b.md'):
                with self.assertRaises(ValueError): model.resolve('', bad)
            with self.assertRaises(FileExistsError):
                ResourceSelection(provider, mode='save').resolve('folder', 'note.md')
            session = ResourceTextSession.open(provider, 'folder/note.md')
            saved = session.save('edited\n')
            self.assertEqual((root / 'folder/note.md').read_bytes(), b'\xef\xbb\xbfedited\r\n')
            (root / 'folder/note.md').write_bytes(b'external')
            with self.assertRaises(ValueError): saved.save('stale')
            self.assertEqual((root / 'folder/note.md').read_bytes(), b'external')
            with patch.object(ResourceTextSession, 'open', side_effect=OSError('reopen failed')):
                with self.assertRaises(MutationIncomplete) as error:
                    session.save_as(provider, 'copy.md', 'kept draft')
            self.assertTrue(error.exception.result.destination_published)
            self.assertEqual(session.text.text, 'hello\n')
            self.assertTrue((root / 'copy.md').exists())

    def test_choice_release_is_idempotent_and_read_cancellation(self):
        with TemporaryDirectory() as directory:
            provider = LocalFiles(directory)
            (Path(directory) / 'note.txt').write_text('hello')
            calls = []
            choice = ResourceChoice(provider, 'note.txt', lambda: calls.append(True))
            choice.close(); choice.close()
            self.assertEqual(calls, [True])
            with self.assertRaises(Exception):
                ResourceTextSession.open(provider, 'note.txt', cancelled=lambda: True)

    def test_save_reopen_distinguishes_collision_failure_and_late_cancel(self):
        from threading import Event
        from commonUtils.runtime.resources.mutations import save_resource_and_reopen
        with TemporaryDirectory() as directory:
            provider = LocalFiles(directory)
            path = Path(directory) / 'note.txt'
            cancelled = Event()
            rename = provider.rename
            def publish_then_cancel(source, destination):
                rename(source, destination)
                cancelled.set()
            with patch.object(provider, 'rename', side_effect=publish_then_cancel):
                result = save_resource_and_reopen(provider, 'note.txt', b'published',
                                                 reopen=path.read_bytes, cancelled=cancelled.is_set)
            self.assertEqual(result, b'published')
            with patch.object(Path, 'read_bytes') as reopen:
                with self.assertRaises(FileExistsError):
                    save_resource_and_reopen(provider, 'note.txt', b'collision', reopen=reopen)
                reopen.assert_not_called()
            with self.assertRaises(MutationIncomplete) as error:
                save_resource_and_reopen(provider, 'other.txt', b'keep published copy',
                                         reopen=lambda: (_ for _ in ()).throw(OSError('reader unavailable')))
            self.assertTrue(error.exception.result.destination_published)
            self.assertEqual((Path(directory) / 'other.txt').read_bytes(), b'keep published copy')


class ResourcePathTests(unittest.TestCase):
    def test_virtual_paths_do_not_use_local_filesystem_normalization(self):
        from commonUtils.runtime.resources.paths import resource_path, resource_name
        for value, expected in (('', ''), ('.', ''), ('folder/note', 'folder/note'), ('😀.md', '😀.md')):
            self.assertEqual(resource_path(value), expected)
        for value in ('../escape', '/root', 'C:drive', 'a//b', 'a/./b', 'a/../b', 'a\\b', 'a\x00b'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                resource_path(value)
        for value in ('', '.', 'nested/name', '../outside'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                resource_name(value)
        self.assertEqual(resource_name('😀.md'), '😀.md')
