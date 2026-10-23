"""Rich/source synchronization with explicit editors, document state and callbacks."""
from .. import pyside as qt
from ...formats.markdown import split_frontmatter
from .headings import _iter_headings
from .syntax import HEADING
from .extensions import reading_source
from .session import MarkdownDocumentState
from collections.abc import Callable


class FormattedEditing:
    """Own rich import/synchronization; no access to the containing viewer."""
    def __init__(self, source: qt.QPlainTextEdit, editor: qt.QTextEdit, mode: qt.QComboBox,
                 document: MarkdownDocumentState, *, set_mode: Callable[[str], None],
                 status: Callable[[str], None], modified: Callable[[bool], None]):
        self.source = source
        self.editor = editor
        self.mode = mode
        self.document = document
        self.set_mode = set_mode
        self.status = status
        self.modified = modified

    def active_editor(self):
        """Choose the rich or source editor from the mode selector."""
        return self.editor if self.mode.currentData() == 'formatted' else self.source

    def pending(self):
        return self.document.rich_snapshot is not None and self.editor.document().toMarkdown() != self.document.rich_snapshot

    def load(self):
        source = self.source.toPlainText()
        self.editor.document().setBaseUrl(
            qt.QUrl.fromLocalFile(str(self.document.loaded_path.parent) + '/') if self.document.loaded_path else qt.QUrl())
        parts = split_frontmatter(source)
        if not parts.complete:
            self.set_mode('source')
            self.status('Unclosed YAML properties: repair the closing --- in Source mode.')
            return
        if reading_source(parts.body)[1]:
            # Qt's rich exporter escapes [!type] markers after actual edits.
            # Keep these documents in exact-source mode until our live editor
            # can round-trip their custom syntax, rather than damaging callouts.
            self.set_mode('source')
            self.status('Callouts are shown in Read mode. Edit their exact Markdown in Source mode.')
            return
        if self.document.rich_source is not None and self.document.rich_snapshot is not None and parts.body == split_frontmatter(self.document.rich_source).body:
            self.document.rich_source = source
            return
        self.document.rich_snapshot = None
        self.editor.setMarkdown(parts.body)
        self.editor.document().setModified(False)
        self.document.rich_source = source
        self.document.rich_snapshot = self.editor.document().toMarkdown()

    def sync(self):
        if not self.pending():
            return
        body = self.editor.document().toMarkdown()
        source = split_frontmatter(self.source.toPlainText()).prefix + body
        self.replace_source(source)
        self.document.rich_source = self.source.toPlainText()
        self.document.rich_snapshot = body
        self.modified(True)

    def replace_source(self, text):
        """Replace source as one undo step without resetting the editor's history."""
        cursor = self.source.textCursor()
        cursor.beginEditBlock()
        cursor.select(qt.QTextCursor.SelectionType.Document)
        cursor.insertText(text)
        cursor.endEditBlock()
        self.source.document().setModified(True)

    def text(self):
        """Return current Markdown, synchronizing actual formatted edits only."""
        self.sync()
        return self.source.toPlainText()

    def scroll_heading(self, anchor):
        for _, _, candidate, block in _iter_headings(self.editor.document(), strip_syntax=True):
            if candidate == anchor:
                self.editor.setTextCursor(qt.QTextCursor(block))
                self.editor.ensureCursorVisible()
                self.editor.setFocus()
                return

    def format_inline(self, marker):
        self.editor.apply_inline_format(marker)
        self.editor.setFocus()

    def format_blocks(self, prefix):
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        if prefix == '- ':
            fmt = qt.QTextListFormat()
            fmt.setStyle(qt.QTextListFormat.Style.ListDisc)
            cursor.createList(fmt)
        else:
            start, end = cursor.selectionStart(), cursor.selectionEnd()
            cursor.setPosition(start)
            while True:
                block = cursor.block()
                fmt = block.blockFormat()
                if prefix.startswith('#') or not prefix:
                    level = len(prefix.strip())
                    heading = HEADING.match(block.text())
                    prefix_cursor = qt.QTextCursor(block)
                    if heading:
                        prefix_cursor.movePosition(qt.QTextCursor.MoveOperation.NextCharacter,
                                                   qt.QTextCursor.MoveMode.KeepAnchor, heading.end())
                    prefix_cursor.insertText('#' * level + ' ' if level else '', qt.QTextCharFormat())
                    fmt.setHeadingLevel(level)
                    cursor.setBlockFormat(fmt)
                    chars = qt.QTextCharFormat()
                    chars.setFontWeight(qt.QFont.Weight.Bold if level else qt.QFont.Weight.Normal)
                    size = self.editor.font().pointSizeF()
                    chars.setFontPointSize((size if size > 0 else 12) * ((1.9, 1.6, 1.35, 1.2, 1.1, 1)[level - 1] if level else 1))
                    cursor.select(qt.QTextCursor.SelectionType.BlockUnderCursor)
                    cursor.mergeCharFormat(chars)
                else:
                    fmt.setProperty(qt.QTextFormat.Property.BlockQuoteLevel, 1)
                    cursor.setBlockFormat(fmt)
                following = block.next()
                if not following.isValid() or following.position() >= end:
                    break
                cursor.setPosition(following.position())
        cursor.endEditBlock()
        self.editor.setFocus()

    def format_link(self, url):
        cursor = self.editor.textCursor()
        label = cursor.selectedText().replace('\u2029', ' ') if cursor.hasSelection() else 'link text'
        cursor.beginEditBlock()
        cursor.insertText(f'[{label}](<{url}>)', qt.QTextCharFormat())
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()
