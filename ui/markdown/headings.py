"""Internal heading anchors shared by reading, contents and formatted editing."""
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
