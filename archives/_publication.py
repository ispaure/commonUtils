"""No-replace publication for verified, newly created archive files."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

import os

from ..runtime.platform import OS, get_os


def publish_created_archive(staged, destination):
    try:
        platform = get_os()
    except RuntimeError:
        platform = OS.UNKNOWN
    if platform is OS.ANDROID:
        # Android can deny hard links even within app-private storage.
        from ..persistence.publication import rename_exclusive
        rename_exclusive(staged, destination)
    else:
        os.link(staged, destination)
