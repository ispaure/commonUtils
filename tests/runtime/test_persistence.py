"""Publication races and staging cleanup, independent of text format policy."""
from contextlib import ExitStack, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.persistence import atomic_write_bytes
from commonUtils.persistence import promote_path
from unittest.mock import patch
from commonUtils.persistence import publication


class PersistenceTests(unittest.TestCase):
    def test_android_arm64_without_libc_wrapper_uses_atomic_kernel_operation(self):
        import ctypes
        import errno
        from types import SimpleNamespace
        from unittest.mock import Mock
        from commonUtils.runtime.platform import OS
        call = Mock(return_value=0)
        with patch('commonUtils.runtime.platform.get_os', return_value=OS.ANDROID), \
                patch('platform.machine', return_value='aarch64'), \
                patch.object(publication.ctypes, 'CDLL', return_value=SimpleNamespace(syscall=call)):
            publication.rename_exclusive('staged', 'destination')
            call.assert_called_once_with(276, -100, b'staged', -100, b'destination', 1)
            self.assertEqual(call.argtypes[0], ctypes.c_long)
            call.return_value = -1
            with patch.object(publication.ctypes, 'get_errno', return_value=errno.EEXIST):
                with self.assertRaises(FileExistsError):
                    publication.rename_exclusive('staged', 'destination')
            with patch.object(publication.ctypes, 'get_errno', return_value=errno.ENOSYS):
                with self.assertRaises(OSError) as error:
                    publication.rename_exclusive('staged', 'destination')
                self.assertEqual(error.exception.errno, errno.ENOSYS)

    def test_missing_native_rename_is_a_filesystem_error_and_preserves_paths(self):
        import errno
        from commonUtils.runtime.platform import OS
        from commonUtils.filesystem.rename import rename_path
        with TemporaryDirectory() as directory:
            source, destination = Path(directory) / 'source', Path(directory) / 'destination'
            source.write_bytes(b'original')
            for platform in (OS.MAC, OS.IOS, OS.LINUX, OS.ANDROID):
                for rename in (publication.rename_exclusive, rename_path):
                    with self.subTest(platform=platform, rename=rename.__name__), \
                            patch('commonUtils.runtime.platform.get_os', return_value=platform), \
                            patch.object(publication.ctypes, 'CDLL', return_value=object()):
                        with self.assertRaises(OSError) as caught:
                            rename(source, destination)
                        self.assertEqual(caught.exception.errno, errno.ENOTSUP)
                        self.assertEqual(source.read_bytes(), b'original')
                        self.assertFalse(destination.exists())

    def test_tree_publication_keeps_recovery_copy(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            old, staged = root / 'app', root / 'staged'
            old.mkdir(); staged.mkdir()
            (old / 'original').write_text('old')
            (staged / 'new').write_text('new')
            backup = promote_path(staged, old)
            self.assertEqual((backup / 'original').read_text(), 'old')
            self.assertEqual((old / 'new').read_text(), 'new')

    def test_failed_promotion_restores_original(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            old, staged = root / 'app', root / 'staged'
            old.write_bytes(b'original'); staged.write_bytes(b'new')
            with self.intercept_moves(lambda source, target: self.fail_stage(source, staged)):
                with self.assertRaisesRegex(OSError, 'promotion failed'):
                    promote_path(staged, old)
            self.assertEqual(old.read_bytes(), b'original')
            self.assertEqual(staged.read_bytes(), b'new')

    @contextmanager
    def intercept_moves(self, before):
        # Exercise the same race against both legacy rename and no-replace moves.
        rename, exclusive = Path.rename, publication.rename_exclusive
        def ordinary(source, target):
            before(Path(source), Path(target))
            return rename(source, target)
        def no_replace(source, target):
            before(Path(source), Path(target))
            return exclusive(source, target)
        with ExitStack() as patches:
            patches.enter_context(patch.object(Path, 'rename', ordinary))
            patches.enter_context(patch.object(publication, 'rename_exclusive', no_replace))
            yield

    @staticmethod
    def fail_stage(source, staged):
        if source == staged:
            raise OSError('promotion failed')

    def test_new_destination_appearing_at_publication_is_preserved(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            staged, target = root / 'stage', root / 'app'
            staged.write_bytes(b'new')
            def race(source, destination):
                if source == staged:
                    target.write_bytes(b'external')
            with self.intercept_moves(race), self.assertRaises(FileExistsError):
                promote_path(staged, target)
            self.assertEqual(target.read_bytes(), b'external')
            self.assertEqual(staged.read_bytes(), b'new')

    def test_conflicting_rollback_retains_original_stage_and_external_file(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            staged, target = root / 'stage', root / 'app'
            staged.write_bytes(b'new')
            target.write_bytes(b'original')
            def race(source, destination):
                if source == staged:
                    target.write_bytes(b'external')
                    raise OSError('promotion failed')
            with self.intercept_moves(race), self.assertRaises(OSError) as caught:
                promote_path(staged, target)
            self.assertEqual(target.read_bytes(), b'external')
            self.assertEqual(staged.read_bytes(), b'new')
            backups = list(root.glob('app.previous-*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), b'original')
            self.assertIn(str(backups[0]), str(caught.exception))

    def test_backup_collision_does_not_replace_existing_recovery(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            staged, target = root / 'stage', root / 'app'
            staged.write_bytes(b'new')
            target.write_bytes(b'original')
            recovery = []
            def race(source, destination):
                if source == target:
                    destination.write_bytes(b'existing recovery')
                    recovery.append(destination)
            with self.intercept_moves(race), self.assertRaises(FileExistsError):
                promote_path(staged, target)
            self.assertEqual(target.read_bytes(), b'original')
            self.assertEqual(staged.read_bytes(), b'new')
            self.assertEqual(recovery[0].read_bytes(), b'existing recovery')

    def test_parent_alias_cannot_move_an_installation_inside_itself(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            staged = root / 'stage'
            staged.mkdir()
            (staged / 'original').write_bytes(b'keep')
            target = staged / '..' / 'stage' / 'child'
            with self.assertRaises(ValueError):
                promote_path(staged, target)
            self.assertEqual((staged / 'original').read_bytes(), b'keep')

    def test_second_validation_preserves_external_write_and_removes_staging(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'note'
            path.write_bytes(b'original')
            calls = []
            def validate():
                calls.append(True)
                if len(calls) == 2:
                    path.write_bytes(b'external')
                    raise ValueError('conflict')
            with self.assertRaises(ValueError):
                atomic_write_bytes(path, b'buffer', validate=validate)
            self.assertEqual(path.read_bytes(), b'external')
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_no_clobber_preserves_racing_destination(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'note'
            path.write_bytes(b'external')
            with self.assertRaises(FileExistsError):
                atomic_write_bytes(path, b'buffer', overwrite=False)
            self.assertEqual(path.read_bytes(), b'external')
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_invalid_json_and_size_limit_preserve_existing_state(self):
        from commonUtils.persistence import atomic_write_json
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            atomic_write_json(path, {'label': '😀'})
            original = path.read_bytes()
            for data, options in [({'value': float('nan')}, {}), ({'large': 'text'}, {'max_bytes': 2})]:
                with self.assertRaises(ValueError):
                    atomic_write_json(path, data, **options)
                self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(directory).iterdir()), [path])
