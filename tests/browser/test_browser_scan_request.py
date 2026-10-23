"""Captured browser requests preserve cache/scan policy and snapshot ownership."""
from pathlib import Path
import unittest
from unittest.mock import MagicMock, Mock

from commonUtils.runtime.operations import OperationCancelled
from commonUtils.ui.file_browser.index_policy import IndexPolicy
from commonUtils.ui.file_browser.index_worker import _FolderScan


class BrowserScanRequestTests(unittest.TestCase):
    def setUp(self):
        self.root = Path('/synthetic/folder')
        self.snapshot = MagicMock()
        self.snapshot.folder_stats.return_value = {self.root: 'totals'}
        self.cache = Mock(coordinator=None)
        self.cache.peek.return_value = self.snapshot
        self.cache.reconcile_folder.return_value = self.snapshot
        self.cancelled, self.report = Mock(return_value=False), Mock()

    def scan(self, *, paused=False, read_cache=True, full=False, policy=None):
        request = _FolderScan(self.cache, policy or IndexPolicy(), read_cache=read_cache,
                              paused=paused, full=full, changes=(self.root / 'changed',))
        return request(self.root, self.cancelled, report=self.report, reuse_for=30)

    def test_paused_request_reads_saved_snapshot_without_repair_or_scan(self):
        self.assertEqual(self.scan(paused=True), {self.root: 'totals'})
        self.cache.repair_cached_exclusions.assert_not_called()
        self.cache.reconcile_folder.assert_not_called()
        self.snapshot.__exit__.assert_called_once()
        self.snapshot.folder_stats.assert_called_once_with(children_of=self.root, cancelled=self.cancelled)

    def test_missing_paused_or_disabled_scan_cache_does_not_start_work(self):
        self.cache.peek.return_value = None
        self.assertIsNone(self.scan(paused=True))
        self.assertIsNone(self.scan(policy=IndexPolicy(scan_on_open=False)))
        self.cache.reconcile_folder.assert_not_called()

    def test_cache_read_repairs_exclusions_before_opening_snapshot(self):
        self.scan()
        self.assertEqual([call[0] for call in self.cache.mock_calls[:2]],
                         ['repair_cached_exclusions', 'peek'])
        self.cache.reconcile_folder.assert_not_called()

    def test_cache_miss_reconciles_with_captured_changes_and_recursion(self):
        self.cache.peek.return_value = None
        policy = IndexPolicy(recursive_on_open=False, background_priority=False)
        self.scan(full=True, policy=policy)
        self.cache.reconcile_folder.assert_called_once_with(
            self.root, changes=(self.root / 'changed',), full=True, once=True,
            cancelled=self.cancelled, report=self.report, recursive_initial=False)
        self.snapshot.__exit__.assert_called_once()

    def test_active_coordinator_is_followed_without_fallback_even_without_snapshot(self):
        coordinator = self.cache.coordinator = Mock()
        coordinator.follow.return_value = None
        self.assertIsNone(self.scan())
        coordinator.follow.assert_called_once_with(coordinator.active_job.return_value, self.root,
                                                   cancelled=self.cancelled, report=self.report)
        self.cache.peek.assert_not_called()
        coordinator.reconcile_folder.assert_not_called()
        coordinator.follow.return_value = self.snapshot
        self.assertEqual(self.scan(), {self.root: 'totals'})
        self.snapshot.__exit__.assert_called_once()

    def test_explicit_scan_uses_coordinator_priority_without_reading_cache(self):
        coordinator = self.cache.coordinator = Mock()
        coordinator.reconcile_folder.return_value = self.snapshot
        self.scan(read_cache=False, full=True, policy=IndexPolicy(background_priority=False))
        self.cache.peek.assert_not_called()
        coordinator.active_job.assert_not_called()
        coordinator.reconcile_folder.assert_called_once_with(
            self.root, changes=(self.root / 'changed',), full=True, once=True,
            cancelled=self.cancelled, report=self.report, recursive_initial=True, background_priority=False)

    def test_snapshot_closes_on_cancellation_and_other_errors_still_propagate(self):
        for exception in (OperationCancelled(), RuntimeError('read failed')):
            with self.subTest(exception=type(exception).__name__):
                self.snapshot.reset_mock()
                self.snapshot.folder_stats.side_effect = exception
                if isinstance(exception, OperationCancelled):
                    self.assertIsNone(self.scan())
                else:
                    with self.assertRaisesRegex(RuntimeError, 'read failed'):
                        self.scan()
                self.snapshot.__exit__.assert_called_once()
