"""Copy fallback owns only newly created targets and never removes the source."""
import errno
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from commonUtils.persistence import exclusive_copy


class ExclusiveCopyTests(unittest.TestCase):
    def test_copy_fallback_preserves_source_and_rejects_existing_destination(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, target = root / 'stage', root / 'target'
            source.write_bytes(b'new')
            with patch.object(exclusive_copy.os, 'link', side_effect=OSError(errno.EXDEV, 'fixture')):
                exclusive_copy.link_or_copy_exclusive(source, target)
                self.assertEqual(source.read_bytes(), b'new')
                self.assertEqual(target.read_bytes(), b'new')
                with self.assertRaises(FileExistsError):
                    exclusive_copy.link_or_copy_exclusive(source, target)
                self.assertEqual(target.read_bytes(), b'new')

    def test_failed_copy_removes_only_its_partial_destination(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, target = root / 'stage', root / 'target'
            source.write_bytes(b'new')
            def fail(source_stream, target_stream):
                target_stream.write(b'partial')
                raise OSError('fixture')
            with patch.object(exclusive_copy.os, 'link', side_effect=OSError(errno.ENOTSUP, 'fixture')), \
                    patch.object(exclusive_copy.shutil, 'copyfileobj', side_effect=fail):
                with self.assertRaises(OSError):
                    exclusive_copy.link_or_copy_exclusive(source, target)
            self.assertFalse(target.exists())
            self.assertEqual(source.read_bytes(), b'new')
