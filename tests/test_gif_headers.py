"""GIF container boundaries and dimensions without importing a UI or decoder."""
import base64
import struct
import unittest

from commonUtils.formats.image_headers import gif_header, image_header

GIF = base64.b64decode(
    'R0lGODlhBAAEAIEAAP8AAAAAAAAAAAAAACH/C05FVFNDQVBFMi4wAwEAAAAh+QQABgAAACwAAAAABAAE'
    'AAAICQABCBxIsCCAgAAh+QQBBgABACwAAAAABAAEAIEAAP8AAAAAAAAAAAAICQABCBxIsCCAgAA7')


class GifHeaderTests(unittest.TestCase):
    def test_animation_canvas_and_legacy_static_gif(self):
        header = gif_header(GIF, max_bytes=len(GIF))
        self.assertEqual((header.format, header.width, header.height, header.animated), ('gif', 4, 4, True))
        # Keep the first frame and replace subsequent blocks with the trailer.
        first_end = GIF.index(b'\x21\xf9', GIF.index(b'\x21\xf9') + 2)
        static = b'GIF87a' + GIF[6:first_end] + b';'
        self.assertFalse(gif_header(static, max_bytes=len(static)).animated)
        with self.assertRaises(ValueError):
            image_header(GIF, max_bytes=len(GIF))  # Existing static-image API stays unchanged.

    def test_every_truncation_is_rejected(self):
        for length in range(len(GIF)):
            with self.subTest(length=length), self.assertRaises(ValueError):
                gif_header(GIF[:length], max_bytes=len(GIF))

    def test_limits_types_canvas_and_frames(self):
        for limit in (-1, 1.5, True, len(GIF) - 1):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                gif_header(GIF, max_bytes=limit)
        for data in ('GIF89a', bytearray(GIF), b'PNG' + GIF[3:]):
            with self.subTest(data=type(data)), self.assertRaises(ValueError):
                gif_header(data, max_bytes=1024)
        for width, height in ((0, 4), (4, 0), (3, 4), (4, 3)):
            with self.subTest(width=width, height=height), self.assertRaises(ValueError):
                gif_header(GIF[:6] + struct.pack('<HH', width, height) + GIF[10:], max_bytes=1024)
        start = GIF.index(b',')
        for replacement in (b';', b'?', b'\x21', b',' + b'\0' * 9 + b'\x02\0;'):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                gif_header(GIF[:start] + replacement, max_bytes=1024)
