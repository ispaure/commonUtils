"""Shared stream helpers retain byte integrity and stop at cooperative boundaries."""
from hashlib import sha256
from io import BytesIO
from threading import Event
import unittest

from commonUtils.operations import OperationCancelled
from commonUtils.streams import CHUNK_SIZE, copy_stream, stream_signature


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
