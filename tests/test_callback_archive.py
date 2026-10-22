"""Callback archive views retain lazy reads and explicit manifest cancellation."""
import unittest
from zipfile import ZipInfo
from commonUtils.archives.callbacks import CallbackArchive
from commonUtils.runtime.operations import OperationCancelled


class CallbackArchiveTests(unittest.TestCase):
    def test_member_reads_are_lazy_validated_and_scoped(self):
        reads = []
        archive = CallbackArchive([ZipInfo('page.jpg')],
            read_member=lambda name: reads.append(name) or b'page')
        self.assertEqual(archive.namelist(), ['page.jpg'])
        self.assertEqual(reads, [])
        with self.assertRaises(KeyError):
            archive.read('missing')
        self.assertEqual(reads, [])
        with archive.open(archive.getinfo('page.jpg')) as stream:
            self.assertEqual(stream.read(), b'page')
        self.assertTrue(stream.closed)
        self.assertEqual(reads, ['page.jpg'])

    def test_manifest_preserves_values_and_checks_revocation_after_callback(self):
        cancelled = False
        def manifest():
            nonlocal cancelled
            cancelled = True
            return {'page.jpg': [4, 'digest']}
        archive = CallbackArchive([], read_member=lambda name: b'', manifest=manifest)
        with self.assertRaises(OperationCancelled):
            archive.content_manifest(cancelled=lambda: cancelled)
        self.assertEqual(archive.content_manifest(), {'page.jpg': (4, 'digest')})
