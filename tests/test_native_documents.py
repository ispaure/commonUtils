"""System export validates leaf names and keeps originals on failed stream copy."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.ui.native.documents import _copy_export, export_stream
from commonUtils.filesystem.local_access import protect_local_root


class NativeDocumentsTests(unittest.IsolatedAsyncioTestCase):
    async def test_export_rejects_paths_before_opening_a_picker(self):
        for name in ('../escape', '/absolute', 'a/b', 'a\\b', '.', '..', '\x00'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                await export_stream(None, name, lambda: BytesIO(b'data'))

    async def test_window_disconnection_cancels_only_its_picker(self):
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import patch
        from commonUtils.ui.native.documents import cancel_document_picker
        first = asyncio.get_running_loop().create_future()
        other = asyncio.get_running_loop().create_future()
        with patch('commonUtils.ui.native.documents._ios_pickers', {'first': (first,), 'other': (other,)}):
            cancel_document_picker(SimpleNamespace(id='first'))
            cancel_document_picker(SimpleNamespace(id='absent'))
        self.assertTrue(first.cancelled())
        self.assertFalse(other.done())
        other.cancel()

    def test_failed_stream_preserves_original_and_cleans_stage(self):
        class Failing(BytesIO):
            def read(self, limit=-1):
                if self.tell(): raise OSError('disconnected')
                return super().read(1)
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'target'
            path.write_bytes(b'original')
            with self.assertRaisesRegex(OSError, 'disconnected'):
                _copy_export(lambda: Failing(b'partial'), path)
            self.assertEqual(path.read_bytes(), b'original')
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_local_export_replaces_selected_file_and_cleans_stage(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'target'
            path.write_bytes(b'original')
            _copy_export(lambda: BytesIO(b'exported'), path)
            self.assertEqual(path.read_bytes(), b'exported')
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_export_rejects_protected_destination_before_opening_source(self):
        from unittest.mock import Mock
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'target'
            path.write_bytes(b'opaque')
            source = Mock(return_value=BytesIO(b'plaintext'))
            release = protect_local_root(self.id(), directory, 'Use the provider')
            try:
                with self.assertRaisesRegex(PermissionError, 'Use the provider'):
                    _copy_export(source, path)
                source.assert_not_called()
                self.assertEqual(path.read_bytes(), b'opaque')
                self.assertEqual(list(path.parent.iterdir()), [path])
            finally:
                release()

    def test_export_rechecks_boundary_before_publication(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'target'
            path.write_bytes(b'opaque')
            releases = []
            def open_source():
                releases.append(protect_local_root(self.id(), directory, 'Use the provider'))
                return BytesIO(b'plaintext')
            try:
                with self.assertRaisesRegex(PermissionError, 'Use the provider'):
                    _copy_export(open_source, path)
                self.assertEqual(path.read_bytes(), b'opaque')
                self.assertEqual(list(path.parent.iterdir()), [path])
            finally:
                for release in releases:
                    release()
