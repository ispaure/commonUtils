"""Data framing retains arbitrary byte boundaries and the existing buffer limit."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest
from commonUtils.runtime.streams.sse import SSEDataDecoder, SSERecordLimit


class SSEFramingTests(unittest.TestCase):
    def test_each_byte_boundary_multiline_utf8_and_ignored_fields(self):
        wire = ':comment\r\nid: 1\r\ndata: café\r\ndata: next\r\n\r\ndata: tail'.encode()
        for size in range(1, len(wire) + 1):
            decoder = SSEDataDecoder(max_record=1024)
            values = []
            for offset in range(0, len(wire), size):
                values.extend(decoder.feed(wire[offset:offset + size]))
            self.assertEqual(values, ['café\nnext'])
            self.assertEqual(list(decoder.feed(b'\n\n')), ['tail'])

    def test_pending_data_counts_toward_limit_before_processing_chunk(self):
        decoder = SSEDataDecoder(max_record=10)
        self.assertEqual(list(decoder.feed(b'data: a\n')), [])
        with self.assertRaises(SSERecordLimit):
            list(decoder.feed(b'data: bbb\n\n'))

    def test_consumer_failure_leaves_later_record_unconsumed(self):
        decoder = SSEDataDecoder(max_record=1024)
        records = decoder.feed(b'data: first\n\ndata: second\n\n')
        self.assertEqual(next(records), 'first')
        records.close()
        self.assertEqual(list(decoder.feed(b'')), ['second'])
