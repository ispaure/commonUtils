"""Qt structure with editable Markdown syntax and safe, non-mutating export."""
import re
from .. import pyside as qt
from .syntax import _units
from .links import link_spans
from .syntax import fenced_regions, HEADING, inline_spans, FENCE_OPEN, fence_close


class LiveMarkdownDocument(qt.QTextDocument):
    def toMarkdown(self, *args, **kwargs):
        """Preserve authored delimiters while Qt serializes tables, links and images.

        Export a clone with temporary plain tokens, then restore source syntax.
        The editor document, cursor, dirty state and undo stack are never changed.
        """
        clone = self.clone()
        original = clone.toPlainText()
        prefix = 'zzmd'
        while prefix in original:
            prefix += 'z'
        tokens = {}
        def token(text):
            key = f'{prefix}{len(tokens)}z'
            tokens[key] = text
            return key
        regions = list(fenced_regions(clone))
        for opening, closing, _, _ in reversed(regions):
            cursor = qt.QTextCursor(clone)
            cursor.setPosition(opening.position())
            end = closing.position() + _units(closing.text()) if closing else clone.characterCount() - 1
            cursor.setPosition(end, qt.QTextCursor.MoveMode.KeepAnchor)
            text = cursor.selectedText().replace('\u2029', '\n')
            cursor.insertText(token(text), qt.QTextCharFormat())
            cursor.setBlockFormat(qt.QTextBlockFormat())
        changes = []
        block = clone.begin()
        while block.isValid():
            heading = HEADING.match(block.text())
            if heading and block.blockFormat().headingLevel():
                changes.append((block.position(), heading.end(), ''))
            links = list(link_spans(block.text()))
            for span in links:
                changes.append((block.position() + _units(block.text()[:span.start]),
                                _units(block.text()[span.start:span.end]), token(block.text()[span.start:span.end])))
            for match in re.finditer(r'[\\*_`]', block.text()):
                if any(span.start <= match.start() < span.end for span in links):
                    continue
                # Fenced blocks were protected above. These characters now belong
                # to authored inline syntax, not generated Qt formatting.
                changes.append((block.position() + _units(block.text()[:match.start()]), 1, token(match.group())))
            block = block.next()
        for position, length, replacement in sorted(changes, reverse=True):
            cursor = qt.QTextCursor(clone)
            cursor.setPosition(position)
            cursor.setPosition(position + length, qt.QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(replacement)
        result = clone.toMarkdown(*args, **kwargs)
        if tokens:
            result = re.sub('|'.join(re.escape(key) for key in tokens), lambda match: tokens[match.group()], result)
        return result


def materialize_formats(editor):
    """Turn loaded rich inline styles/fences into editable source without losing tables."""
    document = editor.document()
    # Qt can add an empty first paragraph inside the first cell when a code
    # block precedes a table. Its writer then invents an extra header cell.
    # Remove only that empty paragraph within the same cell, preserving the table.
    for frame in document.rootFrame().childFrames():
        if isinstance(frame, qt.QTextTable):
            cell = frame.cellAt(0, 0)
            cursor = cell.firstCursorPosition()
            block = cursor.block()
            following = block.next()
            if (not block.text() and following.isValid() and following.text()
                    and following.position() < cell.lastCursorPosition().position()):
                cursor.deleteChar()
    changes = []
    code_groups = []
    code_start = None
    block = document.begin()
    while block.isValid():
        code = block.blockFormat().nonBreakableLines()
        if code and code_start is None:
            code_start = block
        if code_start is not None and (not code or not block.next().isValid()):
            last = block if code else block.previous()
            code_groups.append((code_start, last))
            code_start = None
        if not code:
            heading = block.blockFormat().headingLevel()
            if heading and not HEADING.match(block.text()):
                changes.append((block.position(), 0, '#' * heading + ' ', qt.QTextCharFormat()))
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                fmt = fragment.charFormat()
                is_code = fmt.fontFixedPitch() or any('mono' in family.lower() for family in (fmt.fontFamilies() or ()))
                bold = fmt.fontWeight() >= qt.QFont.Weight.Bold and not heading
                italic = fmt.fontItalic()
                marker = '`' if is_code else '**' if bold else ''
                if italic and not is_code:
                    marker += '*'
                if marker:
                    text = fragment.text()
                    if is_code and '`' in text:
                        marker = '`' * (max(len(run) for run in re.findall(r'`+', text)) + 1)
                    base = qt.QTextCharFormat(fmt)
                    base.setFontWeight(qt.QFont.Weight.Bold if heading else qt.QFont.Weight.Normal)
                    base.setFontItalic(False)
                    base.setFontFixedPitch(False)
                    base.setFontFamilies(editor.font().families())
                    changes.append((fragment.position(), fragment.length(), marker + text + marker, base))
                iterator += 1
        block = block.next()
    for first, last in code_groups:
        language = first.blockFormat().property(qt.QTextFormat.Property.BlockCodeLanguage) or ''
        cursor = qt.QTextCursor(document)
        cursor.setPosition(first.position())
        cursor.setPosition(last.position() + _units(last.text()), qt.QTextCursor.MoveMode.KeepAnchor)
        text = cursor.selectedText().replace('\u2029', '\n')
        runs = re.findall(r'`+', text)
        marker = '`' * max(3, max((len(run) + 1 for run in runs), default=3))
        changes.append((first.position(), _units(text), marker + str(language) + '\n' + text + '\n' + marker,
                        qt.QTextCharFormat()))
        member = first
        while member.isValid() and member.position() <= last.position():
            fmt = member.blockFormat()
            fmt.setNonBreakableLines(False)
            fmt.clearProperty(qt.QTextFormat.Property.BlockCodeLanguage)
            fmt.clearProperty(qt.QTextFormat.Property.BlockCodeFence)
            qt.QTextCursor(member).setBlockFormat(fmt)
            member = member.next()
    for position, length, text, fmt in sorted(changes, key=lambda change: change[0], reverse=True):
        cursor = qt.QTextCursor(document)
        cursor.setPosition(position)
        cursor.setPosition(position + length, qt.QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(text, fmt)


def protect_escapes(markdown):
    """Keep escaped syntax through Qt parsing, without changing literal code payloads."""
    prefix = 'zzescape'
    while prefix in markdown:
        prefix += 'z'
    tokens = {}
    fence = None
    lines = []
    for line in markdown.splitlines(keepends=True):
        opening = FENCE_OPEN.fullmatch(line.rstrip('\r\n'))
        if fence:
            lines.append(line)
            if fence_close(line.rstrip('\r\n'), fence):
                fence = None
            continue
        if opening:
            fence = opening.group(1)
            lines.append(line)
            continue
        # Preserve complete authored links before Qt turns them into native anchors.
        for span in reversed(list(link_spans(line))):
            key = f'{prefix}{len(tokens)}z'
            tokens[key] = line[span.start:span.end]
            line = line[:span.start] + key + line[span.end:]
        code = [(span.start, span.end) for span in inline_spans(line) if span.marker.startswith('`')]
        def replace(match):
            if any(start <= match.start() < end for start, end in code):
                return match.group()
            key = f'{prefix}{len(tokens)}z'
            tokens[key] = match.group()
            return key
        lines.append(re.sub(r'\\[\\*_`]', replace, line))
    return ''.join(lines), tokens


def restore_escapes(document, tokens):
    for token, text in tokens.items():
        while True:
            cursor = document.find(token)
            if cursor.isNull():
                break
            cursor.insertText(text)
