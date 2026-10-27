"""Advisory locks retain one inode and release ownership on every exit path."""
import errno
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

from commonUtils.persistence import locking


class FileLockTests(unittest.TestCase):
    def test_contention_and_exception_release(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'lock'
            with self.assertRaisesRegex(ValueError, 'body'):
                with locking.file_lock(path) as acquired:
                    self.assertTrue(acquired)
                    with locking.file_lock(path) as second:
                        self.assertFalse(second)
                    raise ValueError('body')
            with locking.file_lock(path) as acquired:
                self.assertTrue(acquired)
            self.assertTrue(path.exists())

    def test_windows_never_initializes_locked_byte(self):
        stream, path = MagicMock(), MagicMock()
        path.open.return_value.__enter__.return_value = stream
        api = SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2,
            locking=Mock(side_effect=[BlockingIOError(errno.EACCES, 'busy'), None, None]))
        with patch.object(locking, 'Path', return_value=path), \
                patch.object(locking, 'os', SimpleNamespace(name='nt')), \
                patch.object(locking.time, 'sleep'), patch.dict('sys.modules', msvcrt=api):
            with locking.file_lock('fixture', timeout=1) as acquired:
                self.assertTrue(acquired)
        self.assertEqual(api.locking.call_count, 3)
        stream.write.assert_not_called()
        stream.flush.assert_not_called()

    @unittest.skipIf(os.name == 'nt', 'POSIX error injection')
    def test_unrelated_os_error_is_not_contention(self):
        with TemporaryDirectory() as folder, \
                patch('fcntl.flock', side_effect=OSError(errno.EBADF, 'invalid')):
            with self.assertRaises(OSError):
                with locking.file_lock(Path(folder) / 'lock'):
                    self.fail('must not acquire')
