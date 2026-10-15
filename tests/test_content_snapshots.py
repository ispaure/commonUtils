"""Content inventories reject changed/linked files and honor bounds/cancellation."""
from hashlib import sha256
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from commonUtils.filesystem.snapshots import tree_content_state, verified_file_snapshot
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

    def test_hard_links_are_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'file').write_bytes(b'data')
            try: os.link(root/'file', root/'link')
            except OSError as error: self.skipTest(str(error))
            with self.assertRaises(ValueError): tree_content_state(root)

    def test_symbolic_links_are_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'file').write_bytes(b'data')
            try: (root/'link').symlink_to(root/'file')
            except OSError as error: self.skipTest(str(error))
            with self.assertRaises(ValueError): tree_content_state(root)
