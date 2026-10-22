"""Conformance checks for shared transfer phases without caller policy changes."""
import errno
import unittest
from unittest.mock import Mock
from commonUtils.persistence.transfers import try_rename, verify_unchanged, cleanup_published
from commonUtils.runtime.operations import MutationIncomplete, MutationResult


class TransferPhaseTests(unittest.TestCase):
    def test_only_cross_volume_rename_requests_copy_fallback(self):
        for code, fallback in ((errno.EXDEV, True), (errno.EEXIST, False), (errno.EACCES, False)):
            with self.subTest(code=code):
                rename = Mock(side_effect=OSError(code, 'synthetic'))
                if fallback:
                    self.assertFalse(try_rename('a', 'b', rename=rename))
                else:
                    with self.assertRaises(OSError):
                        try_rename('a', 'b', rename=rename)
                rename.assert_called_once_with('a', 'b')
        self.assertTrue(try_rename('a', 'b', rename=Mock()))

    def test_snapshot_failures_and_cancellation_are_not_suppressed(self):
        verify_unchanged({'revision': 1}, lambda: {'revision': 1}, message='changed')
        with self.assertRaisesRegex(ValueError, 'changed'):
            verify_unchanged(1, lambda: 2, message='changed')
        for error in (OSError('unreadable'), RuntimeError('cancelled')):
            with self.subTest(error=error), self.assertRaises(type(error)):
                verify_unchanged(1, Mock(side_effect=error), message='changed')

    def test_cleanup_failure_always_retains_published_destination_identity(self):
        for state in ('unchanged', 'partial', 'unknown'):
            with self.subTest(state=state), self.assertRaises(MutationIncomplete) as raised:
                cleanup_published(Mock(side_effect=OSError('cleanup')), source_state=lambda: state)
            self.assertEqual(raised.exception.result, MutationResult(True, state))
        partial = MutationResult(False, 'partial', ('removed',))
        with self.assertRaises(MutationIncomplete) as raised:
            cleanup_published(Mock(side_effect=MutationIncomplete('partial', partial)), source_state=lambda: 'unchanged')
        self.assertEqual(raised.exception.result, MutationResult(True, 'partial', ('removed',)))
