"""Content inventories reject changed/linked files and honor bounds/cancellation."""
from hashlib import sha256
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from commonUtils.filesystem.snapshots import tree_content_state, verified_file_snapshot, copy_content_state
from commonUtils.runtime.operations import OperationCancelled


class ContentSnapshots(unittest.TestCase):
    def test_nested_hashes_bounds_and_cancellation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'folder').mkdir()
            (root/'folder'/'file').write_bytes(b'hello')
            self.assertEqual(tree_content_state(root), {'folder': None, 'folder/file': sha256(b'hello').hexdigest()})
            with self.assertRaises(ValueError): tree_content_state(root, max_entries=1)
            with self.assertRaises(OperationCancelled): tree_content_state(root, cancelled=lambda: True)

    def test_file_changes_during_hash_are_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'file'
            path.write_bytes(b'original')
            from commonUtils.runtime.streams import stream_signature
            def changing(stream, **kwargs):
                result = stream_signature(stream, **kwargs)
                path.write_bytes(b'changed and longer')
                return result
            with patch('commonUtils.filesystem.snapshots.stream_signature', side_effect=changing):
                with self.assertRaisesRegex(ValueError, 'changed'): verified_file_snapshot(path)

    def test_path_and_descriptor_ctimes_need_not_have_the_same_meaning(self):
        from types import SimpleNamespace
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'file'
            path.write_bytes(b'payload')
            info = path.stat()
            fields = dict(st_dev=info.st_dev, st_ino=info.st_ino, st_size=info.st_size,
                          st_mtime_ns=info.st_mtime_ns, st_ctime_ns=info.st_ctime_ns + 123456789)
            descriptor = SimpleNamespace(**fields)
            with patch('commonUtils.filesystem.snapshots.os.fstat', return_value=descriptor):
                self.assertEqual(verified_file_snapshot(path)[1], sha256(b'payload').digest())
            changed = SimpleNamespace(**(fields | {'st_ctime_ns': fields['st_ctime_ns'] + 1}))
            with patch('commonUtils.filesystem.snapshots.os.fstat', side_effect=[descriptor, changed]):
                with self.assertRaisesRegex(ValueError, 'changed'): verified_file_snapshot(path)

    def test_hard_links_are_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'file').write_bytes(b'data')
            try: os.link(root/'file', root/'link')
            except OSError as error: self.skipTest(str(error))
            with self.assertRaises(ValueError): tree_content_state(root)
            state = copy_content_state(root)
            self.assertEqual(state['file'], state['link'])

    def test_symbolic_links_are_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'file').write_bytes(b'data')
            try: (root/'link').symlink_to(root/'file')
            except OSError as error: self.skipTest(str(error))
            with self.assertRaises(ValueError): tree_content_state(root)

    def test_copy_content_state_compares_bytes_kinds_and_raw_links(self):
        import shutil
        from commonUtils.filesystem.snapshots import copy_content_state, file_revision
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source, copied = root / 'source', root / 'copied'
            source.mkdir()
            (source / 'empty').mkdir()
            (source / 'file').write_bytes(b'payload')
            (source / 'link').symlink_to('missing')
            shutil.copytree(source, copied, symlinks=True)
            self.assertEqual(copy_content_state(source), copy_content_state(copied))
            self.assertEqual(copy_content_state(source)['link'], ('link', 'missing'))
            self.assertEqual(copy_content_state(source)['empty'], ('directory',))
            self.assertNotEqual(file_revision(source / 'file'), file_revision(copied / 'file'))
            self.assertEqual(file_revision(source / 'link', follow_symlinks=False)[2],
                             (source / 'link').lstat().st_size)
            (copied / 'file').write_bytes(b'corrupt')
            self.assertNotEqual(copy_content_state(source), copy_content_state(copied))
