"""Header mechanisms report facts; consuming readers decide decoder limits."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

import struct
import unittest

from commonUtils.formats.image_headers import image_header


def png(width, height):
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x02\0\0\0"
        + b"\0" * 4
    )


class ImageHeaderTests(unittest.TestCase):
    def test_dimensions_are_not_restricted_to_a_consumer_megapixel_limit(self):
        data = png(10000, 20000)
        header = image_header(data, max_bytes=len(data))
        self.assertEqual(
            (header.format, header.width, header.height, header.animated),
            ("png", 10000, 20000, False),
        )
        with self.assertRaises(ValueError):
            image_header(data, max_bytes=len(data) - 1)

    def test_webp_reports_animation_and_refuses_truncated_container(self):
        payload = (
            b"VP8X"
            + struct.pack("<I", 10)
            + b"\x02\0\0\0"
            + (99).to_bytes(3, "little")
            + (199).to_bytes(3, "little")
        )
        data = b"RIFF" + struct.pack("<I", len(payload) + 4) + b"WEBP" + payload
        header = image_header(data, max_bytes=100)
        self.assertEqual(
            (header.width, header.height, header.animated), (100, 200, True)
        )
        with self.assertRaises(ValueError):
            image_header(data[:-1], max_bytes=100)

    def test_invalid_inputs_do_not_produce_plausible_dimensions(self):
        for data in (b"", b"\xff\xd8", png(0, 10), b"GIF89a", "text"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                image_header(data, max_bytes=100)
