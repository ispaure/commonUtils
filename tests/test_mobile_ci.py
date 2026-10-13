"""Host checks for mobile report integrity and source packaging, without a simulator."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from commonUtils.tests.mobile_smoke import TEST_NAMES

spec = importlib.util.spec_from_file_location('mobile_ci', Path(__file__).resolve().parents[1] / 'tools/mobile_ci.py')
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


class MobileCITests(unittest.TestCase):
    def report(self, **changes):
        report = dict(schema=1, suite='commonUtils-mobile-smoke', target='ios', sys_platform='ios',
                      environment='ios-simulator', success=True, failures=0, errors=0, skipped=0,
                      tests_run=7, expected_tests=list(TEST_NAMES))
        return report | changes

    def test_reports_require_real_target_and_all_tests(self):
        with TemporaryDirectory() as temporary:
            log, output = Path(temporary) / 'test.log', Path(temporary) / 'result.json'
            log.write_text(ci.PREFIX + json.dumps(self.report()) + '\n')
            self.assertTrue(ci.verify(log, 'ios', output)['success'])
            for changes in ({'sys_platform': 'darwin'}, {'environment': 'desktop-harness'},
                            {'target': 'host'}, {'success': False}, {'skipped': 1},
                            {'errors': 1}, {'failures': 1}, {'tests_run': 0}, {'expected_tests': []}):
                with self.subTest(changes=changes):
                    log.write_text(ci.PREFIX + json.dumps(self.report(**changes)))
                    with self.assertRaises(ValueError):
                        ci.verify(log, 'ios', output)
            for text in ('', 'build succeeded', ci.PREFIX + '{broken',
                         (ci.PREFIX + json.dumps(self.report()) + '\n') * 2):
                log.write_text(text)
                with self.assertRaises(ValueError):
                    ci.verify(log, 'ios', output)

    def test_staging_excludes_untracked_files_settings_and_git(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / 'repo'
            repo.mkdir()
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            (repo / 'tests').mkdir()
            (repo / 'tests/mobile_smoke.py').write_text('# smoke\n')
            (repo / 'private.ini').write_text('private')
            (repo / 'untracked.py').write_text('private')
            subprocess.run(['git', '-C', str(repo), 'add', 'tests', 'private.ini'], check=True)
            subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                            '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture'], check=True)
            ci.stage(repo, root / 'payload')
            self.assertEqual(sorted(path.relative_to(root / 'payload').as_posix()
                              for path in (root / 'payload').rglob('*') if path.is_file()),
                             ['commonUtils/tests/mobile_smoke.py', 'source.json'])
            with self.assertRaises(ValueError):
                ci.stage(repo, repo / 'nested')
            (repo / 'tests/mobile_smoke.py').write_text('# local changes\n')
            with self.assertRaises(ValueError):
                ci.stage(repo, root / 'strict')
            ci.stage(repo, root / 'local', allow_dirty=True)
            self.assertTrue(json.loads((root / 'local/source.json').read_text())['commonUtils_dirty'])
            self.assertEqual((root / 'local/commonUtils/tests/mobile_smoke.py').read_text(), '# local changes\n')
            self.assertFalse((root / 'local/commonUtils/untracked.py').exists())

    def test_host_harness_cannot_pass_as_mobile(self):
        for target in ('host', 'ios', 'android'):
            result = subprocess.run([sys.executable, '-m', 'commonUtils.tests.mobile_smoke', '--target', target],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode == 0, target == 'host', result.stdout + result.stderr)
            if target == 'host':
                self.assertIn('"environment": "desktop-harness"', result.stdout)
