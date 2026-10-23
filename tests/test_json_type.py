"""Reusable JSON files preserve originals when serialization or replacement fails."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.formats.jsonType import JSONFile


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
        with patch('commonUtils.persistence.atomic.os.replace', side_effect=OSError('failed')):
            with self.assertRaises(OSError):
                file.write_json({'new': True})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])
        file.write_json({'new': True})
        self.assertEqual(self.path.stat().st_mode & 0o777, expected_mode)

    def test_missing_and_malformed_errors_are_available_to_callers(self):
        with self.assertRaises(FileNotFoundError):
            JSONFile(self.path).read_json()
        self.path.parent.mkdir()
        self.path.write_text('invalid JSON')
        with self.assertRaises(json.JSONDecodeError):
            JSONFile(self.path).read_json()

    def test_pretty_output_retains_native_text_newlines(self):
        JSONFile(self.path).write_json({'title': 'Été'}, ensure_ascii=True)
        expected = '{\n  "title": "\\u00c9t\\u00e9"\n}'.replace('\n', os.linesep).encode()
        self.assertEqual(self.path.read_bytes(), expected)

    def test_protected_destinations_are_rejected_before_creating_parents(self):
        from commonUtils.filesystem.local_access import protect_local_root
        for existing in (False, True):
            with self.subTest(existing=existing):
                path = self.root / str(existing) / 'nested/data.json'
                if existing:
                    path.parent.mkdir(parents=True)
                    path.write_bytes(b'{"old":true}')
                release = protect_local_root(self.id(), self.root, 'Use the provider')
                try:
                    with self.assertRaisesRegex(PermissionError, 'Use the provider'):
                        JSONFile(path).write_json({'new': True})
                    if existing:
                        self.assertEqual(path.read_bytes(), b'{"old":true}')
                    else:
                        self.assertFalse(path.parent.exists())
                finally:
                    release()
