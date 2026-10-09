"""Internal same-pane rich Markdown editing and source synchronization."""
from .. import pyside as qt
from ...markdownUtils import split_frontmatter
from .headings import _iter_headings
from .syntax import HEADING
from .extensions import reading_source


class MarkdownFormattedMixin:
    def active_editor(self):
        """Current editing widget; source remains available through editor."""
        return self.formatted_editor if self.edit_mode.currentData() == 'formatted' else self.editor

    def _rich_pending(self):
        return self._rich_snapshot is not None and self.formatted_editor.document().toMarkdown() != self._rich_snapshot

    def _formatted_changed(self):
        if self._rich_snapshot is not None:
            self._modified_changed(self.is_modified)

    def _load_formatted(self):
        source = self.editor.toPlainText()
        self.formatted_editor.document().setBaseUrl(
            qt.QUrl.fromLocalFile(str(self._loaded_path.parent) + '/') if self._loaded_path else qt.QUrl())
        parts = split_frontmatter(source)
        if not parts.complete:
            self.set_edit_mode('source')
            self.status.setText('Unclosed YAML properties: repair the closing --- in Source mode.')
            return
        if reading_source(parts.body)[1]:
            # Qt's rich exporter escapes [!type] markers after actual edits.
            # Keep these documents in exact-source mode until our live editor
            # can round-trip their custom syntax, rather than damaging callouts.
            self.set_edit_mode('source')
            self.status.setText('Callouts are shown in Read mode. Edit their exact Markdown in Source mode.')
            return
        if self._rich_source is not None and self._rich_snapshot is not None and parts.body == split_frontmatter(self._rich_source).body:
            self._rich_source = source
            return
        self._rich_snapshot = None
        self.formatted_editor.setMarkdown(parts.body)
        self.formatted_editor.document().setModified(False)
        self._rich_source = source
        self._rich_snapshot = self.formatted_editor.document().toMarkdown()

    def _sync_formatted(self):
        if not self._rich_pending():
            return
        body = self.formatted_editor.document().toMarkdown()
        source = split_frontmatter(self.editor.toPlainText()).prefix + body
        self._replace_source_text(source)
        self._rich_source = self.editor.toPlainText()
        self._rich_snapshot = body
        self._modified_changed(True)

    def _replace_source_text(self, text):
        """Replace source as one undo step without resetting the editor's history."""
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        cursor.select(qt.QTextCursor.SelectionType.Document)
        cursor.insertText(text)
        cursor.endEditBlock()
        self.editor.document().setModified(True)

    def markdown_text(self):
        """Return current Markdown, synchronizing actual formatted edits only."""
        self._sync_formatted()
        return self.editor.toPlainText()

    def set_edit_mode(self, mode):
        """Choose 'formatted' (default) or 'source', preserving unsaved edits."""
        index = self.edit_mode.findData(mode)
        if index < 0:
            raise ValueError('Editing mode must be formatted or source')
        self.edit_mode.setCurrentIndex(index)

    def _change_edit_mode(self, index):
        self._sync_formatted()
        if self.edit_button.isChecked():
            self.set_editing(True)

    def _update_edit_actions(self):
        if not hasattr(self, 'undo_action'):
            return
        self._update_table_actions()
        enabled = self.edit_button.isChecked()
        document = self.active_editor().document()
        self.undo_action.setEnabled(enabled and document.isUndoAvailable())
        self.redo_action.setEnabled(enabled and document.isRedoAvailable())
        for action in (self.cut_action, self.paste_action, self.bold_action, self.italic_action,
                       self.code_action, self.link_action):
            action.setEnabled(enabled)

    def _scroll_formatted_heading(self, anchor):
        for _, _, candidate, block in _iter_headings(self.formatted_editor.document(), strip_syntax=True):
            if candidate == anchor:
                self.formatted_editor.setTextCursor(qt.QTextCursor(block))
                self.formatted_editor.ensureCursorVisible()
                self.formatted_editor.setFocus()
                return

    def format_inline(self, marker):
        self.formatted_editor.apply_inline_format(marker)
        self.formatted_editor.setFocus()

    def format_blocks(self, prefix):
        cursor = self.formatted_editor.textCursor()
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
                    size = self.formatted_editor.font().pointSizeF()
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
        self.formatted_editor.setFocus()

    def format_link(self, url):
        cursor = self.formatted_editor.textCursor()
        label = cursor.selectedText().replace('\u2029', ' ') if cursor.hasSelection() else 'link text'
        cursor.beginEditBlock()
        cursor.insertText(f'[{label}](<{url}>)', qt.QTextCharFormat())
        cursor.endEditBlock()
        self.formatted_editor.setTextCursor(cursor)
        self.formatted_editor.setFocus()
