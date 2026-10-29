"""Speech-only prose boundaries with offsets into the untouched source text."""
from array import array
import re


# Keep ordinary compound hyphens, apostrophes, minus signs and numeric en-dash
# ranges. Em dashes and horizontal bars mark prose boundaries even without spaces.
PROSE_DASH = re.compile(r'[—―]|(?<!\d)–|–(?!\d)')
WORD_BOUNDARY = re.compile(r'\s+|[—―]|(?<!\d)–|–(?!\d)')


def utf16_length(text):
    return len(text.encode('utf-16-le')) // 2


def word_ranges(text, base=0):
    """Yield source UTF-16 spans, excluding whitespace and prose dash separators."""
    previous, offset = 0, base
    for match in WORD_BOUNDARY.finditer(text):
        length = utf16_length(text[previous:match.start()])
        if length:
            yield offset, offset + length
        offset += length + utf16_length(match[0])
        previous = match.end()
    length = utf16_length(text[previous:])
    if length:
        yield offset, offset + length


def dash_padding(text, index):
    return (int(index > 0 and not text[index - 1].isspace()),
            int(index + 1 < len(text) and not text[index + 1].isspace()))


class SpeechText:
    """One bounded engine payload; inserted spaces map to dash-edge positions."""
    def __init__(self, source):
        parts, offset = [], 0
        self.offsets = array('I', [0])
        dashes = {match.start() for match in PROSE_DASH.finditer(source)}
        for index, char in enumerate(source):
            before, after = dash_padding(source, index) if index in dashes else (0, 0)
            if before:
                parts.append(' ')
                self.offsets.append(offset)
            parts.append(char)
            length = utf16_length(char)
            self.offsets.extend(range(offset + 1, offset + length + 1))
            offset += length
            if after:
                parts.append(' ')
                self.offsets.append(offset)
        self.text = ''.join(parts)

    def source_range(self, start, end):
        if not 0 <= start < end < len(self.offsets):
            return None
        left, right = self.offsets[start], self.offsets[end]
        return (left, right) if left < right else None
