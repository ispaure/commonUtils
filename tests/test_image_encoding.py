"""Optional encoding preserves pixel/metadata rules and caller-owned allocation."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from PIL import Image
from commonUtils.formats.image_encoding import encode_image, image_is_color


class ImageEncodingTests(unittest.TestCase):
    def test_oriented_alpha_source_resizes_and_retains_transparency(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, destination = root / 'source.png', root / 'output.webp'
            exif = Image.Exif()
            exif[274] = 6
            Image.new('RGBA', (40, 80), (30, 80, 150, 90)).save(source, exif=exif)
            before = source.read_bytes()
            def allocate():
                destination.touch(exist_ok=False)
                return destination
            encode_image(source, allocate_output=allocate, extension='.webp', quality=60, max_long_edge=40)
            with Image.open(destination) as image:
                self.assertEqual(image.size, (40, 20))
                self.assertIn('A', image.getbands())
                self.assertNotEqual(image.getexif().get(274), 6)
            self.assertEqual(source.read_bytes(), before)

    def test_invalid_source_fails_before_allocating_output(self):
        allocations = []
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / 'broken.png'
            source.write_bytes(b'invalid')
            with self.assertRaises(OSError):
                encode_image(source, allocate_output=lambda: allocations.append(True), extension='.webp', quality=60)
        self.assertEqual(allocations, [])

    def test_uniform_tint_and_gray_choose_different_quality_classes(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'page.png'
            for color, expected in [((120, 120, 120), False), ((120, 80, 40), True)]:
                Image.new('RGB', (8, 8), color).save(path)
                self.assertEqual(image_is_color(path), expected)
