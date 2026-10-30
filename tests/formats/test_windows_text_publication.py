"""Transient Windows readers cannot defeat guarded atomic text publication."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from commonUtils.testing.stages import TestStage
from commonUtils.persistence import atomic
from commonUtils.persistence.text import FileConflictError, write_text_file

TEST_STAGE = TestStage.REGRESSION


class SharingRecoveryTests(unittest.TestCase):
    def test_reader_release_retries_the_same_staged_bytes(self):
        self.publication_case(change=False)

    def test_writer_change_while_waiting_preserves_external_bytes(self):
        self.publication_case(change=True)

    def publication_case(self, *, change):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'file.py'
            path.write_bytes(b'original')
            error = PermissionError('synthetic sharing violation')
            error.winerror = 32
            calls = []
            def replace(source, destination):
                calls.append(source)
                if len(calls) == 1:
                    if change:
                        path.write_bytes(b'external')  # Same length: exercise hash guard.
                    raise error
                os.replace(source, destination)
            windows = SimpleNamespace(name='nt', replace=replace, fsync=os.fsync)
            clock = SimpleNamespace(monotonic=time.monotonic, sleep=lambda seconds: None)
            with patch.object(atomic, 'os', windows), patch.object(atomic, 'time', clock):
                if change:
                    with self.assertRaises(FileConflictError):
                        write_text_file(path, b'buffer', expected=b'original')
                else:
                    write_text_file(path, b'buffer', expected=b'original')
            self.assertEqual(path.read_bytes(), b'external' if change else b'buffer')
            self.assertEqual(len(calls), 1 if change else 2)
            if not change:
                self.assertEqual(calls[0], calls[1])
            self.assertEqual(list(root.iterdir()), [path])

    def test_persistent_sharing_and_unrelated_errors_remain_failures(self):
        for code in (32, 87):
            with self.subTest(winerror=code), TemporaryDirectory() as temporary:
                root = Path(temporary)
                path = root / 'file.py'
                path.write_bytes(b'original')
                error = PermissionError('synthetic failure')
                error.winerror = code
                windows = SimpleNamespace(name='nt', fsync=os.fsync)
                with patch.object(atomic, 'os', windows), \
                     patch.object(windows, 'replace', create=True, side_effect=error) as replace, \
                     patch.object(atomic, 'time', SimpleNamespace(monotonic=iter((0, 3)).__next__,
                                                                 sleep=lambda seconds: None)):
                    with self.assertRaises(PermissionError):
                        write_text_file(path, b'buffer', expected=b'original')
                self.assertEqual(replace.call_count, 1)
                self.assertEqual(path.read_bytes(), b'original')
                self.assertEqual(list(root.iterdir()), [path])


@unittest.skipUnless(os.name == 'nt', 'Real Windows file-sharing handles')
class NativeSharingTests(unittest.TestCase):
    def test_actual_reader_handle_release_allows_save(self):
        self.publication_case(change=False)

    def test_actual_lock_wait_still_rejects_a_concurrent_writer(self):
        self.publication_case(change=True)

    def publication_case(self, *, change):
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                           ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
        create.restype = wintypes.HANDLE
        close = kernel.CloseHandle
        close.argtypes = (wintypes.HANDLE,)
        close.restype = wintypes.BOOL
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'file.py'
            path.write_bytes(b'original')
            # Permit reads/writes but deny DELETE sharing, as ordinary readers do.
            handle = create(str(path), 0x80000000, 1 | 2, None, 3, 0x80, None)
            self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
            attempted, released = Event(), Event()
            errors = []
            def release():
                try:
                    if not attempted.wait(5):
                        raise RuntimeError('No real sharing violation observed')
                    if change:
                        path.write_bytes(b'external')
                except BaseException as error:
                    errors.append(error)
                finally:
                    close(handle)
                    released.set()
            thread = Thread(target=release)
            thread.start()
            original_replace = os.replace
            def observed_replace(source, destination):
                try:
                    original_replace(source, destination)
                except OSError as error:
                    if getattr(error, 'winerror', None) in (5, 32, 33):
                        attempted.set()
                    raise
            def wait(seconds):
                if not released.wait(5):
                    raise RuntimeError('Reader did not release its handle')
            windows = SimpleNamespace(name='nt', replace=observed_replace, fsync=os.fsync)
            try:
                with patch.object(atomic, 'os', windows), \
                     patch.object(atomic, 'time', SimpleNamespace(monotonic=time.monotonic, sleep=wait)):
                    if change:
                        with self.assertRaises(FileConflictError):
                            write_text_file(path, b'buffer', expected=b'original')
                    else:
                        write_text_file(path, b'buffer', expected=b'original')
            finally:
                thread.join(6)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertTrue(attempted.is_set())
            self.assertEqual(path.read_bytes(), b'external' if change else b'buffer')
            self.assertEqual(list(root.iterdir()), [path])
