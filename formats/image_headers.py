"""Bounded PNG/JPEG/WebP header probes; does not certify decoded pixel integrity."""

from dataclasses import dataclass
import struct


@dataclass(frozen=True)
class ImageHeader:
    format: str
    width: int
    height: int
    animated: bool = False


def _webp_header(data):
    """Read bounded static WebP canvas dimensions before native decoding."""
    if (
        len(data) < 20
        or data[:4] != b"RIFF"
        or data[8:12] != b"WEBP"
        or int.from_bytes(data[4:8], "little") + 8 != len(data)
    ):
        raise ValueError("Invalid WebP page.")
    kind, size = data[12:16], int.from_bytes(data[16:20], "little")
    if size > len(data) - 20 or size + (size & 1) > len(data) - 20:
        raise ValueError("Truncated WebP page.")
    chunk = data[20 : 20 + size]
    if kind == b"VP8X" and size == 10:
        return ImageHeader(
            "webp",
            1 + int.from_bytes(chunk[4:7], "little"),
            1 + int.from_bytes(chunk[7:10], "little"),
            bool(chunk[0] & 2),
        )
    if kind == b"VP8L" and size >= 5 and chunk[0] == 0x2F:
        bits = int.from_bytes(chunk[1:5], "little")
        if bits >> 29:
            raise ValueError("Unsupported WebP version.")
        return ImageHeader("webp", (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
    if (
        kind == b"VP8 "
        and size >= 10
        and not chunk[0] & 1
        and chunk[3:6] == b"\x9d\x01\x2a"
    ):
        return ImageHeader(
            "webp",
            int.from_bytes(chunk[6:8], "little") & 0x3FFF,
            int.from_bytes(chunk[8:10], "little") & 0x3FFF,
        )
    raise ValueError("Invalid WebP page header.")


def image_header(data, *, max_bytes):
    if type(max_bytes) is not int or max_bytes < 0:
        raise ValueError("Image byte limit must be a nonnegative integer.")
    if not isinstance(data, bytes) or len(data) > max_bytes:
        raise ValueError("Image exceeds the byte limit.")
    if len(data) >= 33 and data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        format = "png"
        width, height = struct.unpack(">II", data[16:24])
    elif data.startswith(b"\xff\xd8"):
        format = "jpeg"
        offset, width, height = 2, 0, 0
        while offset + 4 <= len(data):
            if data[offset] != 255:
                raise ValueError("Invalid JPEG page.")
            while offset < len(data) and data[offset] == 255:
                offset += 1
            if offset >= len(data):
                break
            marker = data[offset]
            offset += 1
            if marker in (0xD9, 0xDA):
                break
            if marker == 0x01 or 0xD0 <= marker <= 0xD8:
                continue
            if offset + 2 > len(data):
                break
            length = int.from_bytes(data[offset : offset + 2], "big")
            if length < 2 or offset + length > len(data):
                raise ValueError("Invalid JPEG segment.")
            if marker in {
                0xC0,
                0xC1,
                0xC2,
                0xC3,
                0xC5,
                0xC6,
                0xC7,
                0xC9,
                0xCA,
                0xCB,
                0xCD,
                0xCE,
                0xCF,
            }:
                if length < 8:
                    raise ValueError("Invalid JPEG dimensions.")
                height, width = struct.unpack(">HH", data[offset + 3 : offset + 7])
                break
            offset += length
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        header = _webp_header(data)
        if header.width <= 0 or header.height <= 0:
            raise ValueError("Invalid image dimensions.")
        return header
    else:
        raise ValueError("Use PNG, JPEG or WebP images.")
    if width <= 0 or height <= 0:
        raise ValueError("Invalid image dimensions.")
    return ImageHeader(format, width, height)
