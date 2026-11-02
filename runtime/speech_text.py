"""Speech-only prose boundaries with offsets into the untouched source text."""
from array import array
import re
import unicodedata


# Keep ordinary compound hyphens, apostrophes, minus signs and numeric en-dash
# ranges. Em dashes and horizontal bars mark prose boundaries even without spaces.
PROSE_DASH = re.compile(r'[—―]|(?<!\d)–|–(?!\d)|(?<=[^\W\d_])--+(?=[^\W\d_])|(?<!\S)-+(?=\s)')
WORD_SEPARATOR = re.compile(r'\s+|[!?…\u3002！？؟।]+|\.{2,}')
SENTENCE_END = re.compile(r'''([.!?…。！？؟।]+)["'”’»›)\]】」』]*(?=\s|$)''')
ABBREVIATIONS = frozenset(('mr', 'mrs', 'ms', 'dr', 'prof', 'sr', 'jr', 'st',
                           'vs', 'etc', 'e.g', 'i.e', 'fig', 'no'))


def prose_dashes(text):
    for match in PROSE_DASH.finditer(text):
        if match[0].startswith('-'):
            left, right = match.start() - 1, match.end()
            while left >= 0 and text[left].isspace():
                left -= 1
            while right < len(text) and text[right].isspace():
                right += 1
            if (left >= 0 and text[left].isdigit()) or (right < len(text) and text[right].isdigit()):
                continue  # Spaced subtraction, not a prose interruption.
            if (left >= 0 and right < len(text) and text[left].isalpha() and text[right].isalpha()
                    and (left == 0 or not text[left - 1].isalnum())
                    and (right + 1 == len(text) or not text[right + 1].isalnum())):
                continue  # Single-letter algebra, such as x - y.
        yield match


def has_content(text):
    """Punctuation alone is a pause, not an independently spoken word."""
    return any(not char.isspace() and char != '\u00ad'
               and not unicodedata.category(char).startswith('P') for char in text)


def sentence_ends(text):
    """Conservative queue boundaries; leave prosody and ambiguous prose to the voice."""
    for match in SENTENCE_END.finditer(text):
        if match[1] == '.':
            start = match.start()
            while start > 0 and (text[start - 1].isalnum() or text[start - 1] in '_.'):
                start -= 1
            token = text[start:match.start()]
            if (token.casefold() in ABBREVIATIONS or len(token) == 1 and token.isalpha()
                    or re.fullmatch(r'(?:[^\W\d_]\.)+[^\W\d_]', token)):
                continue
        yield match.end()


def utf16_length(text):
    return len(text.encode('utf-16-le')) // 2


def word_ranges(text, base=0):
    """Yield source UTF-16 words, excluding prose separators and punctuation alone."""
    previous, offset = 0, base
    separators = sorted([(match.start(), match.end()) for match in WORD_SEPARATOR.finditer(text)]
                        + [(match.start(), match.end()) for match in prose_dashes(text)])
    for start, end in separators:
        if start < previous:
            continue
        length = utf16_length(text[previous:start])
        if length and has_content(text[previous:start]):
            yield offset, offset + length
        offset += length + utf16_length(text[start:end])
        previous = end
    length = utf16_length(text[previous:])
    if length and has_content(text[previous:]):
        yield offset, offset + length


def dash_padding(text, index, end=None):
    end = index + 1 if end is None else end
    return (int(index > 0 and not text[index - 1].isspace()),
            int(end < len(text) and not text[end].isspace()))


class SpeechText:
    """Engine payload with UTF-16 mappings for padding, collapsed dashes and soft hyphens."""
    def __init__(self, source):
        parts, offset = [], 0
        self.offsets = array('I', [0])
        dashes = {match.start(): match for match in prose_dashes(source)}
        index = 0
        while index < len(source):
            char = source[index]
            match = dashes.get(index)
            end = match.end() if match is not None else index + 1
            before, after = dash_padding(source, index, end) if match is not None else (0, 0)
            if before:
                parts.append(' ')
                self.offsets.append(offset)
            length = utf16_length(source[index:end])
            if char == '\u00ad':
                # Discretionary line-wrap hyphens must not split a spoken word.
                self.offsets[-1] = offset + length
            elif match is not None and char == '-':
                parts.append('—')
                self.offsets.append(offset + length)
            else:
                parts.append(char)
                self.offsets.extend(range(offset + 1, offset + length + 1))
            offset += length
            if after:
                parts.append(' ')
                self.offsets.append(offset)
            index = end
        self.text = ''.join(parts)

    def source_range(self, start, end):
        if not 0 <= start < end < len(self.offsets):
            return None
        left, right = self.offsets[start], self.offsets[end]
        return (left, right) if left < right else None
