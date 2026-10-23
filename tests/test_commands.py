"""Real child-process outcomes, argument boundaries, timeouts and cancellation."""
import os
import sys
from threading import Event, Timer
import unittest
from unittest.mock import patch

from commonUtils.integrations.wrappers.cmdShellWrapper import run_command, exec_cmd


class CommandTests(unittest.TestCase):
    def test_macos_terminal_keeps_native_shell_in_requested_directory(self):
        from commonUtils.integrations.wrappers.cmdShellWrapper.terminal import _exec_cmd_new_window_macos
        import shlex
        folder = '/tmp/repo with spaces and \'quotes"'
        with patch('commonUtils.integrations.wrappers.cmdShellWrapper.terminal.subprocess.Popen') as launch:
            self.assertEqual(_exec_cmd_new_window_macos('pwd', folder), [])
            script = launch.call_args.args[0][2]
            expected = ('cd -- ' + shlex.quote(folder) + ' && pwd').replace('\\', '\\\\').replace('"', '\\"')
            self.assertIn(f'do script "{expected}"', script)
            self.assertNotIn('bash', script)
            self.assertEqual(_exec_cmd_new_window_macos('', folder), [])
            self.assertNotIn('&&', launch.call_args.args[0][2])

    def test_private_child_environment_does_not_change_parent(self):
        name = 'COMMONUTILS_CHILD_FIXTURE'
        previous = os.environ.get(name)
        result = run_command([sys.executable, '-c',
            'import os; print(os.environ.get("COMMONUTILS_CHILD_FIXTURE", "missing"))'],
            environment=dict(os.environ, **{name: 'synthetic-value'}))
        self.assertTrue(result.success)
        self.assertEqual(result.stdout, ('synthetic-value',))
        self.assertEqual(os.environ.get(name), previous)

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

    def test_pipe_read_failure_propagates_and_retires_the_child(self):
        from commonUtils.integrations.wrappers.cmdShellWrapper import result
        start = result.subprocess.Popen
        for name in ('stdout', 'stderr'):
            for error_type in (OSError, ValueError):
                with self.subTest(stream=name, error=error_type.__name__):
                    spawned, streams = [], []
                    def launch(*args, **kwargs):
                        child = start(*args, **kwargs)
                        spawned.append(child)
                        streams.extend((child.stdout, child.stderr))
                        stream = getattr(child, name)
                        from unittest.mock import Mock
                        reader = Mock(wraps=stream)
                        reader.read1.side_effect = error_type('synthetic pipe read failure')
                        setattr(child, name, reader)
                        return child
                    with patch.object(result.subprocess, 'Popen', side_effect=launch):
                        with self.assertRaisesRegex(error_type, 'synthetic pipe read failure'):
                            run_command([sys.executable, '-c', 'import time; time.sleep(10)'], timeout=.2)
                    self.assertEqual(len(spawned), 1)
                    self.assertIsNotNone(spawned[0].poll())
                    self.assertTrue(all(stream.closed for stream in streams))

    def test_timeout_retains_outcome_when_stopping_interrupts_a_pipe_reader(self):
        from threading import Event
        from unittest.mock import Mock
        from commonUtils.integrations.wrappers.cmdShellWrapper import result, process
        release = Event()
        start, terminate = result.subprocess.Popen, process.terminate_process_tree
        def interrupted_read(_size):
            if not release.wait(2):
                raise RuntimeError('fixture reader was not stopped')
            raise OSError('synthetic close interruption')
        def launch(*args, **kwargs):
            child = start(*args, **kwargs)
            child.stdout = Mock(wraps=child.stdout)
            child.stdout.read1.side_effect = interrupted_read
            return child
        def stop(child):
            release.set()
            terminate(child)
        with patch.object(result.subprocess, 'Popen', side_effect=launch), \
                patch.object(process, 'terminate_process_tree', side_effect=stop):
            captured = run_command([sys.executable, '-c', 'import time; time.sleep(10)'], timeout=.1)
        self.assertTrue(captured.timed_out)
        self.assertFalse(captured.success)

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
