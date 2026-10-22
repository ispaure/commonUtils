"""Spool capture separates binary data, bounded diagnostics and cancellation."""
import sys
import unittest
from commonUtils.integrations.wrappers.cmdShellWrapper.capture import run_captured, CommandTimeout
from commonUtils.runtime.operations import OperationCancelled
from commonUtils.runtime.diagnostics.redaction import redact


class CommandCaptureTests(unittest.TestCase):
    def command(self, source, **kwargs):
        return run_captured([sys.executable, '-c', source], **kwargs)

    def test_binary_output_truncates_after_completion_and_retains_stderr_tail(self):
        result = self.command("import sys; sys.stdout.buffer.write(b'\\0abcdef'); sys.stderr.write('x' * 70000); sys.exit(3)", limit=4)
        self.assertEqual(result.stdout, b'\0abc')
        self.assertEqual(result.stderr, b'x' * 65536)
        self.assertEqual(result.returncode, 3)
        self.assertTrue(result.truncated)

    def test_sensitive_commands_discard_both_streams_and_progress(self):
        updates = []
        result = self.command("import sys; print('secret'); sys.stderr.write('secret'); sys.exit(2)",
                              discard_output=True, progress=updates.append)
        self.assertEqual((result.stdout, result.stderr, result.returncode), (b'', b'', 2))
        self.assertEqual(updates, [])

    def test_timeout_and_cancellation_retire_process(self):
        source = 'import time; time.sleep(30)'
        with self.assertRaises(CommandTimeout):
            self.command(source, timeout=.05)
        with self.assertRaises(OperationCancelled):
            self.command(source, cancelled=lambda: True)

    def test_input_is_binary_and_environment_is_explicit(self):
        result = self.command('import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())', input_data=b'\0payload')
        self.assertEqual(result.stdout, b'\0payload')

    def test_complete_diagnostic_redaction_keeps_nonsecret_context(self):
        value = redact('https://user:pass@example.test/repo?token=abc password=secret Authorization: Bearer hidden')
        self.assertIn('example.test/repo', value)
        for secret in ('user:pass', 'abc', 'secret', 'hidden'):
            self.assertNotIn(secret, value)
