"""ZIP cancellation at each publication phase preserves all source bytes."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest

from commonUtils.archives.zip_access import create_archive
from commonUtils.runtime.operations import OperationCancelled


class ZipCreationCancellationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_zip_cancellation_in_each_phase_discards_output_and_keeps_sources(self):
        source = self.root / 'large.bin'
        original = os.urandom(2 * 1024 * 1024 + 13)
        source.write_bytes(original)
        for phase in ('Checking ', 'Creating ZIP:', 'Verifying ', 'Publishing verified ZIP:'):
            with self.subTest(phase=phase):
                cancel = Event()
                output = self.root / 'cancelled.zip'
                def progress(done, total, message):
                    if message.startswith(phase):
                        cancel.set()
                with self.assertRaises(OperationCancelled):
                    create_archive([source], output, password='test-only',
                                   progress=progress, cancelled=cancel.is_set)
                self.assertTrue(cancel.is_set())
                self.assertFalse(output.exists())
                self.assertFalse(list(self.root.glob('.logistics-zip-*')))
                self.assertEqual(source.read_bytes(), original)

    def test_zip_cancel_before_start_does_not_create_workspace(self):
        source = self.root / 'source'
        source.write_bytes(b'original')
        output = self.root / 'output/new.zip'
        with self.assertRaises(OperationCancelled):
            create_archive([source], output, password='test-only', cancelled=lambda: True)
        self.assertFalse(output.parent.exists())
