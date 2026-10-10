"""Real child-process outcomes, argument boundaries, timeouts and cancellation."""
import os
import sys
from threading import Event, Timer
import unittest

from commonUtils.wrappers.cmdShellWrapper import run_command, exec_cmd


class CommandTests(unittest.TestCase):
    def test_exit_status_and_streams_are_preserved(self):
        result = run_command([sys.executable, '-c',
            'import sys; print("out"); print("err", file=sys.stderr); sys.exit(7)'])
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout, ('out',))
        self.assertEqual(result.stderr, ('err',))
        self.assertFalse(result.success)

    def test_arguments_are_not_interpreted_by_a_shell(self):
        text = 'spaces & $(echo unwanted) "quotes"'
        result = run_command([sys.executable, '-c', 'import sys; print(sys.argv[1])', text])
        self.assertTrue(result.success)
        self.assertEqual(result.stdout, (text,))

    def test_timeout_still_applies_after_both_streams_close(self):
        result = run_command([sys.executable, '-c',
            'import os,time; os.close(1); os.close(2); time.sleep(10)'], timeout=.2)
        self.assertTrue(result.timed_out)
        self.assertFalse(result.success)

    def test_idle_timeout_and_live_cancellation(self):
        arguments = [sys.executable, '-c', 'import time; time.sleep(10)']
        self.assertTrue(run_command(arguments, idle_timeout=.2).timed_out)
        stop = Event()
        timer = Timer(.2, stop.set)
        timer.start()
        try:
            result = run_command(arguments, cancelled=stop.is_set)
        finally:
            timer.cancel()
        self.assertTrue(result.cancelled)
        self.assertFalse(result.success)

    def test_cancelled_before_start_and_legacy_output_contract(self):
        self.assertIsNone(run_command(['does-not-exist'], cancelled=lambda: True).returncode)
        self.assertEqual(exec_cmd('echo compatible'), ['compatible'])

    def test_missing_executable_and_implicit_shell_strings_are_rejected(self):
        with self.assertRaises(OSError):
            run_command(['this-executable-does-not-exist'])
        with self.assertRaises(TypeError):
            run_command('echo ambiguous')

    @unittest.skipUnless(os.name == 'posix', 'Requires POSIX process groups')
    def test_timeout_kills_descendant_that_ignores_term_and_keeps_pipes_open(self):
        code = '''import os,signal,time
child = os.fork()
if child == 0:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    print("child ready", flush=True)
    time.sleep(20)
else:
    time.sleep(20)
'''
        result = run_command([sys.executable, '-c', code], timeout=.4)
        self.assertTrue(result.timed_out)
        self.assertIn('child ready', result.stdout)
