"""Bounded provider-backed raster images for native Markdown readers/editors."""

def folder_image_source(provider, document):
    """Resolve sibling raster images through the document's rooted provider."""
    import posixpath
    from urllib.parse import unquote, urlsplit
    from ...formats.image_headers import image_header, gif_header
    MAX_IMAGE = 8 * 1024 * 1024
    used = 0
    cache = {}
    parent = posixpath.dirname(provider.relative(document))

    def load(target):
        nonlocal used
        if used >= 16 * 1024 * 1024:
            return None
        parsed = urlsplit(target)
        path_text = unquote(parsed.path)
        if (parsed.scheme or parsed.netloc or parsed.query or not path_text
                or path_text.startswith(('/', '\\')) or '\\' in path_text
                or any(ord(c) < 32 for c in path_text)):
            return None
        path = posixpath.normpath(posixpath.join(parent, path_text))
        if path == '..' or path.startswith('../'):
            return None
        path = provider.relative(path)
        if not path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
            return None
        # Recheck cached entries too: another scene can revoke credentials.
        before = provider.entry(path)
        if (before['directory'] or before.get('size', 0) > MAX_IMAGE + 64
                or used + max(0, before.get('size', 0) - 64) > 16 * 1024 * 1024):
            return None
        if path in cache:
            revision, image = cache[path]
            if revision != before:
                raise ValueError('Image changed while rendering Markdown.')
            if used + len(image[1]) > 16 * 1024 * 1024:
                return None
            used += len(image[1])
            return image
        with provider.open(path) as stream:
            data = stream.read(MAX_IMAGE + 1)
        if provider.entry(path) != before:
            raise ValueError('Image changed while rendering Markdown.')
        header = (gif_header(data, max_bytes=MAX_IMAGE) if data[:6] in (b'GIF87a', b'GIF89a')
                  else image_header(data, max_bytes=MAX_IMAGE))
        if header.animated and header.format != 'gif':
            raise ValueError('Animated WebP images are not supported.')
        if (header.width > 8192 or header.height > 8192
                or header.width * header.height > 16_000_000):
            raise ValueError('Image dimensions exceed the mobile 16-megapixel limit.')
        if used + len(data) > 16 * 1024 * 1024:
            return None
        used += len(data)
        mime = 'image/' + header.format
        image = mime, data
        cache[path] = before, image
        return image
    return load



def local_image_source(document, root):
    """Build a provider-scoped source for a local Markdown wiki page."""
    from pathlib import Path
    from ...runtime.resources.local import LocalFiles
    root, document = Path(root).resolve(), Path(document).resolve()
    return folder_image_source(LocalFiles(root), document.relative_to(root).as_posix())
