"""Bounded archive text/image decoding; no launching, prompts or GUI objects."""
from ..operations import check_cancelled
from .reading import reader, _members, _name, _stream


def preview(path, name, *, password=None, progress=lambda *args: None, cancelled=lambda: False):
    """Read at most 256 KiB; never execute or launch an archive member."""
    with reader(path, password) as (archive, is_zip):
        item = next(item for item in _members(archive, is_zip) if _name(item, is_zip) == name)
        check_cancelled(cancelled)
        with _stream(archive, item, is_zip) as stream:
            data = stream.read(256 * 1024 + 1)
    truncated = len(data) > 256 * 1024
    data = data[:256 * 1024]
    if b'\x00' in data:
        return 'Binary file. Extract this entry to open it in another application.'
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        return 'Preview is available for UTF-8 text. Extract this entry to open it.'
    return text + ('\n\n[Preview limited to 256 KiB]' if truncated else '')


def preview_image(path, name, *, password=None, progress=lambda *args: None, cancelled=lambda: False):
    """Decode one bounded image frame into a thumbnail for the GUI thread."""
    from io import BytesIO
    from PIL import Image, ImageOps
    with reader(path, password) as (archive, is_zip):
        item = next(item for item in _members(archive, is_zip) if _name(item, is_zip) == name)
        size = item.file_size if is_zip else item.size
        if size > 16 * 1024 * 1024:
            return 'Image preview is limited to 16 MiB. Extract this file to open it.'
        with _stream(archive, item, is_zip) as stream:
            data = stream.read(16 * 1024 * 1024 + 1)
    check_cancelled(cancelled)
    if len(data) > 16 * 1024 * 1024:
        return 'Image preview is limited to 16 MiB. Extract this file to open it.'
    with Image.open(BytesIO(data)) as source:
        if source.width * source.height > 25_000_000:
            return 'Image preview is limited to 25 megapixels. Extract this file to open it.'
        source.thumbnail((1000, 1000))
        image = ImageOps.exif_transpose(source).convert('RGBA')
        output = BytesIO()
        image.save(output, format='PNG')
    check_cancelled(cancelled)
    return output.getvalue()
