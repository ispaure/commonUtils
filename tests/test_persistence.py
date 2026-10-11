"""Publication races and staging cleanup, independent of text format policy."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.persistence import atomic_write_bytes
from commonUtils.persistence import promote_path
from unittest.mock import patch


class PersistenceTests(unittest.TestCase):
    def test_tree_publication_keeps_recovery_copy(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            old, staged = root / 'app', root / 'staged'
            old.mkdir(); staged.mkdir()
            (old / 'original').write_text('old')
            (staged / 'new').write_text('new')
            backup = promote_path(staged, old)
            self.assertEqual((backup / 'original').read_text(), 'old')
            self.assertEqual((old / 'new').read_text(), 'new')

    def test_failed_promotion_restores_original(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            old, staged = root / 'app', root / 'staged'
            old.write_bytes(b'original'); staged.write_bytes(b'new')
            rename = Path.rename
            def fail_new(path, target):
                if path == staged:
                    raise OSError('promotion failed')
                return rename(path, target)
            with patch.object(Path, 'rename', fail_new):
                with self.assertRaisesRegex(OSError, 'promotion failed'):
                    promote_path(staged, old)
            self.assertEqual(old.read_bytes(), b'original')
            self.assertEqual(staged.read_bytes(), b'new')

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

    def test_invalid_json_and_size_limit_preserve_existing_state(self):
        from commonUtils.persistence import atomic_write_json
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            atomic_write_json(path, {'label': '😀'})
            original = path.read_bytes()
            for data, options in [({'value': float('nan')}, {}), ({'large': 'text'}, {'max_bytes': 2})]:
                with self.assertRaises(ValueError):
                    atomic_write_json(path, data, **options)
                self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(directory).iterdir()), [path])
