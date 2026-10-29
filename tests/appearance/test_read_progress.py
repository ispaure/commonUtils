"""Read measurement and worker-to-loop progress have no application dependencies."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from commonUtils.runtime.progress import CoalescedProgress
from commonUtils.runtime.streams.progress import reading_stream, ReadingProvider


class ReadProgressTests(unittest.TestCase):
    def test_would_block_read_preserves_failure_and_retires_progress(self):
        class WouldBlock(BytesIO):
            def read(self, count):
                return super().read(1) if self.tell() == 0 else None
        source, updates = WouldBlock(b'complete'), []
        with self.assertRaises(BlockingIOError):
            with reading_stream(source, progress=lambda *values: updates.append(values)) as incoming:
                incoming.read()
        self.assertEqual(updates, [(0, None), (1, None), (None, None)])
        self.assertFalse(source.closed)

    def test_oversized_read_result_does_not_turn_a_bounded_read_into_read_all(self):
        class Oversized(BytesIO):
            def read(self, count):
                return super().read(count + 1)
        source = Oversized(b'complete payload')
        with self.assertRaises(OSError):
            with reading_stream(source, progress=lambda *_: None) as incoming:
                incoming.read(1)
        self.assertEqual(source.tell(), 2)
        self.assertFalse(source.closed)

    def test_chunking_remaining_file_size_and_scope_completion(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'data'
            path.write_bytes(b'x' * (200 * 1024))
            updates = []
            with path.open('rb') as source:
                source.read(1024)
                with reading_stream(source, progress=lambda *v: updates.append(v)) as stream:
                    self.assertEqual(len(stream.read()), 199 * 1024)
                self.assertFalse(source.closed)
            self.assertEqual(updates[0], (0, 199 * 1024))
            self.assertEqual(updates[-2], (199 * 1024, 199 * 1024))
            self.assertEqual(updates[-1], (None, None))
            counts = [done for done, _ in updates[:-1]]
            self.assertTrue(all(0 <= b - a <= 64 * 1024 for a, b in zip(counts, counts[1:])))

    def test_unknown_totals_no_observer_and_failure_cleanup(self):
        source = BytesIO(b'abc')
        with reading_stream(source) as stream:
            self.assertIs(stream, source)
        updates = []
        with self.assertRaisesRegex(ValueError, 'fixture'):
            with reading_stream(source, progress=lambda *v: updates.append(v), total=-1) as stream:
                self.assertEqual(stream.read(0), b'')
                self.assertEqual(stream.read(2), b'ab')
                raise ValueError('fixture')
        self.assertEqual(updates, [(0, None), (2, None), (None, None)])
        self.assertFalse(source.closed)

    def test_provider_reports_entry_size_and_closes_its_source(self):
        updates = []
        source = BytesIO(b'abc')
        @contextmanager
        def opened(path):
            try:
                yield source
            finally:
                source.close()
        provider = SimpleNamespace(entry=lambda path: {'size': 3}, open=opened, root='identity')
        measured = ReadingProvider(provider, progress=lambda *v: updates.append(v))
        self.assertEqual(measured.root, 'identity')
        with measured.open('item') as stream:
            self.assertEqual(stream.read(), b'abc')
        self.assertTrue(source.closed)
        self.assertEqual(updates, [(0, 3), (3, 3), (None, None)])


class ProgressDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_updates_coalesce_and_retirement_suppresses_callbacks(self):
        values = []
        active = [True]
        reporter = CoalescedProgress(asyncio.get_running_loop(), lambda *v: values.append(v),
                                     active=lambda: active[0], interval=.01)
        self.addCleanup(reporter.close)
        await asyncio.to_thread(lambda: [reporter.publish(i, 100) for i in range(100)])
        await asyncio.sleep(.03)
        self.assertEqual(values, [(99, 100)])
        active[0] = False
        reporter.publish(100, 100)
        await asyncio.sleep(.03)
        self.assertEqual(values, [(99, 100)])
        active[0] = True
        reporter.publish()
        reporter.close()
        reporter.publish(1, 2)
        await asyncio.sleep(.03)
        self.assertEqual(values, [(99, 100)])
