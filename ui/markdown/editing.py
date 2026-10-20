"""Internal source-editing actions and safe file operations for MarkdownViewer."""
from ..appearance.icons import set_painted_icon
from ..readers.reader_chrome import ReaderIcon, reader_button
from ..appearance.formatting_icons import FormattingIcon
from pathlib import Path

from .. import pyside as qt
from .io import _encode_markdown, _write_markdown
from .extensions import mermaid_blocks


class MarkdownEditingMixin:
    """Internal implementation; use the public MarkdownViewer widget."""
    @property
    def is_modified(self):
        return self.editor.document().isModified() or self._rich_pending()

    def _modified_changed(self, modified):
        path = self._loaded_path if self._loaded_path is not None else self.current_path
        self.location.setText((str(path) if path else 'Untitled') + (' *' if modified else ''))
        if hasattr(self, 'document_title'):
            self.document_title.setText((path.name if path else 'Untitled') + (' *' if modified else ''))
        self.modified_changed.emit(modified)

    def _action(self, title, callback, standard=None, extra=()):
        action = qt.QAction(title, self)
        shortcuts = qt.QKeySequence.keyBindings(standard) if standard is not None else []
        unique = {sequence.toString(): sequence for sequence in shortcuts + [qt.QKeySequence(value) for value in extra]}
        action.setShortcuts(list(unique.values()))
        action.setShortcutContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        action.triggered.connect(lambda checked=False: callback())
        self.addAction(action)
        return action

    def _build_editor_actions(self, layout):
        key = qt.QKeySequence.StandardKey
        self.new_action = self._action('New', self.new_document, key.New, ('Ctrl+N',))
        self.open_action = self._action('Open…', self.open_dialog, key.Open, ('Ctrl+O',))
        self.save_action = self._action('Save', self.save_document, key.Save, ('Ctrl+S',))
        self.save_as_action = self._action('Save As…', self.save_as_dialog, key.SaveAs, ('Ctrl+Shift+S',))
        self.undo_action = self._action('Undo', lambda: self.active_editor().undo() if self.edit_button.isChecked() else None, key.Undo)
        self.redo_action = self._action('Redo', lambda: self.active_editor().redo() if self.edit_button.isChecked() else None, key.Redo)
        self.undo_action.setEnabled(False)
        self.redo_action.setEnabled(False)
        self.editor.undoAvailable.connect(lambda available: self._update_edit_actions())
        self.editor.redoAvailable.connect(lambda available: self._update_edit_actions())
        self.cut_action = self._action('Cut', lambda: self.active_editor().cut(), key.Cut)
        self.copy_action = self._action('Copy', lambda: (self.active_editor() if self.edit_button.isChecked() else self.browser).copy(), key.Copy)
        self.paste_action = self._action('Paste', lambda: self.active_editor().paste(), key.Paste)
        self.select_all_action = self._action('Select All', lambda: (self.active_editor() if self.edit_button.isChecked() else self.browser).selectAll(), key.SelectAll)
        self.find_action = self._action('Find / Replace in this page…' if self.allow_edit else 'Find in this page…', self.show_find, key.Find, ('Ctrl+F',))
        self.bold_action = self._action('Bold', lambda: self.wrap_selection('**', 'text'), key.Bold, ('Ctrl+B',))
        self.italic_action = self._action('Italic', lambda: self.wrap_selection('*', 'text'), key.Italic, ('Ctrl+I',))
        self.code_action = self._action('Inline code', lambda: self.wrap_selection('`', 'code'))
        self.link_action = self._action('Insert link', self.insert_link, extra=('Ctrl+K',))
        self.editor_toolbar = qt.QToolButton(self)
        self.editor_toolbar.setText('Format')
        set_painted_icon(self.editor_toolbar, FormattingIcon, 'format')
        self.editor_toolbar.setToolButtonStyle(qt.Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.editor_toolbar.setToolTip('Markdown formatting')
        self.editor_toolbar.setIconSize(qt.QSize(20, 20))
        self.editor_toolbar.setMinimumSize(32, 32)
        self.editor_toolbar.setAccessibleName('Markdown formatting')
        self.editor_toolbar.setPopupMode(qt.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.format_menu = qt.QMenu(self.editor_toolbar)
        self.editor_toolbar.setMenu(self.format_menu)
        for action in (self.undo_action, self.redo_action, self.bold_action, self.italic_action,
                       self.code_action, self.link_action):
            self.format_menu.addAction(action)
        for action, glyph in ((self.bold_action, 'bold'), (self.italic_action, 'italic'),
                              (self.undo_action, 'undo'), (self.redo_action, 'redo'),
                              (self.code_action, 'code'), (self.link_action, 'link')):
            set_painted_icon(action, FormattingIcon, glyph)
        menu = self.format_menu.addMenu('Heading')
        set_painted_icon(menu.menuAction(), FormattingIcon, 'heading')
        action = menu.addAction('Paragraph', lambda: self.prefix_lines(''))
        set_painted_icon(action, FormattingIcon, 'paragraph')
        for level in range(1, 7):
            action = menu.addAction(f'Heading {level}', lambda level=level: self.prefix_lines('#' * level + ' '))
            set_painted_icon(action, FormattingIcon, 'heading')
        action = self.format_menu.addAction('Bullet list', lambda: self.prefix_lines('- '))
        set_painted_icon(action, FormattingIcon, 'bullets')
        action = self.format_menu.addAction('Quote', lambda: self.prefix_lines('> '))
        set_painted_icon(action, FormattingIcon, 'quote')
        self._build_table_actions()
        self.format_buttons = {}
        self.navigation_toolbar.insertWidget(2, self.editor_toolbar)
        for index, (glyph, action) in enumerate((('bold', self.bold_action), ('italic', self.italic_action),
                                                ('undo', self.undo_action), ('redo', self.redo_action))):
            button = reader_button(self, action.text(), action=action)
            button.setToolButtonStyle(qt.Qt.ToolButtonStyle.ToolButtonIconOnly)
            self.navigation_toolbar.insertWidget(2 + index, button)
            self.format_buttons[glyph] = button
            button.hide()
        self.editor_toolbar.hide()
        self.find_bar = qt.QWidget()
        find_layout = qt.QVBoxLayout(self.find_bar)
        find_layout.setContentsMargins(0, 0, 0, 0)
        row = qt.QHBoxLayout()
        find_layout.addLayout(row)
        self.find_text = qt.QLineEdit()
        self.find_text.setPlaceholderText('Find in this page…')
        self.find_text.setAccessibleName('Find in this page')
        self.find_text.setClearButtonEnabled(True)
        row.addWidget(qt.QLabel('This page'))
        row.addWidget(self.find_text, 1)
        for title, glyph, callback in (('Previous match', 'previous', self.find_previous),
                                       ('Next match', 'next', self.find_next), ('Close search', 'close', self.close_find)):
            button = reader_button(self, title, icon=glyph)
            button.clicked.connect(lambda checked=False, callback=callback: callback())
            row.addWidget(button)
        self.replace_row = qt.QWidget()
        replace_layout = qt.QHBoxLayout(self.replace_row)
        replace_layout.setContentsMargins(0, 0, 0, 0)
        self.replace_text = qt.QLineEdit()
        self.replace_text.setPlaceholderText('Replace with')
        self.replace_text.setVisible(self.allow_edit)
        replace_layout.addWidget(self.replace_text, 1)
        for title, callback in (('Replace', self.replace_match), ('Replace all', self.replace_all)):
            button = qt.QPushButton(title)
            button.clicked.connect(lambda checked=False, callback=callback: callback())
            replace_layout.addWidget(button)
        find_layout.addWidget(self.replace_row)
        self.replace_row.hide()
        self.find_text.returnPressed.connect(self.find_next)
        self.find_count = qt.QLabel()
        self.find_count.setMinimumWidth(0)
        self.find_count.setAccessibleName('Page search matches')
        row.insertWidget(2, self.find_count)
        layout.insertWidget(0, self.find_bar)
        self.find_button = reader_button(self, 'Find in this page', icon='search')
        self.find_button.setToolTip('Find in this page (Ctrl+F / ⌘F)')
        self.find_button.clicked.connect(self.show_find)
        self.navigation_toolbar.addWidget(self.find_button)
        self.find_bar.hide()
        for action in (self.cut_action, self.paste_action, self.bold_action, self.italic_action, self.code_action, self.link_action):
            action.setEnabled(False)

        for action in (self.new_action, self.save_action, self.save_as_action,
                       self.undo_action, self.redo_action, self.cut_action, self.paste_action,
                       self.bold_action, self.italic_action, self.code_action, self.link_action):
            action.setVisible(self.allow_edit)
        for action in (self.new_action, self.save_action, self.save_as_action):
            action.setEnabled(self.allow_edit)

    def set_editing(self, enabled):
        if enabled and not self.allow_edit:
            self.edit_button.setChecked(False)
            return
        if self.edit_button.isChecked() != enabled:
            self.edit_button.setChecked(enabled)
            return
        self._sync_formatted()
        if enabled and self.edit_mode.currentData() == 'formatted':
            self._load_formatted()
        self.pages.setCurrentWidget(self.active_editor() if enabled else self.browser)
        self.diagrams_button.setVisible(not enabled and bool(mermaid_blocks(self.editor.toPlainText())))
        self.editor_toolbar.setVisible(enabled)
        for button in self.format_buttons.values():
            button.setVisible(enabled)
        self.properties_button.setVisible(enabled and self.allow_edit)
        self.appearance_button.setVisible(not enabled)
        self.speech.action.setVisible(not enabled)
        self.speech.anchor.setVisible(not enabled)
        for action in (self.text_larger_action, self.text_smaller_action, self.text_reset_action):
            action.setEnabled(not enabled)
        self.edit_mode.setVisible(enabled)
        self.replace_text.setEnabled(enabled)
        self.replace_row.setVisible(enabled and self.allow_edit)
        self.properties.set_editable(enabled and self.edit_mode.currentData() == "formatted")
        label = 'Read Markdown' if enabled else 'Edit Markdown'
        set_painted_icon(self.edit_button, ReaderIcon, 'read' if enabled else 'edit')
        self.edit_button.setText('Read' if enabled else 'Edit')
        self.edit_button.setAccessibleName(label)
        self.edit_button.setToolTip(label)
        self._update_edit_actions()
        if not enabled:
            self._render_source(self.markdown_text())
        elif self.edit_mode.currentData() == 'formatted':
            self.status.setText('Formatted edits normalize Markdown syntax. Source mode retains precise syntax.')
        (self.active_editor() if enabled else self.browser).setFocus()

    def _confirm_leave(self):
        if not self.is_modified:
            return True
        buttons = qt.QMessageBox.StandardButton
        answer = qt.QMessageBox.warning(self, 'Unsaved Markdown',
                                       'Save your changes before leaving this document?',
                                       buttons.Save | buttons.Discard | buttons.Cancel, buttons.Save)
        if answer == buttons.Save:
            return self.save_document()
        return answer == buttons.Discard

    def new_document(self):
        """Start an untitled document after resolving unsaved changes."""
        if not self.allow_edit or not self._confirm_leave():
            return False
        self.history.clear()
        self.history_index = -1
        self._loaded_path = None
        self._source_bytes = None
        self._rich_snapshot = None
        self._rich_source = None
        self.editor.clear()
        self.editor.document().setModified(False)
        self.location.setText('Untitled')
        self.status.clear()
        self._render_source('', preserve_selection=False)
        self._update_buttons()
        self.set_editing(True)
        self.path_changed.emit(None)
        return True

    def can_close(self):
        """Resolve unsaved changes; embedding applications call this before closing."""
        return self._confirm_leave()

    def open_dialog(self):
        if self.storage is not None and callable(getattr(self.storage, 'open_dialog', None)):
            return self.storage.open_dialog(self)
        action = getattr(qt.QApplication.instance(), '_commonutils_markdown_resource_action', None)
        if action:
            return action(self, 'open')
        path, _ = qt.QFileDialog.getOpenFileName(self, 'Open Markdown',
                                               str(self.current_path.parent) if self.current_path else '',
                                               'Markdown (*.md *.markdown);;All files (*)')
        if path:
            return self.open_document(path)
        return False

    def save_as_dialog(self):
        if not self.allow_edit:
            return False
        if self.storage is not None and hasattr(self.storage, 'save_as'):
            return self.storage.save_as(self)
        action = getattr(qt.QApplication.instance(), '_commonutils_markdown_resource_action', None)
        if action:
            return action(self, 'save')
        path, _ = qt.QFileDialog.getSaveFileName(self, 'Save Markdown As',
                                               str(self.current_path) if self.current_path else 'document.md',
                                               'Markdown (*.md *.markdown)')
        return self.save_document(path) if path else False

    def capture_save(self):
        """Return a lossless byte snapshot of the current draft for a storage host."""
        return _encode_markdown(self.markdown_text(), self._source_bytes, self.is_modified)

    def begin_save(self):
        """Reserve an asynchronous save; False means a save is already pending."""
        if not self.allow_edit or getattr(self, '_save_pending', False):
            return False
        self._save_pending = True
        return True

    def complete_save(self, destination, data, error=None):
        """Accept a published snapshot or retain the draft on failure."""
        self._save_pending = False
        if error:
            self.status.setText(f'Cannot save {destination}: {error}')
            return False
        return self._finish_save(Path(destination), data)

    def save_document(self, path=None):
        if not self.allow_edit or getattr(self, '_save_pending', False):
            return False
        destination = Path(path).expanduser().absolute() if path is not None else self.current_path
        if destination is None:
            return self.save_as_dialog()
        try:
            data = self.capture_save()
            expected = self._source_bytes if destination == self._loaded_path else None
            if self.storage is not None and hasattr(self.storage, 'submit_write'):
                self._save_pending = True
                self.status.setText('Saving locally…')
                def completed(error):
                    self._save_pending = False
                    if error:
                        self.status.setText(f'Cannot save {destination}: {error}')
                    else:
                        self._finish_save(destination, data)
                self.storage.submit_write(destination, data, expected, completed)
                return False  # A close request waits for the host's completion.
            if self.storage is not None:
                self.storage.write_bytes(destination, data, expected=expected)
            else:
                _write_markdown(destination, data, expected=expected)
        except (OSError, UnicodeError, ValueError) as error:
            self._save_pending = False
            self.status.setText(f'Cannot save {destination}: {error}')
            return False
        return self._finish_save(destination, data)

    def _finish_save(self, destination, data):
        self._source_bytes = data
        self._loaded_path = destination
        self.formatted_editor.document().setBaseUrl(qt.QUrl.fromLocalFile(str(destination.parent) + '/'))
        if self.history_index < 0:
            self.history.append({'url': qt.QUrl.fromLocalFile(str(destination)), 'scroll': 0})
            self.history_index = 0
        elif destination != self.current_path:
            self.history[self.history_index]['url'] = qt.QUrl.fromLocalFile(str(destination))
        self.editor.document().setModified(False)
        self.formatted_editor.document().setModified(False)
        self._render_source(self.markdown_text())
        self._modified_changed(False)
        self.location.setText(str(destination))
        self.document_title.setText(destination.name)
        self.status.setText('Saved.')
        self._update_buttons()
        self.path_changed.emit(destination)
        return True

    def wrap_selection(self, marker, placeholder):
        if not self.edit_button.isChecked():
            return
        cursor = self.active_editor().textCursor()
        if self.active_editor() is self.formatted_editor:
            self.format_inline(marker)
            return
        text = cursor.selectedText().replace('\u2029', '\n') or placeholder
        cursor.insertText(marker + text + marker)
        self.active_editor().setTextCursor(cursor)
        self.active_editor().setFocus()

    def prefix_lines(self, prefix):
        if not self.edit_button.isChecked():
            return
        if self.active_editor() is self.formatted_editor:
            self.format_blocks(prefix)
            return
        cursor = self.active_editor().textCursor()
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        cursor.setPosition(start)
        cursor.movePosition(qt.QTextCursor.MoveOperation.StartOfBlock)
        start = cursor.position()
        cursor.setPosition(end)
        if end > start and cursor.atBlockStart():
            cursor.movePosition(qt.QTextCursor.MoveOperation.PreviousCharacter)
        cursor.movePosition(qt.QTextCursor.MoveOperation.EndOfBlock)
        cursor.setPosition(start, qt.QTextCursor.MoveMode.KeepAnchor)
        lines = cursor.selectedText().split('\u2029')
        if not prefix:
            import re
            lines = [re.sub(r'^\s{0,3}#{1,6}\s+', '', line) for line in lines]
        cursor.insertText('\n'.join(prefix + line for line in lines))
        self.active_editor().setTextCursor(cursor)
        self.active_editor().setFocus()

    def insert_link(self):
        if not self.edit_button.isChecked():
            return
        url, accepted = qt.QInputDialog.getText(self, 'Insert link', 'URL or relative Markdown path:')
        if accepted and url:
            if self.active_editor() is self.formatted_editor:
                self.format_link(url)
                return
            cursor = self.active_editor().textCursor()
            label = cursor.selectedText() or 'link text'
            cursor.insertText(f'[{label}]({url})')
            self.active_editor().setTextCursor(cursor)

    def show_find(self):
        self.find_bar.show()
        self.replace_text.setEnabled(self.edit_button.isChecked())
        self.replace_row.setVisible(self.edit_button.isChecked() and self.allow_edit)
        self.find_text.setFocus()
        self.find_text.selectAll()
        self._refresh_search_highlights()

    def close_find(self):
        self.find_bar.hide()
        self._clear_search_selection('page')
        self._refresh_search_highlights()

    def find_previous(self):
        return self.find_next(backward=True)

    def find_next(self, backward=False):
        target = self.active_editor() if self.edit_button.isChecked() else self.browser
        if not self.find_text.text():
            return False
        flags = qt.QTextDocument.FindFlag.FindBackward if backward else qt.QTextDocument.FindFlag(0)
        original = target.textCursor()
        if target.find(self.find_text.text(), flags):
            self._select_search_match(target, target.textCursor(), 'page')
            return True
        target.moveCursor(qt.QTextCursor.MoveOperation.End if backward else qt.QTextCursor.MoveOperation.Start)
        if target.find(self.find_text.text(), flags):
            self._select_search_match(target, target.textCursor(), 'page')
            return True
        target.setTextCursor(original)
        return False

    def replace_match(self):
        if not self.edit_button.isChecked() or not self.find_text.text():
            return
        cursor = self.active_editor().textCursor()
        if cursor.selectedText().casefold() != self.find_text.text().casefold() and not self.find_next():
            return
        cursor = self.active_editor().textCursor()
        cursor.insertText(self.replace_text.text())
        self.active_editor().setTextCursor(cursor)
        self.find_next()

    def replace_all(self):
        if not self.edit_button.isChecked() or not self.find_text.text():
            return
        cursor = self.active_editor().textCursor()
        cursor.beginEditBlock()
        cursor.movePosition(qt.QTextCursor.MoveOperation.Start)
        count = 0
        while True:
            match = self.active_editor().document().find(self.find_text.text(), cursor)
            if match.isNull():
                break
            match.insertText(self.replace_text.text())
            cursor = match
            count += 1
        cursor.endEditBlock()
        self.status.setText(f'Replaced {count} matches.')
