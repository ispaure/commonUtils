"""Shared stream helpers retain byte integrity and stop at cooperative boundaries."""
from hashlib import sha256
from io import BytesIO
from threading import Event
import unittest

from commonUtils.runtime.operations import OperationCancelled
from commonUtils.runtime.streams import CHUNK_SIZE, copy_stream, stream_signature


class StreamTests(unittest.TestCase):
    def test_signature_and_copy_report_all_bytes_across_chunk_boundaries(self):
        data = b'payload' * (CHUNK_SIZE // 7 + 9)
        counts = []
        self.assertEqual(stream_signature(BytesIO(data), progress=counts.append),
                         (len(data), sha256(data).hexdigest()))
        self.assertEqual(sum(counts), len(data))
        self.assertGreater(len(counts), 1)
        output = BytesIO()
        copy_stream(BytesIO(data), output)
        self.assertEqual(output.getvalue(), data)

    def test_copy_cancels_before_next_chunk(self):
        cancel = Event()
        source = BytesIO(b'x' * (CHUNK_SIZE + 10))
        output = BytesIO()
        with self.assertRaises(OperationCancelled):
            copy_stream(source, output, progress=lambda size: cancel.set(), cancelled=cancel.is_set)
        self.assertEqual(output.getvalue(), b'x' * CHUNK_SIZE)
        self.assertEqual(source.tell(), CHUNK_SIZE)

    def test_empty_stream_still_observes_cancellation(self):
        with self.assertRaises(OperationCancelled):
            stream_signature(BytesIO(), cancelled=lambda: True)

    def test_partial_writes_retry_the_unwritten_bytes_without_changing_progress_units(self):
        class PartialWriter(BytesIO):
            def write(self, data):
                return super().write(data[:3])
        output = PartialWriter()
        progress = []
        data = b'complete binary payload\x00'
        copy_stream(BytesIO(data), output, progress=progress.append)
        self.assertEqual(output.getvalue(), data)
        self.assertEqual(progress, [len(data)])

    def test_invalid_write_counts_fail_instead_of_silently_truncating_or_spinning(self):
        class InvalidWriter:
            def __init__(self, result):
                self.result = result
            def write(self, data):
                return self.result
        for result in (None, 0, -1, 100, True, '3'):
            with self.subTest(result=result), self.assertRaises(OSError):
                copy_stream(BytesIO(b'payload'), InvalidWriter(result))

    def test_cancellation_between_partial_writes_keeps_only_the_written_prefix(self):
        cancel = Event()
        class PartialWriter(BytesIO):
            def write(self, data):
                count = super().write(data[:3])
                cancel.set()
                return count
        output = PartialWriter()
        with self.assertRaises(OperationCancelled):
            copy_stream(BytesIO(b'complete payload'), output, cancelled=cancel.is_set)
        self.assertEqual(output.getvalue(), b'com')

    def test_would_block_reads_are_not_mistaken_for_successful_end_of_stream(self):
        class WouldBlock:
            def read(self, size):
                return None
        with self.assertRaises(BlockingIOError):
            copy_stream(WouldBlock(), BytesIO())
        with self.assertRaises(BlockingIOError):
            stream_signature(WouldBlock())
