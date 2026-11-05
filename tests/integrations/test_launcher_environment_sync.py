"""Optional project sync wrappers receive literal argv before application launch."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

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


WINDOWS = os.name == 'nt'
# This diagnostic child queries one owned executable. It never terminates owners,
# reads process command lines, or changes Restart Manager state beyond its session.
LOCK_OWNERS = r"""
import ctypes as c,json,sys
from ctypes import wintypes as w
class Process(c.Structure):
    _fields_=[('pid',w.DWORD),('started',w.FILETIME)]
class Info(c.Structure):
    _fields_=[('process',Process),('app',w.WCHAR*256),('service',w.WCHAR*64),
              ('kind',w.UINT),('status',w.ULONG),('session',w.DWORD),('restartable',w.BOOL)]
r=c.WinDLL('rstrtmgr',use_last_error=True)
for name,arguments in {
 'RmStartSession':[c.POINTER(w.DWORD),w.DWORD,w.LPWSTR],
 'RmRegisterResources':[w.DWORD,w.UINT,c.POINTER(w.LPCWSTR),w.UINT,c.POINTER(Process),w.UINT,c.POINTER(w.LPCWSTR)],
 'RmGetList':[w.DWORD,c.POINTER(w.UINT),c.POINTER(w.UINT),c.POINTER(Info),c.POINTER(w.DWORD)],
 'RmEndSession':[w.DWORD]}.items():
    getattr(r,name).argtypes=arguments;getattr(r,name).restype=w.DWORD
session=w.DWORD();status=r.RmStartSession(c.byref(session),0,c.create_unicode_buffer(33))
result={'query_error':status}
if status==0:
    try:
        status=r.RmRegisterResources(session,1,(w.LPCWSTR*1)(sys.argv[1]),0,None,0,None)
        result={'query_error':status}
        if status==0:
            needed,count,reasons=w.UINT(),w.UINT(),w.DWORD()
            status=r.RmGetList(session,c.byref(needed),c.byref(count),None,c.byref(reasons))
            result={'query_error':status,'needed':needed.value}
            if status==0:result={'query_error':0,'owners':[]}
            elif status==234 and 0<needed.value<=32:
                count.value=needed.value;rows=(Info*count.value)()
                status=r.RmGetList(session,c.byref(needed),c.byref(count),rows,c.byref(reasons))
                result={'query_error':status}
                if status==0:result['owners']=[{'pid':x.process.pid,
                    'creation_time':(x.process.started.dwHighDateTime<<32)|x.process.started.dwLowDateTime}
                    for x in rows[:count.value]]
    finally:r.RmEndSession(session)
print(json.dumps(result))
"""


def fixture_lock_owners(target):
    result = subprocess.run([sys.executable, '-I', '-c', LOCK_OWNERS, str(target)],
                            capture_output=True, text=True, timeout=3)
    if result.returncode or len(result.stdout) > 16384:
        raise ValueError('Bounded lock diagnostic failed')
    return json.loads(result.stdout)


def fixture_interpreter_identity(root, target):
    root, target = Path(root).absolute(), Path(target).absolute()
    expected = root / '.venv/Scripts/python.exe'
    if target != expected or root.resolve() != root:
        raise ValueError('Cleanup target is not the owned fixture interpreter')
    paths = (root, root / '.venv', root / '.venv/Scripts', expected)
    infos = []
    for path in (*root.parents, *paths):
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Cleanup must not follow a link or junction')
        if not (stat.S_ISREG(info.st_mode) if path == expected else stat.S_ISDIR(info.st_mode)):
            raise ValueError('Unexpected fixture path type')
        if path in paths:
            infos.append((info.st_dev, info.st_ino))
    return tuple(infos)


def cleanup_windows_fixture(temporary):
    """Bound only transient Windows locks on this fixture's own interpreter."""
    try:
        temporary.cleanup()
        return
    except PermissionError as original:
        if not WINDOWS or getattr(original, 'winerror', None) not in (5, 32, 33) or not original.filename:
            raise
        try:
            identity = fixture_interpreter_identity(temporary.name, original.filename)
        except (OSError, ValueError):
            raise original
        try:
            evidence = fixture_lock_owners(original.filename)
        except Exception as diagnostic_error:
            evidence = {'diagnostic_error': type(diagnostic_error).__name__}
        note = json.dumps({'winerror': original.winerror, 'resource_owners': evidence}, sort_keys=True)
        original.add_note('Owned launcher interpreter first cleanup failure: ' + note)
        print('Owned launcher interpreter first cleanup failure: ' + note, file=sys.stderr, flush=True)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                if fixture_interpreter_identity(temporary.name, original.filename) != identity:
                    raise ValueError('Fixture identity changed')
                temporary.cleanup()
                if Path(temporary.name).exists():
                    raise ValueError('Fixture cleanup did not remove its root')
                print('Owned launcher interpreter cleanup: removed after transient lock', file=sys.stderr, flush=True)
                return
            except PermissionError as retry:
                if retry.filename != original.filename or getattr(retry, 'winerror', None) not in (5, 32, 33):
                    raise original from retry
            except (OSError, ValueError) as failure:
                raise original from failure
            time.sleep(min(0.05, max(0, deadline - time.monotonic())))
        raise original


@contextmanager
def windows_fixture_directory():
    temporary = TemporaryDirectory(prefix='launcher café & (literal)! ')
    try:
        yield temporary.name
    finally:
        cleanup_windows_fixture(temporary)


def run_windows_batch(arguments, *, env, timeout=60):
    command = subprocess.list2cmdline(arguments)
    # CMD uses its OEM code page while Python may run in UTF-8 mode. Capture
    # raw bytes: a decoding exception in Windows' reader thread loses stdout.
    # Pass a raw command string so Popen cannot CRT-escape CMD's inner quotes.
    return subprocess.run(f'cmd.exe /d /v:off /s /c "{command}"',
                          env=env, capture_output=True, timeout=timeout)


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


class WindowsBatchInvocationTests(unittest.TestCase):
    def test_cmd_receives_one_raw_command_with_literal_path_quotes(self):
        batch = r'C:\checkout café & (literal)!\LaunchPythonProject_WIN.bat'
        root = r'C:\Temp\launcher café & (literal)! probe'
        config = root + r'\config.ini'
        environment = {'literal': 'MUST_NOT_EXPAND', 'FAKE_WRAPPER_STATUS': '37'}
        options = dict(env=environment, timeout=60)
        with patch.object(subprocess, 'run') as run:
            result = run_windows_batch([batch, root, config, 'false'], **options)
        run.assert_called_once()
        self.assertIs(result, run.return_value)
        raw_command = run.call_args.args[0]
        # A list would undergo a second CRT serialization before CreateProcess,
        # inserting backslashes before the quotes that CMD needs to see literally.
        self.assertIsInstance(raw_command, str)
        prefix = 'cmd.exe /d /v:off /s /c "'
        self.assertTrue(raw_command.startswith(prefix), raw_command)
        self.assertTrue(raw_command.endswith('"'), raw_command)
        payload = raw_command[len(prefix):-1]  # CMD /s removes only the outer pair.
        self.assertEqual(payload, f'"{batch}" "{root}" "{config}" false')
        self.assertNotIn('\\"', raw_command)
        self.assertEqual(run.call_args.kwargs, dict(options, capture_output=True))
        self.assertIs(run.call_args.kwargs['env'], environment)


    def test_cmd_capture_preserves_oem_bytes_under_utf8_python_without_decoder_thread(self):
        # Real byte-emitting child proves the capture contract on every host;
        # native CMD/metacharacter acceptance remains the Windows-only test.
        environment = dict(os.environ, PYTHONUTF8='1')
        emitted = b'launcher caf\x82\r\n'
        diagnostic = b'raw stderr \xff\r\n'
        code = "import os,sys;os.write(1," + repr(emitted) + ");os.write(2," + repr(diagnostic) + ");sys.exit(37)"
        real_run = subprocess.run
        def emit_bytes(command, **options):
            self.assertIsInstance(command, str)
            self.assertTrue(command.startswith('cmd.exe /d /v:off /s /c '))
            self.assertEqual(options, dict(env=environment, capture_output=True, timeout=10))
            return real_run([sys.executable, '-I', '-c', code], **options)
        with patch.object(subprocess, 'run', side_effect=emit_bytes):
            result = run_windows_batch(['synthetic.bat', 'literal café path'], env=environment, timeout=10)
        self.assertEqual(result.returncode, 37, result.stdout + result.stderr)
        self.assertEqual(result.stdout, emitted)
        self.assertEqual(result.stderr, diagnostic)


class WindowsLauncherDiagnosticSourceTests(unittest.TestCase):
    def test_path_diagnostics_do_not_turn_literal_paths_into_cmd_syntax(self):
        # This source guard checks CMD metacharacter exposure, not native CMD
        # execution. The Windows integration below remains the acceptance test.
        source = (LAUNCHERS / 'LaunchPythonProject_WIN.bat').read_text()
        path_variables = {'PROJECT_ROOT', 'CONFIG_FILE', 'SOURCE_DIR', 'VENV_DIR',
                          'LAUNCH_PATH', 'CHECK_PATH', 'CHECK_FILE', 'UV_EXE',
                          'UV_INSTALL_DIR', 'UV_INSTALLER_FILE', 'ENSURE_USER_PATH',
                          'ENSURE_USER_DIR', 'LAUNCH_FILE_VALUE'}
        variable = re.compile(r'%([A-Z_]+)(?::[^%]*)?%')
        diagnostics = [line.strip() for line in source.splitlines()
                       if line.lstrip().lower().startswith('echo ')
                       and any(match[1] in path_variables for match in variable.finditer(line))]
        self.assertTrue(diagnostics)
        self.assertTrue(any('%PROJECT_ROOT%' in line for line in diagnostics))
        literal_path = r'C:\launcher café & (literal)! %literal%'
        for line in diagnostics:
            with self.subTest(diagnostic=line):
                expanded = variable.sub(lambda match: literal_path if match[1] in path_variables
                                        else 'fixed-label', line)
                # Quoted spans and caret-escaped characters are literal in CMD.
                # Any remaining grouping, command or redirection token is unsafe
                # when CMD parses the entire parenthesized diagnostic block.
                unquoted = re.sub(r'"[^"\r\n]*"|\^.', '', expanded)
                self.assertNotRegex(unquoted, r'[&|<>()"]')


class WindowsFixtureCleanupTests(unittest.TestCase):
    def fixture(self):
        root = Path(self.enterContext(TemporaryDirectory())).resolve()
        target = root / '.venv/Scripts/python.exe'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'owned executable fixture')
        return root, target

    def locked(self, target):
        error = PermissionError(13, 'fixture is locked', str(target))
        error.winerror = 5
        return error

    def test_transient_owned_interpreter_lock_is_diagnosed_before_actual_removal(self):
        root, target = self.fixture()
        error = self.locked(target)
        cleanup = Mock(side_effect=[error, lambda: None])
        def attempt():
            if cleanup.call_count == 0:
                cleanup()
            else:
                cleanup()
                shutil.rmtree(root)
        temporary = type('Owned', (), {'name': str(root), 'cleanup': staticmethod(attempt)})()
        with patch(__name__ + '.WINDOWS', True), patch(__name__ + '.fixture_lock_owners', return_value={'owners': [{'pid': 7}]}) as diagnose:
            cleanup_windows_fixture(temporary)
        diagnose.assert_called_once_with(str(target))
        self.assertFalse(root.exists())
        self.assertEqual(cleanup.call_count, 2)
        self.assertIn('"pid": 7', error.__notes__[0])

    def test_permanent_lock_preserves_original_error_and_evidence(self):
        root, target = self.fixture()
        original = self.locked(target)
        cleanup = Mock(side_effect=original)
        temporary = type('Owned', (), {'name': str(root), 'cleanup': cleanup})()
        with patch(__name__ + '.WINDOWS', True), patch(__name__ + '.fixture_lock_owners', side_effect=TimeoutError), \
                patch(__name__ + '.time.monotonic', side_effect=[0, 0, 1, 4]), patch(__name__ + '.time.sleep'):
            with self.assertRaises(PermissionError) as raised:
                cleanup_windows_fixture(temporary)
        self.assertIs(raised.exception, original)
        self.assertIn('TimeoutError', original.__notes__[0])
        self.assertTrue(target.is_file())

    def test_unowned_path_and_symlink_are_never_retried_or_diagnosed(self):
        root, target = self.fixture()
        outside = root / 'other.exe'
        outside.write_bytes(b'preserve')
        for failed in (outside, target):
            with self.subTest(path=failed.name):
                if failed == target:
                    target.unlink()
                    try:
                        target.symlink_to(outside)
                    except (OSError, NotImplementedError):
                        continue  # Exact outside-path case still runs on hosts without symlink privileges.
                error = self.locked(failed)
                cleanup = Mock(side_effect=error)
                temporary = type('Owned', (), {'name': str(root), 'cleanup': cleanup})()
                with patch(__name__ + '.WINDOWS', True), patch(__name__ + '.fixture_lock_owners') as diagnose:
                    with self.assertRaises(PermissionError) as raised:
                        cleanup_windows_fixture(temporary)
                self.assertIs(raised.exception, error)
                self.assertEqual(cleanup.call_count, 1)
                diagnose.assert_not_called()
                self.assertEqual(outside.read_bytes(), b'preserve')

    def test_other_platforms_or_error_codes_keep_normal_cleanup_failure(self):
        root, target = self.fixture()
        for windows, code in ((False, 5), (True, 87)):
            with self.subTest(windows=windows, code=code):
                error = self.locked(target)
                error.winerror = code
                cleanup = Mock(side_effect=error)
                temporary = type('Owned', (), {'name': str(root), 'cleanup': cleanup})()
                with patch(__name__ + '.WINDOWS', windows), patch(__name__ + '.fixture_lock_owners') as diagnose:
                    with self.assertRaises(PermissionError) as raised:
                        cleanup_windows_fixture(temporary)
                self.assertIs(raised.exception, error)
                self.assertEqual(cleanup.call_count, 1)
                diagnose.assert_not_called()

    def test_lock_diagnostic_has_fixed_stdlib_child_and_timeout(self):
        result = type('Result', (), {'returncode': 0, 'stdout': '{"owners": []}'})()
        with patch.object(subprocess, 'run', return_value=result) as run:
            self.assertEqual(fixture_lock_owners('literal owned path'), {'owners': []})
        self.assertEqual(run.call_args.args[0], [sys.executable, '-I', '-c', LOCK_OWNERS, 'literal owned path'])
        self.assertEqual(run.call_args.kwargs, dict(capture_output=True, text=True, timeout=3))

    def test_replaced_fixture_identity_stops_before_second_cleanup(self):
        root, target = self.fixture()
        error = self.locked(target)
        cleanup = Mock(side_effect=error)
        temporary = type('Owned', (), {'name': str(root), 'cleanup': cleanup})()
        with patch(__name__ + '.WINDOWS', True), patch(__name__ + '.fixture_lock_owners', return_value={}), \
                patch(__name__ + '.fixture_interpreter_identity', side_effect=[('original',), ('replaced',)]):
            with self.assertRaises(PermissionError) as raised:
                cleanup_windows_fixture(temporary)
        self.assertIs(raised.exception, error)
        self.assertEqual(cleanup.call_count, 1)


@unittest.skipUnless(os.name == 'nt' and shutil.which('uv.exe'), 'Native Windows and an existing uv.exe are required')
class WindowsEnvironmentSyncTests(unittest.TestCase):
    def test_actual_batch_wrapper_uses_owned_python_and_literal_metacharacter_path(self):
        with windows_fixture_directory() as temporary:
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
            result = run_windows_batch([str(LAUNCHERS / 'LaunchPythonProject_WIN.bat'),
                                        str(root), str(config), 'false'],
                                       env=env, timeout=60)
            self.assertEqual(result.returncode, 37, result.stdout + result.stderr)
            rows = [json.loads(line) for line in trace.read_text().splitlines()]
            argv = rows[-1]['argv']
            self.assertEqual(argv[:6], ['sync', '--project-root', str(root), '--venv', str(root / '.venv'), '--'])
            self.assertEqual(argv[7:], ['sync', '--locked', '--no-dev', '--no-python-downloads'])
            self.assertTrue((root / '.venv/Scripts/python.exe').is_file())
