"""Optional project sync wrappers receive literal argv before application launch."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

LAUNCHERS = Path(__file__).resolve().parents[2] / 'launchers'
FAKE_UV = r'''
import json, os, pathlib, subprocess, sys
args = sys.argv[1:]
def record(kind, **values):
    with open(os.environ['LAUNCHER_TRACE'], 'a', encoding='utf-8') as f:
        f.write(json.dumps(dict(kind=kind, **values)) + '\n')
request = pathlib.Path('.python-version')
record('uv', argv=args, cwd=os.getcwd(), python_request=request.read_text() if request.is_file() else None)
if args == ['--version']:
    print('uv 0.13.4 fixture')
elif args[:2] == ['python', 'find']:
    pass
elif args[0] == 'venv':
    destination = pathlib.Path(args[-1]) / 'bin/python'
    destination.parent.mkdir(parents=True, exist_ok=True)
    shim = "import json,os,runpy,sys\nwith open(os.environ['LAUNCHER_TRACE'],'a',encoding='utf-8') as f: f.write(json.dumps(dict(kind='venv-python', executable=sys.argv[0],argv=sys.argv[1:]))+'\\n')\nargs=sys.argv[1:];sys.argv=args;runpy.run_path(args[0],run_name='__main__')\n"
    destination.write_text('#!' + sys.executable + '\n' + shim)
    destination.chmod(0o755)
elif args[0] == 'lock':
    pathlib.Path('uv.lock').write_text('fixture lock')
elif args[0] == 'sync':
    pathlib.Path(os.environ['UV_PROJECT_ENVIRONMENT']).mkdir(exist_ok=True)
    sys.exit(int(os.environ.get('FAKE_SYNC_STATUS', '0')))
elif args[0] == 'run':
    sys.exit(subprocess.run([sys.executable, *args[5:]]).returncode)
else:
    raise AssertionError('Unexpected fake uv operation')
'''
WRAPPER = '''import json, os, subprocess, sys
with open(os.environ['LAUNCHER_TRACE'], 'a', encoding='utf-8') as stream:
    stream.write(json.dumps(dict(kind='wrapper', argv=sys.argv[1:])) + '\\n')
status = int(os.environ.get('FAKE_WRAPPER_STATUS', '0'))
if status:
    raise SystemExit(status)
separator = sys.argv.index('--')
raise SystemExit(subprocess.run(sys.argv[separator + 1:]).returncode)
'''


@unittest.skipUnless(shutil.which('bash') and os.name != 'nt', 'Actual Bash launchers require Unix')
class UnixEnvironmentSyncTests(unittest.TestCase):
    @contextmanager
    def fixture(self, name, *, option=True):
        with TemporaryDirectory(prefix='launch café & (literal) $() %! ') as temporary:
            root = Path(temporary).resolve()
            source = root / 'Python source'
            source.mkdir()
            for filename, content in {'.python-version': '3.12.2', 'pyproject.toml': '[project]\nname="fixture"\nversion="0"',
                                      'uv.lock': 'fixture lock'}.items():
                (source / filename).write_text(content)
            (source / 'launch.py').write_text("import json,os,sys\nwith open(os.environ['LAUNCHER_TRACE'],'a') as f: f.write(json.dumps(dict(kind='app',argv=sys.argv[1:]))+'\\n')\n")
            wrapper = root / 'sync wrapper & $(literal); café.py'
            wrapper.write_text(WRAPPER)
            config = root / 'config.ini'
            config.write_text('[Launch]\nsource_dir=Python source\nlaunch_file=launch\n' +
                              ('environment_sync_wrapper=' + wrapper.name + '\n' if option else ''))
            binaries = root / 'bin'
            binaries.mkdir()
            uv = binaries / 'uv'
            uv.write_text('#!' + sys.executable + '\n' + FAKE_UV)
            uv.chmod(0o755)
            uname = binaries / 'uname'
            uname.write_text('#!/bin/sh\nif [ "$1" = -s ]; then echo "$FAKE_OS"; else echo arm64; fi\n')
            uname.chmod(0o755)
            trace = root / 'trace.jsonl'
            env = dict(os.environ, HOME=str(root), PATH=str(binaries) + os.pathsep + os.environ['PATH'],
                       LAUNCHER_TRACE=str(trace), FAKE_OS='Darwin' if 'MAC' in name else 'Linux')
            def run(**overrides):
                return subprocess.run(['bash', str(LAUNCHERS / name), str(root), str(config), 'false',
                    'space value', 'literal&value', '$(not-executed)', 'quote"value'],
                    cwd='/', env=dict(env, **overrides), text=True, capture_output=True, timeout=20)
            yield root, source, wrapper, uv, trace, run

    def names(self):
        return ('LaunchPythonProject_LINUX_UV.sh', 'LaunchPythonProject_MAC.command')

    def events(self, trace):
        return [json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []

    def test_fresh_owned_environment_wrapper_receives_literal_original_argv_before_launch(self):
        for name in self.names():
            with self.subTest(platform=name), self.fixture(name) as (root, source, wrapper, uv, trace, run):
                result = run()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                rows = self.events(trace)
                bootstrap = next(x for x in rows if x['kind'] == 'uv' and x['argv'][0] == 'venv')
                self.assertEqual(bootstrap['argv'], ['venv', '--no-python-downloads', str(root / '.venv')])
                self.assertEqual(bootstrap['cwd'], str(source))
                self.assertEqual(bootstrap['python_request'], '3.12.2')
                invoked = next(x for x in rows if x['kind'] == 'venv-python')
                self.assertEqual(invoked['executable'], str(root / '.venv/bin/python'))
                flags = ['sync', '--locked', *([] if 'MAC' in name else ['--no-dev']), '--no-python-downloads']
                self.assertEqual(invoked['argv'], [str(wrapper), 'sync', '--project-root', str(root), '--venv', str(root / '.venv'), '--', str(uv), *flags])
                self.assertEqual([x['kind'] for x in rows if x['kind'] in ('wrapper', 'app')], ['wrapper', 'app'])
                self.assertEqual(rows[-1], dict(kind='app', argv=['space value', 'literal&value', '$(not-executed)', 'quote"value']))

    def test_wrapper_failure_preserves_exit_and_prevents_sync_and_application(self):
        for name in self.names():
            with self.subTest(platform=name), self.fixture(name) as (_, _, _, _, trace, run):
                result = run(FAKE_WRAPPER_STATUS='37')
                self.assertEqual(result.returncode, 37, result.stdout + result.stderr)
                rows = self.events(trace)
                self.assertFalse(any(x['kind'] == 'app' or x['kind'] == 'uv' and x['argv'][0] == 'sync' for x in rows))

    def test_configured_missing_wrapper_fails_before_environment_mutation(self):
        for name in self.names():
            with self.subTest(platform=name), self.fixture(name) as (root, _, wrapper, _, trace, run):
                wrapper.unlink()
                result = run()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Environment sync wrapper', result.stderr)
                self.assertFalse((root / '.venv').exists())
                self.assertFalse(trace.exists())

    def test_invalid_nonempty_environment_is_preserved_without_bootstrap_or_sync(self):
        for name in self.names():
            with self.subTest(platform=name), self.fixture(name) as (root, _, _, _, trace, run):
                (root / '.venv').mkdir()
                marker = root / '.venv/keep-owner-state'
                marker.write_text('preserve')
                result = run()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('nonempty environment was preserved', result.stderr)
                self.assertEqual(marker.read_text(), 'preserve')
                self.assertFalse(any(x['kind'] == 'uv' and x['argv'][0] in ('venv', 'sync') for x in self.events(trace)))

    def test_wrapper_forwards_uv_failure_and_absent_option_keeps_original_sync_flags(self):
        for name in self.names():
            with self.subTest(platform=name), self.fixture(name) as (_, _, _, _, trace, run):
                result = run(FAKE_SYNC_STATUS='41')
                self.assertEqual(result.returncode, 41, result.stdout + result.stderr)
                self.assertFalse(any(x['kind'] == 'app' for x in self.events(trace)))
            with self.subTest(platform=name, option=False), self.fixture(name, option=False) as (_, _, _, _, trace, run):
                result = run()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                rows = self.events(trace)
                self.assertFalse(any(x['kind'] in ('wrapper', 'venv-python') or x['kind'] == 'uv' and x['argv'][0] == 'venv' for x in rows))
                sync = next(x for x in rows if x['kind'] == 'uv' and x['argv'][0] == 'sync')
                self.assertEqual(sync['argv'], ['sync', '--locked', *([] if 'MAC' in name else ['--no-dev']), '--no-python-downloads'])

    def test_existing_owned_python_is_reused_without_bootstrap(self):
        for name in self.names():
            with self.subTest(platform=name), self.fixture(name) as (_, _, _, _, trace, run):
                self.assertEqual(run().returncode, 0)
                trace.unlink()
                result = run()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                rows = self.events(trace)
                self.assertTrue(any(x['kind'] == 'venv-python' for x in rows))
                self.assertFalse(any(x['kind'] == 'uv' and x['argv'][0] == 'venv' for x in rows))

    def test_personal_empty_disables_wrapper_and_invalid_relative_paths_fail_early(self):
        for name in self.names():
            with self.subTest(platform=name), self.fixture(name) as (root, _, wrapper, _, trace, run):
                personal = root / 'personal settings.ini'
                personal.write_text('[Launch]\nenvironment_sync_wrapper=\n')
                wrapper.unlink()
                result = run(COMMONUTILS_PERSONAL_CONFIG_FILE=str(personal))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertFalse(any(x['kind'] == 'wrapper' for x in self.events(trace)))
            for value in ('../outside.py', '/absolute.py'):
                with self.subTest(platform=name, value=value), self.fixture(name) as (root, _, _, _, trace, run):
                    personal = root / 'personal settings.ini'
                    personal.write_text('[Launch]\nenvironment_sync_wrapper=' + value + '\n')
                    result = run(COMMONUTILS_PERSONAL_CONFIG_FILE=str(personal))
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(trace.exists())
                    self.assertFalse((root / '.venv').exists())

    def test_unix_shell_syntax_and_windows_crlf_are_preserved(self):
        for name in self.names():
            subprocess.run(['bash', '-n', str(LAUNCHERS / name)], check=True, timeout=10)
        raw = (LAUNCHERS / 'LaunchPythonProject_WIN.bat').read_bytes()
        self.assertIn(b'\r\n', raw)
        self.assertNotIn(b'\n', raw.replace(b'\r\n', b''))


@unittest.skipUnless(os.name == 'nt' and shutil.which('uv.exe'), 'Native Windows and an existing uv.exe are required')
class WindowsEnvironmentSyncTests(unittest.TestCase):
    def test_actual_batch_wrapper_uses_owned_python_and_literal_metacharacter_path(self):
        with TemporaryDirectory(prefix='launcher café & (literal)! ') as temporary:
            root = Path(temporary).resolve()
            (root / '.python-version').write_text(sys.version.split()[0])
            (root / 'pyproject.toml').write_text('[project]\nname="fixture"\nversion="0.0.0"\nrequires-python=">=3.10"\ndependencies=[]\n')
            (root / 'launch.py').write_text("raise AssertionError('Application must not launch after wrapper failure')")
            wrapper = root / 'sync %literal% & (guard)!.py'
            wrapper.write_text(WRAPPER)
            config = root / 'config.ini'
            config.write_text('[Launch]\nsource_dir=.\nlaunch_file=launch\nenvironment_sync_wrapper=' + wrapper.name + '\n')
            trace = root / 'trace.jsonl'
            env = dict(os.environ, LAUNCHER_TRACE=str(trace), FAKE_WRAPPER_STATUS='37', literal='MUST_NOT_EXPAND')
            command = subprocess.list2cmdline([str(LAUNCHERS / 'LaunchPythonProject_WIN.bat'), str(root), str(config), 'false'])
            result = subprocess.run(['cmd.exe', '/d', '/c', command], env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 37, result.stdout + result.stderr)
            rows = [json.loads(line) for line in trace.read_text().splitlines()]
            argv = rows[-1]['argv']
            self.assertEqual(argv[:6], ['sync', '--project-root', str(root), '--venv', str(root / '.venv'), '--'])
            self.assertEqual(argv[7:], ['sync', '--locked', '--no-dev', '--no-python-downloads'])
            self.assertTrue((root / '.venv/Scripts/python.exe').is_file())
