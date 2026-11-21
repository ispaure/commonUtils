"""Internal heading anchors shared by reading, contents and formatted editing."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

import re


def _iter_headings(document, *, strip_syntax=False):
    """Yield level/title/unique anchor/block without mutating the document."""
    used = set()
    counters = {}
    block = document.begin()
    while block.isValid():
        level = block.blockFormat().headingLevel()
        if level:
            title = block.text()
            if strip_syntax:
                title = re.sub(r'^#{1,6} ', '', title, count=1)
            slug = re.sub(r'[^\w\- ]', '', title.lower()).replace(' ', '-')
            count = counters.get(slug, 0)
            anchor = f'{slug}-{count}' if count else slug
            while anchor in used:
                count += 1
                anchor = f'{slug}-{count}'
            counters[slug] = count + 1
            used.add(anchor)
            yield level, title, anchor, block
        block = block.next()
