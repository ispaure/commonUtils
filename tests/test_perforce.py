import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from commonUtils.wrappers.perforce import PerforceRuntime, configure_runtime
from commonUtils.wrappers.perforce import p4_utils
from commonUtils.wrappers import cmdShellWrapper

class PerforceTests(unittest.TestCase):
    def tearDown(self):
        configure_runtime()

    def test_final_record_and_spaces(self):
        lines = ['... clientFile /work/a b.txt', '... depotFile //depot/a', '', '... clientFile /work/c']
        with patch.object(p4_utils, 'exec_p4_command', return_value=lines):
            self.assertEqual(p4_utils.p4_fstat_dict('/work/...'), [
                {'clientFile': '/work/a b.txt', 'depotFile': '//depot/a'}, {'clientFile': '/work/c'}])

    def test_binary_placeholder_preserves_existing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'sub'/'file'
            p4_utils.create_empty_binary_file(path)
            self.assertEqual(path.read_bytes(), b'\0')
            path.write_bytes(b'original')
            p4_utils.create_empty_binary_file(path)
            self.assertEqual(path.read_bytes(), b'original')

    def test_lazy_environment_and_allowed_keys(self):
        environment = {'P4USER': 'a b'}
        configure_runtime(PerforceRuntime(environment=lambda: environment))
        with patch.object(p4_utils, 'exec_p4_command') as run:
            p4_utils.set_p4_env_settings()
            self.assertIn('a b', run.call_args.args[0])
            environment['UNSUPPORTED'] = 'value'
            with self.assertRaises(ValueError):
                p4_utils.set_p4_env_settings()

    def test_nonzero_diagnostics_and_timeout(self):
        result = cmdShellWrapper.CommandResult(1, stderr=('file - no such file(s).',))
        with patch.object(p4_utils, 'get_os', return_value=p4_utils.OS.WIN), patch.object(cmdShellWrapper, 'run_command', return_value=result):
            self.assertEqual(p4_utils.exec_p4_command('p4 fstat file'), result.lines)
        def fail(severity, title, message, **kwargs):
            if severity == p4_utils.Severity.CRITICAL:
                raise RuntimeError(message)
        result = cmdShellWrapper.CommandResult(-1, stdout=('partial',), timed_out=True)
        with patch.object(p4_utils, 'get_os', return_value=p4_utils.OS.WIN), patch.object(cmdShellWrapper, 'run_command', return_value=result), patch.object(p4_utils, 'log', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'timed out'):
                p4_utils.exec_p4_command('p4 edit file')
