"""Spool capture separates binary data, bounded diagnostics and cancellation."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import sys
import os
import errno
import unittest
from time import monotonic
from threading import Timer, Event, enumerate as threads
from unittest.mock import patch, MagicMock
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

    def test_blocked_input_still_obeys_timeout_and_cancellation(self):
        before = set(threads())
        for cancel in (False, True):
            with self.subTest(cancel=cancel):
                stop = Event()
                timer = Timer(.1, stop.set)
                if cancel:
                    timer.start()
                try:
                    started = monotonic()
                    with self.assertRaises(OperationCancelled if cancel else CommandTimeout):
                        self.command('import time; time.sleep(10)', input_data=b'x' * 1048576,
                                     timeout=3 if cancel else .1, cancelled=stop.is_set)
                    self.assertLess(monotonic() - started, 5)
                finally:
                    timer.cancel()
                    if cancel:
                        timer.join()
        self.assertFalse([thread for thread in set(threads()) - before
                          if thread.name == 'command-capture-stdin'])

    def test_large_binary_input_reaches_child_and_early_pipe_closure_is_safe(self):
        data = bytes(range(256)) * 8192
        result = self.command('import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())',
                              input_data=data, limit=len(data))
        self.assertEqual(result.stdout, data)
        self.assertEqual(result.returncode, 0)
        result = self.command('pass', input_data=data)
        self.assertEqual(result.returncode, 0)

    def test_cancelled_request_never_launches_a_child(self):
        with patch('commonUtils.integrations.wrappers.cmdShellWrapper.capture.subprocess.Popen') as start:
            with self.assertRaises(OperationCancelled):
                self.command('pass', cancelled=lambda: True)
            start.assert_not_called()

    @unittest.skipIf(os.name == 'nt', 'POSIX process-group inheritance fixture')
    def test_orphaned_stdin_holder_is_killed_when_parent_has_already_exited(self):
        source = ("import subprocess, sys; subprocess.Popen([sys.executable, '-c', "
                  "'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(10)'])")
        started = monotonic()
        with self.assertRaises(CommandTimeout):
            self.command(source, input_data=b'x' * 1048576, timeout=.2)
        self.assertLess(monotonic() - started, 5)

    def test_input_writer_error_is_propagated_and_child_is_retired(self):
        from commonUtils.integrations.wrappers.cmdShellWrapper import capture
        spawned = []
        source = 'import time; time.sleep(10)'
        arguments = [sys.executable, '-c', source]
        start = capture.subprocess.Popen
        def record(*args, **kwargs):
            process = start(*args, **kwargs)
            # Windows cleanup launches taskkill through the same subprocess module.
            if process.args == arguments:
                spawned.append(process)
            return process
        with patch.object(capture.subprocess, 'Popen', side_effect=record):
            with self.assertRaises(TypeError):
                self.command(source, input_data=object())
        self.assertEqual(len(spawned), 1)
        self.assertIsNotNone(spawned[0].poll())

    @unittest.skipUnless(hasattr(os, 'pread'), 'Incremental progress requires pread')
    def test_progress_failure_retires_a_blocked_input_writer(self):
        before = set(threads())
        def fail(_data):
            raise RuntimeError('synthetic progress failure')
        with self.assertRaisesRegex(RuntimeError, 'synthetic progress failure'):
            self.command("import sys,time; sys.stderr.write('ready'); sys.stderr.flush(); time.sleep(10)",
                         input_data=b'x' * 1048576, progress=fail, timeout=3)
        self.assertFalse([thread for thread in set(threads()) - before
                          if thread.name == 'command-capture-stdin'])

    def test_windows_closed_input_pipe_einval_is_an_early_eof(self):
        process = MagicMock()
        process.wait.return_value = 0
        process.stdin.write.side_effect = OSError(errno.EINVAL, 'synthetic closed pipe')
        with patch('commonUtils.integrations.wrappers.cmdShellWrapper.capture.subprocess.Popen', return_value=process):
            result = self.command('pass', input_data=b'fixture')
        self.assertEqual(result.returncode, 0)
        process.stdin.write.assert_called_once_with(b'fixture')
