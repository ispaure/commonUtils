"""ZIP writes to subprocess pipes retain correct headers on every platform."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from io import BytesIO, UnsupportedOperation
import sys
import unittest
import zipfile
from commonUtils.archives.zip_access import open_archive
from commonUtils.integrations.wrappers.cmdShellWrapper.binary import BinaryCommandError, _BinarySink, run_bytes


class BinaryStreamTests(unittest.TestCase):
    def test_failed_command_diagnostics_are_opt_in_bounded_and_not_in_message(self):
        command = [sys.executable, '-c',
                   'import sys; sys.stderr.buffer.write(b"private-sentinel" * 10000); sys.exit(7)']
        for limit in (0, 37):
            with self.subTest(limit=limit), self.assertRaises(BinaryCommandError) as caught:
                run_bytes(command, max_stderr=limit)
            error = caught.exception
            self.assertEqual(error.returncode, 7)
            self.assertEqual(error.stderr, (b'private-sentinel' * 10000)[:limit])
            self.assertNotIn('private-sentinel', str(error))
            self.assertNotIn('private-sentinel', repr(error))

    def write_archive(self, stream, password=None):
        with open_archive(stream, 'w', password=password) as archive:
            archive.writestr('page.png', b'page bytes\r\n\x1a\x00' * 1000)
            archive.writestr('ComicInfo.xml', b'<ComicInfo><Title>Edited</Title></ComicInfo>')

    def verify_archive(self, data, password=None):
        with open_archive(BytesIO(data), password=password) as archive:
            self.assertEqual(archive.read('page.png'), b'page bytes\r\n\x1a\x00' * 1000)
            self.assertIn(b'Edited', archive.read('ComicInfo.xml'))

    def test_pipe_with_apparently_successful_seek_uses_streaming_headers(self):
        class WindowsPipe(BytesIO):
            def seek(self, *_):
                return 0
            def tell(self):
                return 0
        broken = WindowsPipe()
        self.write_archive(broken)
        with self.assertRaises((zipfile.BadZipFile, KeyError)):
            self.verify_archive(broken.getvalue())
        output = WindowsPipe()
        sink = _BinarySink(output)
        self.assertFalse(sink.seekable())
        with self.assertRaises(UnsupportedOperation):
            sink.seek(0)
        self.write_archive(sink)
        self.verify_archive(output.getvalue())

    def test_binary_subprocess_archive_round_trip_including_aes(self):
        for password in (None, 'synthetic archive password'):
            with self.subTest(encrypted=password is not None):
                data = run_bytes([sys.executable, '-c',
                    'import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())'],
                    input_writer=lambda stream: self.write_archive(stream, password),
                    max_output=65536)
                self.verify_archive(data, password)
