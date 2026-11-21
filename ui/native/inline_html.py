"""Load fully inlined document HTML without a synthetic website origin on iOS."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from urllib.parse import urlsplit
from .text_size import native_backend


def set_inline_html(view, root_url, content):
    """Preserve routing identifiers and the view's privacy/navigation contracts."""
    target = root_url
    if isinstance(root_url, str) and getattr(view, '_impl', None) is not None:
        parts = urlsplit(root_url)
        if (parts.scheme in {'http', 'https'} and parts.hostname
                and parts.hostname.endswith('.invalid')
                and native_backend(view).startswith('toga_iOS.')):
            target = 'app-document' + root_url[root_url.index(':'):]
    return view.set_content(target, content)
