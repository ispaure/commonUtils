"""Execute native launcher readers against sparse personal configuration."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import shutil
import subprocess
import unittest


class LauncherLayersTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.defaults = self.root / 'software defaults.ini'
        self.personal = self.root / 'personal settings.ini'
        self.defaults.write_text('[Launch]\nsource_dir=Python\nensure_user_dir=Server\n')
        self.personal.write_text('[Launch]\nensure_user_dir=\n')
        self.base = Path(__file__).resolve().parents[1] / 'launchers'

    def unix(self, launcher, key):
        bash = shutil.which('bash')
        if bash is None:
            self.skipTest('Bash reader is checked on Unix platforms')
        text = (self.base / launcher).read_text()
        function = 'read_launch_value() {' + text.split('read_launch_value() {', 1)[1].split('\n}\n', 1)[0] + '\n}'
        script = 'fail(){ printf "%s" "$1" >&2; exit 1; }; CONFIG_FILE="$1"; COMMONUTILS_PERSONAL_CONFIG_FILE="$2";\n' + function + '\nread_launch_value "$3" result; printf "%s" "$result"'
        return subprocess.run([bash, '-c', script, 'launcher', str(self.defaults), str(self.personal), key],
                              capture_output=True, text=True, timeout=20)

    def test_unix_missing_personal_keys_inherit_and_explicit_empty_is_retained(self):
        for launcher in ('LaunchPythonProject_MAC.command', 'LaunchPythonProject_LINUX_UV.sh'):
            result = self.unix(launcher, 'source_dir')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, 'Python')
            result = self.unix(launcher, 'ensure_user_dir')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '')
            self.personal.write_text('[Other]\nsource_dir=wrong\n[Launch]\nsource_dir=Personal Python\n')
            result = self.unix(launcher, 'source_dir')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, 'Personal Python')
            self.personal.write_text('[Launch]\nensure_user_dir=\n')

    def test_unix_duplicate_in_either_layer_is_rejected(self):
        for launcher in ('LaunchPythonProject_MAC.command', 'LaunchPythonProject_LINUX_UV.sh'):
            self.defaults.write_text('[Launch]\nsource_dir=Python\nsource_dir=duplicate\n')
            self.personal.write_text('[Launch]\nsource_dir=personal\n')
            self.assertNotEqual(self.unix(launcher, 'source_dir').returncode, 0)
            self.defaults.write_text('[Launch]\nsource_dir=Python\n')
            self.personal.write_text('[Launch]\nsource_dir=one\nsource_dir=two\n')
            self.assertNotEqual(self.unix(launcher, 'source_dir').returncode, 0)

    @unittest.skipUnless(os.name == 'nt', 'Windows reader is checked on native Windows')
    def test_windows_reader_inherits_overrides_and_rejects_duplicates(self):
        text = (self.base / 'LaunchPythonProject_WIN.bat').read_text()
        command = next(line for line in text.splitlines() if line.startswith('powershell.exe ') and '$path' in line)
        script = command.split('-Command "', 1)[1][:-1]
        output = self.root / 'result.txt'
        environment = dict(os.environ, CONFIG_FILE=str(self.defaults), COMMONUTILS_PERSONAL_CONFIG_FILE=str(self.personal),
                           CONFIG_OUTPUT=str(output), CONFIG_KEY='source_dir')
        def run():
            return subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script],
                                  env=environment, capture_output=True, text=True, timeout=20)
        result = run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.read_text(encoding='utf-8-sig'), 'Python')
        self.personal.write_text('[Launch]\nsource_dir=Personal Python\n')
        self.assertEqual(run().returncode, 0)
        self.assertEqual(output.read_text(encoding='utf-8-sig'), 'Personal Python')
        self.personal.write_text('[Launch]\nsource_dir=\n')
        self.assertEqual(run().returncode, 0)
        self.assertEqual(output.read_text(encoding='utf-8-sig'), '')
        self.personal.write_text('[Launch]\nsource_dir=one\nsource_dir=two\n')
        self.assertNotEqual(run().returncode, 0)
