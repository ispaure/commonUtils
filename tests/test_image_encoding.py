"""Optional encoding preserves pixel/metadata rules and caller-owned allocation."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock
from PIL import Image, ImageCms
from commonUtils.formats.image_encoding import encode_image, image_is_color, UnsupportedImageFormat


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


class ImageEncodingContracts(unittest.TestCase):
    def test_lazy_quality_precedes_exclusive_output_allocation(self):
        with TemporaryDirectory() as temporary:
            source, output = Path(temporary) / 'source.png', Path(temporary) / 'output.jpg'
            Image.new('RGB', (20, 30), 'red').save(source)
            original = source.read_bytes()
            events = []
            def quality():
                self.assertFalse(output.exists())
                self.assertEqual(source.read_bytes(), original)
                events.append('quality')
                return 70
            def allocate():
                self.assertEqual(events, ['quality'])
                events.append('allocate')
                output.touch(exist_ok=False)
                return output
            encode_image(source, allocate_output=allocate, extension='.jpg', quality=quality)
            self.assertEqual(events, ['quality', 'allocate'])
            self.assertEqual(source.read_bytes(), original)
            with Image.open(output) as image:
                self.assertEqual(image.size, (20, 30))

    def test_oriented_bounds_update_existing_exif_dimensions_without_upscaling(self):
        for long_edge, height, expected in [(20, 15, (20, 10)), (0, 15, (30, 15)),
                                             (400, 400, (80, 40))]:
            with self.subTest(long_edge=long_edge, height=height), TemporaryDirectory() as temporary:
                source, output = Path(temporary) / 'source.png', Path(temporary) / 'output.webp'
                exif = Image.Exif()
                exif[274] = 6
                exif[256], exif[257] = 40, 80
                exif[40962], exif[40963] = 40, 80
                exif[34665] = {40962: 40, 40963: 80}
                Image.new('RGB', (40, 80), 'blue').save(source, exif=exif)
                encode_image(source, allocate_output=lambda: output, extension='.webp', quality=60,
                             max_long_edge=long_edge, max_height=height)
                with Image.open(output) as image:
                    self.assertEqual(image.size, expected)
                    metadata = image.getexif()
                    self.assertEqual((metadata[256], metadata[257]), expected)
                    self.assertEqual((metadata[40962], metadata[40963]), expected)
                    nested = metadata.get_ifd(34665)
                    self.assertEqual((nested[40962], nested[40963]), expected)
                    self.assertNotIn(274, metadata)

    def test_unsupported_icc_space_fails_before_output_allocation(self):
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / 'source.tiff'
            profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('LAB')).tobytes()
            Image.new('LAB', (8, 8)).save(source, icc_profile=profile)
            allocate = Mock()
            with self.assertRaisesRegex(ValueError, 'Unsupported ICC color space: Lab'):
                encode_image(source, allocate_output=allocate, extension='.webp', quality=60)
            allocate.assert_not_called()

    def test_unsupported_encoder_leaves_allocated_stage_with_its_owner(self):
        with TemporaryDirectory() as temporary:
            source, output = Path(temporary) / 'source.png', Path(temporary) / 'output.png'
            Image.new('RGB', (8, 8), 'red').save(source)
            def allocate():
                output.touch(exist_ok=False)
                return output
            with self.assertRaises(UnsupportedImageFormat):
                encode_image(source, allocate_output=allocate, extension='.png', quality=60)
            self.assertEqual(output.read_bytes(), b'')

    def test_palette_transparency_follows_requested_webp_policy(self):
        with TemporaryDirectory() as temporary:
            source, output = Path(temporary) / 'source.png', Path(temporary) / 'output.webp'
            palette = Image.new('P', (8, 8), 0)
            palette.putpalette([255, 0, 0] + [0] * 765)
            palette.save(source, transparency=0)
            for preserve in (True, False):
                encode_image(source, allocate_output=lambda: output, extension='.webp',
                             quality=60, preserve_alpha=preserve)
                with Image.open(output) as image:
                    self.assertEqual('A' in image.getbands(), preserve)
                    if preserve:
                        self.assertEqual(image.getchannel('A').getextrema(), (0, 0))
