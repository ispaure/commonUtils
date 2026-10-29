
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import piexif
from commonUtils.integrations.wrappers.piexifWrapper import jpg_set_exif_comments, COMMENTS_TAG_ADDRESS


class JpegCommentTests(unittest.TestCase):
    def test_unicode_comments_and_recovery_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'photo.jpg'
            Image.new('RGB', (8, 8)).save(path)
            original = path.read_bytes()
            self.assertTrue(jpg_set_exif_comments(path, 'Café 航空'))
            raw = bytes(piexif.load(str(path))['0th'][COMMENTS_TAG_ADDRESS])
            self.assertEqual(raw.decode('utf-16-le').rstrip('\0'), 'Café 航空')
            self.assertEqual(path.with_name('photo.jpg.before-comments').read_bytes(), original)
            self.assertFalse(jpg_set_exif_comments(path, 'Café 航空'))

    def test_failed_metadata_conversion_preserves_original(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'photo.jpg'
            Image.new('RGB', (8, 8)).save(path)
            original = path.read_bytes()
            with patch('commonUtils.integrations.wrappers.piexifWrapper.piexif.insert', side_effect=OSError('failed')):
                with self.assertRaises(OSError):
                    jpg_set_exif_comments(path, 'new')
            self.assertEqual(path.read_bytes(), original)
