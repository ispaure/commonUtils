
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.selection import ResourceSelection, ResourceTextSession, ResourceChoice
from commonUtils.runtime.operations import MutationIncomplete


class ResourceSelectionTests(unittest.TestCase):
    def test_short_provider_reads_load_complete_text_and_enforce_total_limit(self):
        from contextlib import contextmanager
        from io import BytesIO
        class ShortReads(BytesIO):
            def read(self, size=-1):
                return super().read(min(2, size) if size >= 0 else 2)
        with TemporaryDirectory() as directory:
            provider = LocalFiles(directory)
            data = b'first\nsecond\n'
            (Path(directory) / 'note.txt').write_bytes(data)
            @contextmanager
            def open_short(path):
                with ShortReads(data) as stream:
                    yield stream
            for limit in (100, 4):
                with self.subTest(limit=limit), patch.object(provider, 'open', side_effect=open_short):
                    if limit < len(data):
                        with self.assertRaisesRegex(ValueError, 'memory limit'):
                            ResourceTextSession.open(provider, 'note.txt', max_bytes=limit)
                    else:
                        session = ResourceTextSession.open(provider, 'note.txt', max_bytes=limit)
                        self.assertEqual(session.text.data, data)
                        self.assertEqual(session.text.text, 'first\nsecond\n')

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
