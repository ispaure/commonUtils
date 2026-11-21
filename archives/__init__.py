"""Reusable ZIP/TAR operations with bounded streams and verified staged writes.

Passwords are explicit parameters. Configuration, prompts, session credentials
and application navigation belong to the caller. Metadata declarations and
suffix matching do not import Qt, image decoders or cryptography backends.
"""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from importlib import import_module
from .models import Entry
from .formats import (ARCHIVE_SUFFIXES, ZIP_SUFFIXES, TAR_SUFFIXES, ARCHIVE_FILTER,
                      is_supported_archive, is_zip_archive, is_image_entry)

_OPERATIONS = {'entries': 'reading', 'test_archive': 'reading', 'extract': 'extraction',
               'create': 'creation', 'update_zip': 'editing', 'preview': 'previews',
               'preview_image': 'previews'}


def __getattr__(name):
    module = _OPERATIONS.get(name)
    if module is None:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    value = getattr(import_module(f'{__name__}.{module}'), name)
    globals()[name] = value
    return value


__all__ = ['Entry', 'ARCHIVE_SUFFIXES', 'ZIP_SUFFIXES', 'TAR_SUFFIXES', 'ARCHIVE_FILTER',
           'is_supported_archive', 'is_zip_archive', 'is_image_entry', *_OPERATIONS]
