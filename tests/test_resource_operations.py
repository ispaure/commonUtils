import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.mutations import move_resource, delete_resource, inventory


class ResourceOperationsTests(unittest.TestCase):
    def test_nonblocking_source_does_not_create_a_truncated_local_resource(self):
        from io import BytesIO
        class WouldBlock(BytesIO):
            def read(self, limit=-1):
                if self.tell():
                    return None
                return super().read(1)
        with TemporaryDirectory() as directory:
            provider = LocalFiles(directory)
            with self.assertRaises(BlockingIOError):
                provider.create_file('copy', WouldBlock(b'complete'))
            self.assertEqual(list(provider.root.iterdir()), [])

    def test_verification_cannot_treat_would_block_as_empty_content(self):
        from contextlib import contextmanager
        from commonUtils.runtime.resources.mutations import save_resource_bytes
        class WouldBlock:
            def read(self, limit):
                return None
        with TemporaryDirectory() as directory:
            provider = LocalFiles(directory)
            @contextmanager
            def unavailable(path):
                # Storage corruption plus a nonblocking verifier must not look
                # like a verified empty save or publish the corrupted stage.
                (provider.root / path).write_bytes(b'corrupted')
                yield WouldBlock()
            with patch.object(provider, 'open', side_effect=unavailable):
                with self.assertRaises(BlockingIOError):
                    save_resource_bytes(provider, 'copy', b'')
            self.assertEqual(list(provider.root.iterdir()), [])

    def test_recursive_move_collisions_and_self_moves(self):
        with TemporaryDirectory() as directory:
            a, b = Path(directory) / 'a', Path(directory) / 'b'
            a.mkdir(); b.mkdir()
            source, destination = LocalFiles(a), LocalFiles(b)
            source.mkdir('folder'); source.mkdir('folder/empty')
            (a / 'folder/note').write_bytes(b'private bytes')
            with self.assertRaises(ValueError):
                move_resource(source, 'folder', source, 'folder/child')
            move_resource(source, 'folder', destination, 'moved')
            self.assertFalse((a / 'folder').exists())
            self.assertEqual((b / 'moved/note').read_bytes(), b'private bytes')
            self.assertTrue((b / 'moved/empty').is_dir())
            destination.mkdir('occupied')
            with self.assertRaises(FileExistsError):
                destination.rename('moved', 'occupied')
            delete_resource(destination, 'moved')
            self.assertEqual([r['name'] for r in destination.list()], ['occupied'])

    def test_verification_failure_conflict_and_cancellation_preserve_source(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a').mkdir(); (root / 'b').mkdir()
            a, b = LocalFiles(root / 'a'), LocalFiles(root / 'b')
            (a.root / 'note').write_bytes(b'original')
            original_create = b.create_file
            def corrupt(path, stream, **kwargs):
                original_create(path, stream, **kwargs)
                (b.root / path).write_bytes(b'bad')
            with patch.object(b, 'create_file', side_effect=corrupt):
                with self.assertRaisesRegex(ValueError, 'verification'):
                    move_resource(a, 'note', b, 'copy')
            self.assertFalse(list(b.root.iterdir()))
            self.assertEqual((a.root / 'note').read_bytes(), b'original')
            (b.root / 'copy').write_bytes(b'existing')
            with self.assertRaises(FileExistsError):
                move_resource(a, 'note', b, 'copy')
            self.assertEqual((b.root / 'copy').read_bytes(), b'existing')
            with self.assertRaises(Exception):
                move_resource(a, 'note', b, 'new', cancelled=lambda: True)
            self.assertTrue((a.root / 'note').exists())
            before = inventory(a, 'note')
            (a.root / 'note').write_bytes(b'changed')
            with self.assertRaises(ValueError):
                delete_resource(a, 'note', expected=before)

    def test_roots_links_and_traversal_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); source = LocalFiles(root)
            for path in ('../outside', '/outside', 'a//b', 'a/./b', 'C:escape'):
                with self.assertRaises(ValueError): source.mkdir(path)
            with self.assertRaises(ValueError): delete_resource(source, '')
            (root / 'linked').symlink_to(root, target_is_directory=True)
            with self.assertRaises(ValueError): inventory(source, 'linked')

    def test_save_as_is_verified_no_clobber_and_view_aliases_rejected(self):
        from commonUtils.runtime.resources.mutations import save_resource_bytes
        with TemporaryDirectory() as directory:
            provider = LocalFiles(directory)
            save_resource_bytes(provider, 'first.txt', b'first')
            with self.assertRaises(FileExistsError):
                save_resource_bytes(provider, 'first.txt', b'overwrite')
            self.assertEqual((provider.root / 'first.txt').read_bytes(), b'first')
            before = provider.entry('first.txt')['revision']
            save_resource_bytes(provider, 'first.txt', b'changed', expected_revision=before)
            with self.assertRaises(ValueError):
                save_resource_bytes(provider, 'first.txt', b'stale', expected_revision=before)
            alias = LocalFiles(directory)
            alias.storage_namespace = 'other-view'
            with self.assertRaisesRegex(ValueError, 'provider views'):
                move_resource(provider, 'first.txt', alias, 'other.txt')
            self.assertEqual([p.name for p in provider.root.iterdir()], ['first.txt'])

    def test_save_transaction_failure_and_cancellation_never_publish(self):
        from commonUtils.persistence.publication import save_transaction
        for failure in ('stage', 'verify', 'revalidate', 'cancel', None):
            events = []
            def validate():
                events.append('validate')
                if failure == 'revalidate' and events.count('validate') == 2:
                    raise ValueError('stale')
            def stage():
                events.append('stage')
                if failure == 'stage': raise ValueError('write failed')
            def verify():
                events.append('verify')
                if failure == 'verify': raise ValueError('corrupt')
                return 'document'
            def run():
                return save_transaction(stage=stage, verify=verify, validate=validate,
                    publish=lambda: events.append('publish'), cleanup=lambda: events.append('cleanup'),
                    cancelled=lambda: failure == 'cancel' and 'verify' in events)
            if failure:
                with self.assertRaises(Exception): run()
                self.assertNotIn('publish', events)
            else:
                self.assertEqual(run(), 'document')
                self.assertIn('publish', events)
            self.assertEqual(events[-1], 'cleanup')

    def test_read_only_capabilities_prevent_mutations(self):
        from commonUtils.runtime.resources.provider import ResourceCapabilities
        from commonUtils.runtime.resources.mutations import save_resource_bytes
        with TemporaryDirectory() as directory:
            provider = LocalFiles(directory)
            (provider.root / 'note').write_bytes(b'original')
            provider.capabilities = ResourceCapabilities()
            for operation in (lambda: save_resource_bytes(provider, 'copy', b'new'),
                              lambda: delete_resource(provider, 'note'),
                              lambda: move_resource(provider, 'note', provider, 'renamed')):
                with self.assertRaises(PermissionError): operation()
            self.assertEqual((provider.root / 'note').read_bytes(), b'original')
            self.assertEqual(len(list(provider.root.iterdir())), 1)

    def test_move_reports_published_destination_and_partial_source_cleanup(self):
        from commonUtils.runtime.operations import MutationIncomplete
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a').mkdir(); (root / 'b').mkdir()
            source, target = LocalFiles(root / 'a'), LocalFiles(root / 'b')
            source.mkdir('folder')
            (source.root / 'folder/one').write_bytes(b'one')
            (source.root / 'folder/two').write_bytes(b'two')
            remove = source.remove_empty
            calls = []
            def interrupted(path, revision):
                if calls: raise OSError('injected cleanup failure')
                remove(path, revision)
                calls.append(path)
            with patch.object(source, 'remove_empty', side_effect=interrupted):
                with self.assertRaises(MutationIncomplete) as caught:
                    move_resource(source, 'folder', target, 'saved')
            result = caught.exception.result
            self.assertTrue(result.destination_published)
            self.assertEqual(result.source_state, 'partial')
            self.assertEqual(result.removed_paths, tuple(calls))
            self.assertEqual((target.root / 'saved/one').read_bytes(), b'one')
            self.assertEqual((target.root / 'saved/two').read_bytes(), b'two')

    def test_saved_destination_is_reported_when_cleanup_fails(self):
        from commonUtils.persistence.publication import save_transaction
        from commonUtils.runtime.operations import MutationIncomplete
        events = []
        def cleanup(): raise OSError('cleanup')
        with self.assertRaises(MutationIncomplete) as caught:
            save_transaction(stage=lambda: None, verify=lambda: None, validate=lambda: None,
                             publish=lambda: events.append('published'), cleanup=cleanup)
        self.assertTrue(caught.exception.result.destination_published)
        self.assertEqual(events, ['published'])

    def test_no_late_cancellation_after_successful_publication(self):
        from commonUtils.persistence.publication import save_transaction
        published = []
        result = save_transaction(stage=lambda: None, verify=lambda: 'saved', validate=lambda: None,
            publish=lambda: published.append(True), cleanup=lambda: None, cancelled=lambda: bool(published))
        self.assertEqual(result, 'saved')

    def test_move_reports_retained_source_after_publication(self):
        from commonUtils.runtime.operations import MutationIncomplete
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a').mkdir(); (root / 'b').mkdir()
            source, target = LocalFiles(root / 'a'), LocalFiles(root / 'b')
            (source.root / 'note').write_bytes(b'original')
            with patch.object(source, 'remove_empty', side_effect=PermissionError('denied')):
                with self.assertRaises(MutationIncomplete) as caught:
                    move_resource(source, 'note', target, 'saved')
            self.assertTrue(caught.exception.result.destination_published)
            self.assertEqual(caught.exception.result.source_state, 'unchanged')
            self.assertEqual((source.root / 'note').read_bytes(), (target.root / 'saved').read_bytes())

    def test_folder_and_rename_entrypoints_check_capability_and_cancellation(self):
        from commonUtils.runtime.resources.mutations import create_resource_folder, rename_resource
        from commonUtils.runtime.resources.provider import ResourceCapabilities
        from commonUtils.runtime.operations import OperationCancelled
        with TemporaryDirectory() as directory:
            provider = LocalFiles(directory)
            provider.capabilities = ResourceCapabilities()
            with self.assertRaises(PermissionError): create_resource_folder(provider, 'folder')
            provider.capabilities = LocalFiles.capabilities
            with self.assertRaises(OperationCancelled): create_resource_folder(provider, 'folder', cancelled=lambda: True)
            create_resource_folder(provider, 'folder')
            with self.assertRaises(OperationCancelled): rename_resource(provider, 'folder', 'renamed', cancelled=lambda: True)
            self.assertTrue((provider.root / 'folder').is_dir())
