"""Automatic local-image fallback respects provider privacy before any I/O."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import base64
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.filesystem.image_previews import local_native_image, local_provider_image
from commonUtils.runtime.resources.local import LocalFiles


class ImagePreviewEligibilityTests(unittest.TestCase):
    def test_public_local_image_keeps_bounded_native_fallback(self):
        data = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
        with TemporaryDirectory() as temporary:
            provider = LocalFiles(temporary)
            (Path(temporary) / 'image.gif').write_bytes(data)
            with patch('commonUtils.filesystem.network.is_network_location', return_value=False):
                self.assertTrue(local_provider_image(provider, 'image.gif'))
                self.assertEqual(local_native_image(provider, 'image.gif'), data)

    def test_private_local_subclass_never_resolves_or_reads_automatic_preview(self):
        class PrivateFiles(LocalFiles):
            private = True
        with TemporaryDirectory() as temporary:
            provider = PrivateFiles(temporary)
            with patch.object(provider, 'relative', side_effect=AssertionError('Resolved private path')), \
                    patch.object(provider, 'entry', side_effect=AssertionError('Read private metadata')), \
                    patch.object(provider, 'open', side_effect=AssertionError('Read private content')), \
                    patch('commonUtils.filesystem.network.is_network_location',
                          side_effect=AssertionError('Probed private filesystem')):
                self.assertFalse(local_provider_image(provider, 'image.png'))
                self.assertEqual(local_native_image(provider, 'image.png'), b'')

    def test_instance_private_flag_also_excludes_ordinary_local_provider(self):
        with TemporaryDirectory() as temporary:
            provider = LocalFiles(temporary)
            provider.private = True
            with patch.object(provider, 'relative', side_effect=AssertionError('Resolved private path')):
                self.assertFalse(local_provider_image(provider, 'image.png'))
                self.assertEqual(local_native_image(provider, 'image.png'), b'')
