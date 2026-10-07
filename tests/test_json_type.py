"""Reusable JSON files preserve originals when serialization or replacement fails."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.fileTypes.jsonType import JSONFile


class JSONFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'nested' / 'data.json'

    def test_unicode_nested_values_compact_bom_and_file_properties(self):
        file = JSONFile(self.path)
        data = {'name': 'Été', 'values': [True, None, {'x': 3}]}
        file.write_json(data, compact=True, sort_keys=True)
        self.assertEqual(file.read_json(), data)
        self.assertEqual(file.size, self.path.stat().st_size)
        self.assertNotIn(': ', self.path.read_text())
        self.path.write_bytes(b'\xef\xbb\xbf' + self.path.read_bytes())
        self.assertEqual(file.read_json(), data)
        file.write_json(data)
        self.assertIn('\n', self.path.read_text())

    def test_serialization_and_replace_failure_preserve_original_and_remove_temp(self):
        file = JSONFile(self.path)
        file.write_json({'old': True})
        self.path.chmod(0o640)
        expected_mode = self.path.stat().st_mode & 0o777
        before = self.path.read_bytes()
        with self.assertRaises(TypeError):
            file.write_json({'invalid': object()})
        with self.assertRaises(ValueError):
            file.write_json(float('nan'))
        with patch('commonUtils.fileTypes.jsonType.os.replace', side_effect=OSError('failed')):
            with self.assertRaises(OSError):
                file.write_json({'new': True})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(list(self.path.parent.glob('*.tmp')))
        file.write_json({'new': True})
        self.assertEqual(self.path.stat().st_mode & 0o777, expected_mode)

    def test_missing_and_malformed_errors_are_available_to_callers(self):
        with self.assertRaises(FileNotFoundError):
            JSONFile(self.path).read_json()
        self.path.parent.mkdir()
        self.path.write_text('invalid JSON')
        with self.assertRaises(json.JSONDecodeError):
            JSONFile(self.path).read_json()
