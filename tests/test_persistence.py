"""Publication races and staging cleanup, independent of text format policy."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.persistence import atomic_write_bytes


class PersistenceTests(unittest.TestCase):
    def test_second_validation_preserves_external_write_and_removes_staging(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'note'
            path.write_bytes(b'original')
            calls = []
            def validate():
                calls.append(True)
                if len(calls) == 2:
                    path.write_bytes(b'external')
                    raise ValueError('conflict')
            with self.assertRaises(ValueError):
                atomic_write_bytes(path, b'buffer', validate=validate)
            self.assertEqual(path.read_bytes(), b'external')
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_no_clobber_preserves_racing_destination(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'note'
            path.write_bytes(b'external')
            with self.assertRaises(FileExistsError):
                atomic_write_bytes(path, b'buffer', overwrite=False)
            self.assertEqual(path.read_bytes(), b'external')
            self.assertEqual(list(Path(directory).iterdir()), [path])
