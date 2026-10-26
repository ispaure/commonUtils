"""Injected content factories retain provider policy and independent lifetime."""
import base64
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from commonUtils.runtime.resources.content import ProviderContent
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.mutations import save_resource_bytes
from commonUtils.runtime.operations import OperationCancelled


class ProviderContentTests(unittest.TestCase):
    def test_class_factory_decodes_without_a_filesystem_plaintext_copy(self):
        with TemporaryDirectory() as folder:
            path = Path(folder, 'document.txt')
            path.write_bytes(base64.b64encode(b'private fixture'))
            provider = LocalFiles(folder)
            instances = []
            class Decoder:
                def __init__(self, name, *, password, cancelled):
                    self.data = base64.b64decode(provider._locate(name).read_bytes())
                    self.closed = False
                    instances.append(self)
                @contextmanager
                def open(self, name):
                    with BytesIO(self.data) as stream:
                        yield stream
                def close(self):
                    self.closed = True
                    self.data = b''
            provider.content_source = Decoder
            content = ProviderContent(provider, 'document.txt')
            with content.open('document.txt') as stream:
                self.assertEqual(stream.read(), b'private fixture')
            self.assertEqual(list(Path(folder).iterdir()), [path])
            content.close()
            content.close()
            self.assertTrue(instances[0].closed)
            with self.assertRaisesRegex(ValueError, 'closed'):
                content.open('document.txt').__enter__()

    def test_version_cancel_and_wrong_document_are_checked_before_factory_content(self):
        with TemporaryDirectory() as folder:
            path = Path(folder, 'note.txt')
            path.write_bytes(b'original')
            cancelled = [False]
            content = ProviderContent(LocalFiles(folder), 'note.txt', cancelled=lambda: cancelled[0])
            self.addCleanup(content.close)
            with self.assertRaisesRegex(ValueError, 'different document'):
                content.version('other.txt')
            cancelled[0] = True
            with self.assertRaises(OperationCancelled):
                content.version('note.txt')
            cancelled[0] = False
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'changed'):
                content.version('note.txt')

    def test_verified_replacement_hook_is_capability_checked_and_receives_revision(self):
        with TemporaryDirectory() as folder:
            path = Path(folder, 'note.txt')
            path.write_bytes(b'original')
            provider = LocalFiles(folder)
            revision = provider.entry('note.txt')['revision']
            calls = []
            def replace(name, data, *, expected_revision, cancelled):
                self.assertEqual(provider.entry(name)['revision'], expected_revision)
                calls.append((name, data))
            provider.replace_bytes = replace
            save_resource_bytes(provider, 'note.txt', b'updated', expected_revision=revision)
            self.assertEqual(calls, [('note.txt', b'updated')])
            from commonUtils.runtime.resources.provider import ResourceCapabilities
            provider.capabilities = ResourceCapabilities()
            with self.assertRaises(PermissionError):
                save_resource_bytes(provider, 'note.txt', b'rejected', expected_revision=revision)
            self.assertEqual(len(calls), 1)
