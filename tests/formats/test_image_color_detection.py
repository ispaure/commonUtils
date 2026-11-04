"""Color classification across modes, chroma tolerances and downsampling."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image
from commonUtils.formats.image_encoding import image_is_color


class ImageColorDetectionTests(unittest.TestCase):
    def setUp(self):
        self.workspace = TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)

    def assert_color(self, image, expected_color):
        source = self.root / 'source.png'
        image.save(source)
        self.assertEqual(image_is_color(source), expected_color)

    def test_uniform_colors_are_color(self):
        for color in ('red', 'green', 'blue', 'yellow', 'cyan', 'magenta', '#805030'):
            with self.subTest(color=color):
                self.assert_color(Image.new('RGB', (64, 64), color), True)

    def test_uniform_rgb_grays_are_grayscale(self):
        for level in (0, 32, 127, 128, 200, 255):
            with self.subTest(level=level):
                self.assert_color(Image.new('RGB', (64, 64), (level, level, level)), False)

    def test_rgb_grayscale_gradient_stays_grayscale(self):
        image = Image.new('RGB', (256, 16))
        image.putdata([(x, x, x) for _ in range(16) for x in range(256)])
        self.assert_color(image, False)

    def test_neutral_quantization_tolerance_is_preserved(self):
        self.assert_color(Image.new('RGB', (64, 64), (128, 129, 128)), False)

    def test_visible_uniform_tint_is_color(self):
        self.assert_color(Image.new('RGB', (64, 64), (150, 128, 128)), True)

    def test_grayscale_modes_stay_grayscale(self):
        for mode in ('1', 'L', 'LA'):
            with self.subTest(mode=mode):
                self.assert_color(Image.new(mode, (64, 64)), False)

    def test_palette_color_is_detected(self):
        image = Image.new('RGB', (64, 64), 'red').convert('P')
        self.assert_color(image, True)

    def test_rgba_color_is_detected(self):
        self.assert_color(Image.new('RGBA', (64, 64), (255, 0, 0, 255)), True)

    def test_uniform_color_is_detected_after_sampling(self):
        self.assert_color(Image.new('RGB', (1024, 16), 'blue'), True)

    def test_varying_color_remains_color(self):
        image = Image.new('RGB', (64, 64))
        image.putdata([(255, 0, 0) if x % 2 else (0, 0, 255) for x in range(64 * 64)])
        self.assert_color(image, True)


if __name__ == '__main__':
    unittest.main()
