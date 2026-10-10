"""Launcher pause flags must work with macOS's bundled Bash 3.2."""
from pathlib import Path
import subprocess
import shutil
import unittest


class LauncherPauseTests(unittest.TestCase):
    def test_pause_flags_on_bundled_bash(self):
        base = Path(__file__).resolve().parents[1] / 'launchers'
        bash = '/bin/bash' if Path('/bin/bash').is_file() else shutil.which('bash')
        if bash is None:
            self.skipTest('Unix launcher parsing requires Bash')
        for name in ('LaunchPythonProject_MAC.command', 'LaunchPythonProject_LINUX_UV.sh'):
            text = (base/name).read_text()
            # Execute the actual argument parsing, stopping before setup/downloads.
            prefix = text.split('\nesac',1)[0] + '\nesac\nprintf "%s" "$PAUSE_ON_EXIT"\n'
            for value, expected in [('false','false'),('FALSE','false'),('No','false'),
                                     ('off','false'),('0','false'),('','false'),
                                     ('true','true'),('TrUe','true'),('YES','true'),
                                     ('on','true'),('1','true')]:
                with self.subTest(launcher=name, value=value):
                    result = subprocess.run([bash,'-c',prefix,'launcher','root','config',value],
                                            capture_output=True,text=True,timeout=5)
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertEqual(result.stdout,expected)
                    self.assertNotIn('bad substitution',result.stderr)
            result = subprocess.run([bash,'-c',prefix,'launcher','root','config','invalid'],
                                    capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,1)
            self.assertIn('pause_on_exit must be',result.stderr)


if __name__ == '__main__':
    unittest.main()
