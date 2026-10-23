"""Real local Git/archive transactions, private-file preservation and restart handoff."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from commonUtils.runtime.updates import transaction as updates


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.protected = ('.git', '.env', '.venv', 'Software', 'Credentials')

    def command(self, root, *args):
        return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.STDOUT).decode().strip()

    def repository(self):
        remote = self.root / 'source'
        remote.mkdir()
        self.command(remote, 'init', '-b', 'main')
        self.command(remote, 'config', 'user.name', 'Fixture')
        self.command(remote, 'config', 'user.email', 'fixture@example.invalid')
        (remote / '.gitignore').write_text('Software/\nCredentials/\n.env\n.venv/\n')
        (remote / 'app.py').write_text('old')
        self.command(remote, 'add', '.')
        self.command(remote, 'commit', '-m', 'old')
        checkout = self.root / 'checkout'
        subprocess.check_call(['git', 'clone', str(remote), str(checkout)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        before = updates.head(checkout)
        (remote / 'app.py').write_text('new')
        self.command(remote, 'commit', '-am', 'new')
        return remote, checkout, before, updates.head(remote)

    def private_files(self, checkout):
        values = {'Software/app/data': b'private software', 'Credentials/rclone/account.zip': b'secret',
                  '.env': b'private environment', '.venv/data': b'venv', 'personal.txt': b'untracked'}
        for name, data in values.items():
            path = checkout / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return values

    def test_git_update_preserves_ignored_and_untracked_files_and_local_branch(self):
        remote, checkout, before, target = self.repository()
        private = self.private_files(checkout)
        plan = updates.prepare_git(checkout, target, self.protected, str(remote))
        self.assertEqual((checkout / 'app.py').read_text(), 'old')
        updates.apply_git(plan)
        self.assertEqual(updates.head(checkout), target)
        self.assertEqual((checkout / 'app.py').read_text(), 'new')
        self.assertEqual(self.command(checkout, 'rev-parse', 'main'), before)
        for name, data in private.items():
            self.assertEqual((checkout / name).read_bytes(), data)

    def test_dirty_checkout_and_untracked_collision_are_rejected(self):
        remote, checkout, before, target = self.repository()
        (checkout / 'app.py').write_text('local edits')
        with self.assertRaisesRegex(ValueError, 'Uncommitted'):
            updates.prepare_git(checkout, target, self.protected, str(remote))
        (checkout / 'app.py').write_text('old')
        (checkout / 'new.py').write_text('local file')
        (remote / 'new.py').write_text('remote file')
        self.command(remote, 'add', 'new.py'); self.command(remote, 'commit', '-m', 'collision')
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            updates.prepare_git(checkout, updates.head(remote), self.protected, str(remote))
        self.assertEqual(updates.head(checkout), before)
        self.assertEqual((checkout / 'new.py').read_text(), 'local file')

    def test_remote_cannot_replace_protected_ignored_resources(self):
        remote, checkout, before, target = self.repository()
        self.private_files(checkout)
        (remote / '.env').write_text('remote environment')
        self.command(remote, 'add', '-f', '.env'); self.command(remote, 'commit', '-m', 'bad update')
        with self.assertRaises(ValueError):
            updates.prepare_git(checkout, updates.head(remote), self.protected, str(remote))
        self.assertEqual((checkout / '.env').read_bytes(), b'private environment')
        self.assertEqual(updates.head(checkout), before)

    def test_changes_after_prepare_prevent_application(self):
        remote, checkout, before, target = self.repository()
        plan = updates.prepare_git(checkout, target, self.protected, str(remote))
        (checkout / 'app.py').write_text('edited during download')
        with self.assertRaises(ValueError):
            updates.apply_git(plan)
        self.assertEqual(updates.head(checkout), before)

    def test_update_cannot_delete_previously_tracked_private_file(self):
        remote, checkout, before, target = self.repository()
        (remote / '.env').write_text('legacy private configuration')
        self.command(remote, 'add', '-f', '.env')
        self.command(remote, 'commit', '-m', 'legacy private file')
        self.command(checkout, 'fetch', 'origin')
        self.command(checkout, 'checkout', '--detach', updates.head(remote))
        self.command(remote, 'rm', '.env')
        self.command(remote, 'commit', '-m', 'delete legacy private file')
        with self.assertRaises(ValueError):
            updates.prepare_git(checkout, updates.head(remote), self.protected, str(remote))
        self.assertEqual((checkout / '.env').read_text(), 'legacy private configuration')

    def submodule_repository(self):
        remote, checkout, before, target = self.repository()
        child_source = self.root / 'dependency'
        child_source.mkdir()
        self.command(child_source, 'init', '-b', 'main')
        self.command(child_source, 'config', 'user.name', 'Fixture')
        self.command(child_source, 'config', 'user.email', 'fixture@example.invalid')
        (child_source / 'code.py').write_text('dependency old')
        (child_source / '.gitignore').write_text('.env\n')
        self.command(child_source, 'add', '.')
        self.command(child_source, 'commit', '-m', 'dep old')
        old_child = updates.head(child_source)
        self.command(remote, '-c', 'protocol.file.allow=always', 'submodule', 'add', str(child_source), 'vendor')
        self.command(remote, 'commit', '-am', 'add dependency')
        old_root = updates.head(remote)
        self.command(checkout, 'fetch', 'origin')
        self.command(checkout, 'checkout', '--detach', old_root)
        self.command(checkout, '-c', 'protocol.file.allow=always', 'submodule', 'update', '--init')
        (child_source / 'code.py').write_text('dependency new')
        self.command(child_source, 'commit', '-am', 'dep new')
        new_child = updates.head(child_source)
        self.command(remote / 'vendor', 'fetch', 'origin')
        self.command(remote / 'vendor', 'checkout', '--detach', new_child)
        self.command(remote, 'commit', '-am', 'new dependency pin')
        return remote, checkout, old_root, old_child, updates.head(remote), new_child

    def test_pinned_submodule_updates_preserve_private_dependency_files(self):
        remote, checkout, old_root, old_child, target, child_target = self.submodule_repository()
        (checkout / 'vendor/.env').write_text('private dependency configuration')
        plan = updates.prepare_git(checkout, target, self.protected, str(remote))
        updates.apply_git(plan)
        self.assertEqual(updates.head(checkout), target)
        self.assertEqual(updates.head(checkout / 'vendor'), child_target)
        self.assertEqual((checkout / 'vendor/.env').read_text(), 'private dependency configuration')

    def test_submodule_failure_rolls_back_parent_revision(self):
        remote, checkout, old_root, old_child, target, child_target = self.submodule_repository()
        plan = updates.prepare_git(checkout, target, self.protected, str(remote))
        original = updates.git
        def fail(root, *args, **kwargs):
            if root == checkout.resolve() / 'vendor' and args[-1] == child_target and args[0] == 'checkout':
                raise OSError('simulated dependency checkout failure')
            return original(root, *args, **kwargs)
        with patch.object(updates, 'git', side_effect=fail):
            with self.assertRaisesRegex(OSError, 'dependency checkout'):
                updates.apply_git(plan)
        self.assertEqual(updates.head(checkout), old_root)
        self.assertEqual(updates.head(checkout / 'vendor'), old_child)

    def archive(self):
        installed = self.root / 'installed'; installed.mkdir()
        snapshot = self.root / 'snapshot'; snapshot.mkdir()
        workspace = self.root / 'work'; workspace.mkdir()
        (installed / 'app.py').write_text('old')
        (installed / 'obsolete.py').write_text('obsolete')
        (installed / updates.MARKER).write_text(json.dumps({'format': 1, 'revision': 'old', 'files':
            {name: updates.digest(installed / name) for name in ('app.py', 'obsolete.py')}}))
        (snapshot / 'app.py').write_text('new')
        (snapshot / 'nested').mkdir()
        (snapshot / 'nested/new.py').write_text('new nested')
        return installed, snapshot, workspace

    def test_archive_update_preserves_private_files_and_removes_only_managed_obsolete_files(self):
        installed, snapshot, workspace = self.archive()
        private = self.private_files(installed)
        plan = updates.prepare_archive(installed, snapshot, 'new', self.protected)
        updates.apply_archive(plan, workspace)
        self.assertEqual((installed / 'app.py').read_text(), 'new')
        self.assertFalse((installed / 'obsolete.py').exists())
        for name, data in private.items(): self.assertEqual((installed / name).read_bytes(), data)
        self.assertEqual(json.loads((installed / updates.MARKER).read_text())['revision'], 'new')

    def test_archive_publication_failure_restores_previous_files_and_manifest(self):
        installed, snapshot, workspace = self.archive()
        marker = (installed / updates.MARKER).read_bytes()
        plan = updates.prepare_archive(installed, snapshot, 'new', self.protected)
        original = shutil.copy2
        def copy(source, destination, *args, **kwargs):
            if '.new.py.update-' in str(destination):
                raise OSError('simulated disk failure')
            return original(source, destination, *args, **kwargs)
        with patch.object(updates.shutil, 'copy2', side_effect=copy):
            with self.assertRaisesRegex(OSError, 'disk failure'):
                updates.apply_archive(plan, workspace)
        self.assertEqual((installed / 'app.py').read_text(), 'old')
        self.assertEqual((installed / 'obsolete.py').read_text(), 'obsolete')
        self.assertEqual((installed / updates.MARKER).read_bytes(), marker)

    def test_archive_rejects_local_edits_and_symlink_destinations(self):
        installed, snapshot, workspace = self.archive()
        (installed / 'app.py').write_text('artist edits')
        with self.assertRaisesRegex(ValueError, 'Locally modified'):
            updates.prepare_archive(installed, snapshot, 'new', self.protected)
        (installed / 'app.py').unlink()
        outside = self.root / 'outside'; outside.write_text('private')
        (installed / 'app.py').symlink_to(outside)
        with self.assertRaises(ValueError):
            updates.prepare_archive(installed, snapshot, 'new', self.protected)
        self.assertEqual(outside.read_text(), 'private')

    def test_archive_rejects_corrupt_recovery_copies_before_changing_the_file(self):
        base = self.root
        for name in (updates.MARKER, 'app.py', 'obsolete.py'):
            with self.subTest(name=name):
                self.root = base / name
                self.root.mkdir()
                installed, snapshot, workspace = self.archive()
                before = {path.name: path.read_bytes() for path in installed.iterdir()}
                plan = updates.prepare_archive(installed, snapshot, 'new', self.protected)
                original = shutil.copy2

                def corrupt(source, destination, *args, **kwargs):
                    result = original(source, destination, *args, **kwargs)
                    if Path(destination) == workspace / 'rollback' / name:
                        Path(destination).write_bytes(b'corrupted recovery copy')
                    return result

                with patch.object(updates.shutil, 'copy2', side_effect=corrupt):
                    with self.assertRaisesRegex(ValueError, 'Recovery copy'):
                        updates.apply_archive(plan, workspace)
                self.assertEqual({path.name: path.read_bytes() for path in installed.iterdir()
                                  if path.is_file()}, before)

    def test_archive_preserves_edits_made_while_copying_recovery_or_payload(self):
        base = self.root
        for phase in ('recovery', 'payload'):
            with self.subTest(phase=phase):
                self.root = base / phase
                self.root.mkdir()
                installed, snapshot, workspace = self.archive()
                marker = (installed / updates.MARKER).read_bytes()
                plan = updates.prepare_archive(installed, snapshot, 'new', self.protected)
                original = shutil.copy2

                def edit(source, destination, *args, **kwargs):
                    result = original(source, destination, *args, **kwargs)
                    if (phase == 'recovery' and Path(destination) == workspace / 'rollback/app.py'
                            or phase == 'payload' and Path(source).resolve() == snapshot.resolve() / 'app.py'):
                        (installed / 'app.py').write_text('newer local edits')
                    return result

                with patch.object(updates.shutil, 'copy2', side_effect=edit):
                    with self.assertRaisesRegex(ValueError, 'Local file changed'):
                        updates.apply_archive(plan, workspace)
                self.assertEqual((installed / 'app.py').read_text(), 'newer local edits')
                self.assertEqual((installed / 'obsolete.py').read_text(), 'obsolete')
                self.assertEqual((installed / updates.MARKER).read_bytes(), marker)

    def test_archive_preserves_new_unmanaged_file_created_during_payload_copy(self):
        installed, snapshot, workspace = self.archive()
        plan = updates.prepare_archive(installed, snapshot, 'new', self.protected)
        original = shutil.copy2
        target = installed / 'nested/new.py'

        def create(source, destination, *args, **kwargs):
            result = original(source, destination, *args, **kwargs)
            if Path(source).resolve() == snapshot.resolve() / 'nested/new.py':
                target.write_text('new unmanaged file')
            return result

        with patch.object(updates.shutil, 'copy2', side_effect=create):
            with self.assertRaisesRegex(ValueError, 'Local file changed'):
                updates.apply_archive(plan, workspace)
        self.assertEqual(target.read_text(), 'new unmanaged file')
        self.assertEqual((installed / 'app.py').read_text(), 'old')

    def test_archive_does_not_advertise_new_manifest_before_file_publication(self):
        installed, snapshot, workspace = self.archive()
        marker = (installed / updates.MARKER).read_bytes()
        plan = updates.prepare_archive(installed, snapshot, 'new', self.protected)
        original = shutil.copy2
        observed = []

        def copy(source, destination, *args, **kwargs):
            if Path(source).resolve().is_relative_to(snapshot.resolve()):
                observed.append((installed / updates.MARKER).read_bytes())
            return original(source, destination, *args, **kwargs)

        with patch.object(updates.shutil, 'copy2', side_effect=copy):
            updates.apply_archive(plan, workspace)
        self.assertEqual(observed, [marker, marker])
        self.assertEqual(json.loads((installed / updates.MARKER).read_bytes())['revision'], 'new')

    def test_archive_failed_recovery_copy_preserves_installed_bytes_and_reports_rollback_failure(self):
        base = self.root
        for failure in ('corrupt', 'partial'):
            with self.subTest(failure=failure):
                self.root = base / failure
                self.root.mkdir()
                installed, snapshot, workspace = self.archive()
                plan = updates.prepare_archive(installed, snapshot, 'new', self.protected)
                original = shutil.copy2

                def fail(source, destination, *args, **kwargs):
                    if Path(source).resolve() == snapshot.resolve() / 'nested/new.py':
                        raise OSError('payload failure')
                    if Path(source) == workspace / 'rollback/app.py':
                        Path(destination).write_bytes(b'bad recovery output')
                        if failure == 'partial':
                            raise OSError('recovery copy interrupted')
                        return destination
                    return original(source, destination, *args, **kwargs)

                with patch.object(updates.shutil, 'copy2', side_effect=fail):
                    with self.assertRaises(updates.RollbackError):
                        updates.apply_archive(plan, workspace)
                self.assertEqual((installed / 'app.py').read_text(), 'new')
                self.assertEqual((workspace / 'rollback/app.py').read_text(), 'old')
                self.assertEqual((installed / 'obsolete.py').read_text(), 'obsolete')
                self.assertFalse(list(installed.glob('.*.update-*')))

    def test_archive_rollback_preserves_external_changes_to_already_published_paths(self):
        base = self.root
        for name in ('app.py', 'nested/new.py', 'obsolete.py'):
            with self.subTest(name=name):
                self.root = base / name.replace('/', '-')
                self.root.mkdir()
                installed, snapshot, workspace = self.archive()
                plan = updates.prepare_archive(installed, snapshot, 'new', self.protected)
                original = shutil.copy2
                target = installed / name

                def edit(source, destination, *args, **kwargs):
                    if Path(destination) == workspace / 'rollback' / updates.MARKER:
                        target.write_text('external change after publication')
                        raise OSError('later update failure')
                    return original(source, destination, *args, **kwargs)

                with patch.object(updates.shutil, 'copy2', side_effect=edit):
                    with self.assertRaises(updates.RollbackError):
                        updates.apply_archive(plan, workspace)
                self.assertEqual(target.read_text(), 'external change after publication')
                self.assertEqual((workspace / 'rollback/app.py').read_text(), 'old')

    def test_archive_failed_atomic_replace_does_not_restore_an_untouched_path(self):
        installed, snapshot, workspace = self.archive()
        plan = updates.prepare_archive(installed, snapshot, 'new', self.protected)
        original = Path.replace

        def fail(path, target):
            if Path(target) == installed.resolve() / 'app.py':
                Path(target).write_text('external edit before failed replace')
                raise OSError('replace denied')
            return original(path, target)

        with patch.object(Path, 'replace', new=fail):
            with self.assertRaisesRegex(OSError, 'replace denied'):
                updates.apply_archive(plan, workspace)
        self.assertEqual((installed / 'app.py').read_text(), 'external edit before failed replace')

    def test_helper_does_not_restart_after_incomplete_rollback(self):
        workspace = self.root / 'failed-runner'; workspace.mkdir()
        status = workspace / 'status.json'
        request = workspace / 'request.json'
        request.write_text(json.dumps({'pid': 123, 'plan': {'kind': 'git', 'root': str(self.root)},
                                       'status': str(status), 'restart': ['unused']}))
        with patch.object(updates, 'pid_alive', return_value=False), \
                patch.object(updates, 'apply_git', side_effect=updates.RollbackError('recovery failed')), \
                patch.object(updates.subprocess, 'Popen') as restart:
            self.assertEqual(updates.run_request(request), 1)
        restart.assert_not_called()
        self.assertFalse(json.loads(status.read_text())['success'])
        self.assertEqual(json.loads(status.read_text())['recovery'], str(workspace))

    def test_helper_waits_for_parent_exit_then_updates_and_restarts(self):
        remote, checkout, before, target = self.repository()
        plan = updates.prepare_git(checkout, target, self.protected, str(remote))
        workspace = self.root / 'runner'; workspace.mkdir()
        shutil.copy2(updates.__file__, workspace / 'runner.py')
        parent = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(.5)'])
        self.addCleanup(lambda: parent.wait(timeout=5))
        receipt = self.root / 'restarted'
        request = workspace / 'request.json'
        request.write_text(json.dumps({'pid': parent.pid, 'plan': plan, 'status': str(workspace / 'status.json'),
            'restart': [sys.executable, '-c', f'from pathlib import Path; Path({str(receipt)!r}).write_text("restarted")']}))
        runner = subprocess.Popen([sys.executable, str(workspace / 'runner.py'), str(request)])
        self.addCleanup(lambda: runner.wait(timeout=5))
        time.sleep(.1)
        self.assertEqual((checkout / 'app.py').read_text(), 'old')
        parent.wait(timeout=5)  # Reap the exited parent, as a real launcher does.
        self.assertEqual(runner.wait(timeout=5), 0)
        for _ in range(50):
            if receipt.exists(): break
            time.sleep(.02)
        self.assertEqual(receipt.read_text(), 'restarted')
        self.assertEqual(updates.head(checkout), target)


class ReleaseSourceTests(unittest.TestCase):
    def release(self, tag, *, draft=False, prerelease=False, digest='a' * 64):
        return {'tag_name': tag, 'draft': draft, 'prerelease': prerelease,
                'published_at': '2026-10-12T12:00:00Z', 'assets': [{'name': 'release.zip', 'state': 'uploaded',
                'digest': 'sha256:' + digest, 'browser_download_url':
                f'https://github.com/owner/repo/releases/download/{tag}/release.zip'}]}

    def test_release_channels_are_explicit_and_skip_drafts_or_unverified_assets(self):
        from commonUtils.runtime.updates.github import GitHubSource
        releases = [self.release('v2.0.0-alpha.2', prerelease=True), self.release('v1.0.0'),
                    self.release('v2.0.0', draft=True), self.release('v1.2.0', digest='invalid'),
                    self.release('v1.1.0-beta.3', prerelease=True), self.release('v9.0.0-unknown')]
        for channel, expected in [('main', 'v1.0.0'), ('beta', 'v1.1.0-beta.3'), ('alpha', 'v2.0.0-alpha.2')]:
            with patch('commonUtils.runtime.updates.github.json_get', side_effect=[releases, {'sha': 'b' * 40}]):
                result = GitHubSource('owner/repo').latest_release(channel)
            self.assertEqual(result['tag'], expected)
            self.assertEqual(result['commit'], 'b' * 40)
        with patch('commonUtils.runtime.updates.github.json_get', return_value=[]):
            self.assertIsNone(GitHubSource('owner/repo').latest_release('main'))

    def test_numbered_main_releases_sort_numerically_and_keep_legacy_tags(self):
        from commonUtils.runtime.updates.github import GitHubSource, release_channel, release_version
        self.assertEqual(release_channel('v0.1.0-main.01'), 'main')
        self.assertEqual(release_channel('v0.1.0'), 'main')
        self.assertGreater(release_version('v0.1.0-main.10'), release_version('v0.1.0-main.02'))
        releases = [self.release(tag) for tag in ('v0.1.0-main.02', 'v0.1.0', 'v0.1.0-main.10')]
        releases.append(self.release('v0.1.0-main.99', prerelease=True))
        with patch('commonUtils.runtime.updates.github.json_get', side_effect=[releases, {'sha': 'b' * 40}]):
            self.assertEqual(GitHubSource('owner/repo').latest_release('main')['tag'], 'v0.1.0-main.10')

    def test_release_manifest_and_asset_digest_must_both_match(self):
        import hashlib
        import io
        import zipfile
        from commonUtils.runtime.updates.github import GitHubSource
        from contextlib import nullcontext
        data = b'tested source'
        commit = 'b' * 40
        manifest = {'format': 1, 'revision': commit, 'files': {'app.py': hashlib.sha256(data).hexdigest()}}
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, 'w') as archive:
            archive.writestr('App/app.py', data)
            archive.writestr('App/' + updates.MARKER, json.dumps(manifest))
        payload = archive_bytes.getvalue()
        release = {'url': 'https://github.com/owner/repo/releases/download/v1.0.0/release.zip',
                   'sha256': hashlib.sha256(payload).hexdigest(), 'commit': commit}
        with TemporaryDirectory() as temp, patch('commonUtils.runtime.updates.github.urlopen', return_value=nullcontext(io.BytesIO(payload))):
            snapshot = GitHubSource('owner/repo').release_snapshot(release, Path(temp))
            self.assertEqual((snapshot / 'app.py').read_bytes(), data)
            self.assertFalse((snapshot / updates.MARKER).exists())
        with TemporaryDirectory() as temp, patch('commonUtils.runtime.updates.github.urlopen', return_value=nullcontext(io.BytesIO(payload))):
            with self.assertRaisesRegex(ValueError, 'checksum'):
                GitHubSource('owner/repo').release_snapshot({**release, 'sha256': '0' * 64}, Path(temp))


if __name__ == '__main__':
    unittest.main()
