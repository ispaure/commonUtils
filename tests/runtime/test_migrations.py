"""Explicit completion, retryable partial migrations and preserved metadata."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock
from configparser import Error
from commonUtils.configuration.migrations import MigrationLedger


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'state' / 'migrations.ini'
        self.ledger = MigrationLedger(self.path)

    def test_reads_do_not_create_metadata_and_success_runs_once(self):
        self.assertIsNone(self.ledger.state('example-v1'))
        self.assertFalse(self.path.exists())
        callback = Mock()
        self.assertTrue(self.ledger.run('example-v1', callback))
        self.assertFalse(self.ledger.run('example-v1', callback))
        callback.assert_called_once()
        self.assertEqual(self.ledger.state('example-v1'), 'done')

    def test_adopts_existing_completion_without_importing_old_settings(self):
        callback = Mock()
        self.assertFalse(self.ledger.run('example-v1', callback, already_applied=True))
        callback.assert_not_called()
        self.assertEqual(self.ledger.state('example-v1'), 'done')

    def test_partial_failure_retries_despite_created_destination(self):
        destination = self.path.parent / 'partial.ini'
        def migrate():
            destination.write_text('partial')
            raise OSError('Second write failed')
        with self.assertRaises(OSError):
            self.ledger.run('example-v1', migrate)
        self.assertEqual(self.ledger.state('example-v1'), 'pending')
        retry = Mock()
        self.assertTrue(self.ledger.run('example-v1', retry, already_applied=destination.exists()))
        retry.assert_called_once()

    def test_reset_completion_preserves_other_migrations(self):
        self.ledger.complete('other-v1')
        self.ledger.complete('git-v1', 'editor-v1')
        self.assertEqual(self.ledger.state('other-v1'), 'done')
        self.assertEqual(self.ledger.state('git-v1'), 'done')

    def test_malformed_metadata_is_preserved_and_no_callback_runs(self):
        self.path.parent.mkdir()
        self.path.write_bytes(b'[broken')
        callback = Mock()
        with self.assertRaises(Error):
            self.ledger.run('example-v1', callback)
        self.assertEqual(self.path.read_bytes(), b'[broken')
        callback.assert_not_called()

    def test_invalid_state_is_not_treated_as_completion(self):
        self.path.parent.mkdir()
        self.path.write_text('[Migrations]\nexample-v1=invalid\n')
        with self.assertRaises(ValueError):
            self.ledger.run('example-v1', Mock())


if __name__ == '__main__':
    unittest.main()
