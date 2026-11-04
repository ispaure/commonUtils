"""Cheap local-image eligibility shared by browser adapters; no content reads.

Decoders decide which of these image/texture containers they support. Unknown,
corrupt and unsupported files keep the browser's ordinary file icon.
"""
from pathlib import Path

IMAGE_SUFFIXES = frozenset({'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp',
    '.tif', '.tiff', '.ico', '.icns', '.tga', '.dds', '.ktx', '.pkm', '.pbm',
    '.pgm', '.ppm', '.xbm', '.xpm', '.hdr', '.exr'})
MAX_IMAGE_BYTES = 16 * 1024 * 1024


def local_image(path):
    """Use mount metadata (including resolved links), without opening the file."""
    from .network import is_network_location
    return Path(path).suffix.lower() in IMAGE_SUFFIXES and not is_network_location(path)


def local_provider_image(provider, path):
    """Virtual/cloud identities must never be interpreted as physical paths."""
    from ..runtime.resources.local import LocalFiles
    return isinstance(provider, LocalFiles) and local_image(provider.root / provider.relative(path))


def local_native_image(provider, path, cancelled=lambda: False):
    """Bounded native raster input when no resizing bridge is available.

    Native widgets own decoding/resizing. Validate headers first so malformed or
    excessively large input never reaches them. Texture support stays decoder
    specific; this portable fallback accepts PNG/JPEG/WebP/GIF only.
    """
    from ..runtime.operations import check_cancelled
    from ..formats.image_headers import image_header, gif_header
    check_cancelled(cancelled)
    if not local_provider_image(provider, path):
        return b''
    try:
        before = provider.entry(path)
        if before['directory'] or before.get('size', 0) > MAX_IMAGE_BYTES:
            return b''
        with provider.open(path) as stream:
            data = stream.read(MAX_IMAGE_BYTES + 1)
        check_cancelled(cancelled)
        if before != provider.entry(path):
            return b''
        header = (gif_header(data, max_bytes=MAX_IMAGE_BYTES) if data[:6] in (b'GIF87a', b'GIF89a')
                  else image_header(data, max_bytes=MAX_IMAGE_BYTES))
        if header.width * header.height > 16 * 1024 * 1024:
            return b''
        return data
    except (OSError, ValueError):
        return b''
