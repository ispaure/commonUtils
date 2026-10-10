"""Supported suffixes shared by models, dialogs, drag/drop and activation."""
from pathlib import Path

ZIP_SUFFIXES = ('.zip', '.cbz')
TAR_SUFFIXES = ('.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2', '.tar.xz', '.txz')
ARCHIVE_SUFFIXES = ZIP_SUFFIXES + TAR_SUFFIXES
IMAGE_SUFFIXES = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.tif', '.tiff')
ARCHIVE_FILTER = 'Supported archives (' + ' '.join('*' + suffix for suffix in ARCHIVE_SUFFIXES) + ');;All files (*)'


def is_supported_archive(path):
    return str(path).lower().endswith(ARCHIVE_SUFFIXES)


def is_zip_archive(path):
    return str(path).lower().endswith(ZIP_SUFFIXES)


def is_image_entry(name):
    return Path(name).suffix.lower() in IMAGE_SUFFIXES
