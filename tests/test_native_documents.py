"""System export validates leaf names and keeps originals on failed stream copy."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.ui.native.documents import _copy_export, export_stream


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
