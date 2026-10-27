"""Explicit private modes and bounded Windows sharing retry preserve old data."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from commonUtils.persistence import atomic


class PublicationTests(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'POSIX permissions')
    def test_explicit_mode_tightens_existing_file_default_preserves_it(self):
        with TemporaryDirectory() as folder:
            target = Path(folder) / 'state'
            target.write_bytes(b'old')
            target.chmod(0o644)
            atomic.atomic_write_bytes(target, b'normal')
            self.assertEqual(target.stat().st_mode & 0o777, 0o644)
            atomic.atomic_write_bytes(target, b'private', file_mode=0o600)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_transient_retry_and_permanent_failure_cleanup(self):
        with TemporaryDirectory() as folder:
            target = Path(folder) / 'state'
            target.write_bytes(b'old')
            original = os.replace
            sharing = PermissionError('sharing'); sharing.winerror = 32
            windows = Mock(wraps=os); windows.name = 'nt'
            calls = []
            def replace(source, destination):
                calls.append(source)
                if len(calls) == 1:
                    raise sharing
                return original(source, destination)
            with patch.object(atomic, 'os', windows), patch.object(windows, 'replace', side_effect=replace):
                atomic.atomic_write_bytes(target, b'new', replace_timeout=1)
            self.assertEqual(len(calls), 2)
            with patch.object(atomic.os, 'replace', side_effect=OSError('permanent')):
                with self.assertRaises(OSError):
                    atomic.atomic_write_bytes(target, b'lost', replace_timeout=1)
            self.assertEqual(target.read_bytes(), b'new')
            self.assertEqual(list(Path(folder).iterdir()), [target])

    def test_retry_deadline_is_bounded(self):
        with TemporaryDirectory() as folder:
            target = Path(folder) / 'state'
            target.write_bytes(b'old')
            sharing = PermissionError('sharing'); sharing.winerror = 32
            windows = Mock(wraps=os); windows.name = 'nt'
            with patch.object(atomic, 'os', windows), \
                    patch.object(windows, 'replace', side_effect=sharing) as replace, \
                    patch.object(atomic.time, 'monotonic', side_effect=[0, 0, 2]), \
                    patch.object(atomic.time, 'sleep'):
                with self.assertRaises(PermissionError):
                    atomic.atomic_write_bytes(target, b'lost', replace_timeout=1)
                self.assertEqual(replace.call_count, 2)
            self.assertEqual(target.read_bytes(), b'old')
            self.assertEqual(list(Path(folder).iterdir()), [target])
