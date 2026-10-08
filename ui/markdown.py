"""Reusable Markdown reading/editing, heading navigation and document history."""
from pathlib import Path

from . import pyside as qt
from .file_browser.controls import navigation_button
from .markdown_editing import MarkdownEditingMixin
from .markdown_formatted import MarkdownFormattedMixin
from .markdown_properties import MarkdownProperties
from .markdown_headings import _iter_headings
from ..markdownUtils import split_frontmatter


class MarkdownViewer(MarkdownFormattedMixin, MarkdownEditingMixin, qt.QWidget):
    """Embeddable Markdown viewer/editor; opens read-only and protects unsaved edits."""
    path_changed = qt.Signal(object)
    modified_changed = qt.Signal(bool)

    def __init__(self, path=None, parent=None):
        super().__init__(parent)
        self.history = []
        self.history_index = -1
        self._source_bytes = None
        self._loaded_path = None
        self.headings = []
        self.toc_popup = None
        self._rich_snapshot = None
        self._rich_source = None
        layout = qt.QVBoxLayout(self)
        toolbar = qt.QHBoxLayout()
        self.back_button = navigation_button(self, 'Back', qt.QStyle.StandardPixmap.SP_ArrowBack)
        self.forward_button = navigation_button(self, 'Forward', qt.QStyle.StandardPixmap.SP_ArrowForward)
        self.back_button.setToolTip('Previous document or heading (Alt+Left)')
        self.forward_button.setToolTip('Next document or heading (Alt+Right)')
        self.location = qt.QLabel(self)
        self.location.hide()
        self.location.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.location.setTextInteractionFlags(qt.Qt.TextInteractionFlag.TextSelectableByMouse)
        toolbar.addWidget(self.back_button)
        toolbar.addWidget(self.forward_button)
        toolbar.addStretch(1)
        self.edit_button = qt.QPushButton('Edit')
        self.edit_button.setCheckable(True)
        self.edit_button.setToolTip('Switch between reading and editing Markdown')
        self.edit_button.toggled.connect(self.set_editing)
        toolbar.addWidget(self.edit_button)
        self.edit_mode = qt.QComboBox()
        self.edit_mode.addItem('Formatted', 'formatted')
        self.edit_mode.addItem('Source', 'source')
        self.edit_mode.setAccessibleName('Markdown editing mode')
        self.edit_mode.setToolTip('Edit the formatted document or its Markdown source')
        self.edit_mode.currentIndexChanged.connect(self._change_edit_mode)
        self.edit_mode.hide()
        toolbar.addWidget(self.edit_mode)
        self.toc_button = qt.QPushButton('Contents')
        self.toc_button.setToolTip('Jump to a heading')
        self.toc_button.clicked.connect(self.show_contents)
        toolbar.addWidget(self.toc_button)
        layout.addLayout(toolbar)
        self.browser = qt.QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        self.browser.setAccessibleName('Markdown document')
        self.browser.anchorClicked.connect(self.follow_link)
        self.editor = qt.QPlainTextEdit()
        self.editor.setAccessibleName('Markdown source')
        self.editor.setFont(qt.QFontDatabase.systemFont(qt.QFontDatabase.SystemFont.FixedFont))
        self.editor.document().modificationChanged.connect(self._modified_changed)
        self.formatted_editor = qt.QTextEdit()
        self.formatted_editor.setAccessibleName('Formatted Markdown editor')
        self.formatted_editor.document().contentsChanged.connect(self._formatted_changed)
        self.formatted_editor.undoAvailable.connect(lambda available: self._update_edit_actions())
        self.formatted_editor.redoAvailable.connect(lambda available: self._update_edit_actions())
        self.pages = qt.QStackedWidget()
        self.pages.addWidget(self.browser)
        self.pages.addWidget(self.editor)
        self.pages.addWidget(self.formatted_editor)
        layout.addWidget(self.pages, 1)
        self.properties = MarkdownProperties(self)
        self.properties.changed.connect(self._apply_properties)
        layout.insertWidget(1, self.properties)
        self.properties.hide()
        self._properties_timer = qt.QTimer(self)
        self._properties_timer.setSingleShot(True)
        self._properties_timer.setInterval(200)
        self._properties_timer.timeout.connect(lambda: self.properties.refresh(self.editor.toPlainText()))
        self.editor.textChanged.connect(lambda: self._properties_timer.start())
        self._build_editor_actions(layout)
        self.status = qt.QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(qt.Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.back_button.clicked.connect(self.back)
        self.forward_button.clicked.connect(self.forward)
        self.back_shortcut = qt.QShortcut(qt.QKeySequence('Alt+Left'), self)
        self.forward_shortcut = qt.QShortcut(qt.QKeySequence('Alt+Right'), self)
        for shortcut, callback in ((self.back_shortcut, self.back), (self.forward_shortcut, self.forward)):
            shortcut.setContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(callback)
        self._update_buttons()
        if path is not None:
            self.open_document(path)

    def show_contents(self):
        self._render_source(self.markdown_text())
        if self.toc_popup is not None:
            self.toc_popup.close()
            self.toc_popup.deleteLater()
        self.toc_popup = qt.QFrame(self, qt.Qt.WindowType.Popup)
        self.toc_popup.setFrameShape(qt.QFrame.Shape.StyledPanel)
        self.toc_popup.setAccessibleName('Markdown table of contents')
        layout = qt.QVBoxLayout(self.toc_popup)
        layout.addWidget(qt.QLabel('Table of contents'))
        listing = qt.QListWidget()
        listing.setAccessibleName('Document headings')
        for level, title, anchor in self.headings:
            item = qt.QListWidgetItem('    ' * (level - 1) + title)
            item.setData(qt.Qt.ItemDataRole.UserRole, anchor)
            listing.addItem(item)
        if not self.headings:
            layout.addWidget(qt.QLabel('This document has no headings.'))
        layout.addWidget(listing)
        listing.itemClicked.connect(self._select_heading)
        listing.itemActivated.connect(self._select_heading)
        self.toc_popup.resize(min(380, self.width()), min(420, max(140, self.height())))
        point = self.toc_button.mapToGlobal(qt.QPoint(self.toc_button.width(), self.toc_button.height()))
        screen = self.toc_button.screen().availableGeometry()
        x = max(screen.left(), min(point.x() - self.toc_popup.width(), screen.right() - self.toc_popup.width() + 1))
        y = max(screen.top(), min(point.y(), screen.bottom() - self.toc_popup.height() + 1))
        self.toc_popup.move(x, y)
        self.toc_popup.show()
        listing.setFocus()

    def _select_heading(self, item):
        anchor = item.data(qt.Qt.ItemDataRole.UserRole)
        self.toc_popup.close()
        # Heading navigation never reloads the file or discards unsaved source.
        if self.edit_button.isChecked() and self.active_editor() is self.formatted_editor:
            self._scroll_formatted_heading(anchor)
            return
        if self.edit_button.isChecked():
            self.set_editing(False)
        if self.current_path is not None:
            url = qt.QUrl()
            url.setFragment(anchor)
            self.follow_link(url)
        else:
            self.browser.scrollToAnchor(anchor)
        self.browser.setFocus()

    @property
    def current_path(self):
        return Path(self.history[self.history_index]['url'].toLocalFile()) if self.history_index >= 0 else None

    def _update_buttons(self):
        self.back_button.setEnabled(self.history_index > 0)
        self.forward_button.setEnabled(0 <= self.history_index < len(self.history) - 1)

    def _remember_scroll(self):
        if self.history_index >= 0:
            self.history[self.history_index]['scroll'] = self.browser.verticalScrollBar().value()

    def _render(self, url, scroll=None):
        path = Path(url.toLocalFile())
        try:
            if path.suffix.lower() not in ('.md', '.markdown'):
                raise ValueError('This viewer opens Markdown (.md or .markdown) files.')
            data = path.read_bytes()
            text = data.decode('utf-8-sig')
        except (OSError, UnicodeError, ValueError) as error:
            self.status.setText(f'Cannot open {path}: {error}')
            return False
        self._source_bytes = data
        self._loaded_path = path
        self.editor.setPlainText(text)
        self.editor.document().setModified(False)
        self._rich_source = None
        self._rich_snapshot = None
        if self.edit_button.isChecked() and self.edit_mode.currentData() == "formatted":
            self._load_formatted()
        self._render_source(text)
        self.location.setText(str(path))
        self.status.clear()
        if scroll is not None:
            self.browser.verticalScrollBar().setValue(scroll)
        elif url.fragment():
            self.browser.scrollToAnchor(url.fragment())
        else:
            self.browser.verticalScrollBar().setValue(0)
        return True

    def _render_source(self, text):
        scroll = self.browser.verticalScrollBar().value()
        self.browser.document().setBaseUrl(qt.QUrl.fromLocalFile(str(self._loaded_path.parent) + '/')
                                         if self._loaded_path else qt.QUrl())
        self.properties.refresh(text)
        parts = split_frontmatter(text)
        self.browser.setMarkdown(parts.body)
        # Qt renders headings but does not supply GitHub-style fragment names.
        self.headings = []
        for level, title, anchor, block in _iter_headings(self.browser.document()):
            self.headings.append((level, title, anchor))
            cursor = qt.QTextCursor(block)
            cursor.movePosition(qt.QTextCursor.MoveOperation.NextCharacter, qt.QTextCursor.MoveMode.KeepAnchor)
            fmt = qt.QTextCharFormat()
            fmt.setAnchor(True)
            fmt.setAnchorNames([anchor])
            cursor.mergeCharFormat(fmt)
        self.browser.verticalScrollBar().setValue(scroll)

    def _apply_properties(self, updated):
        # Property edits must not replace an unsynchronized, freshly edited body.
        current = self.markdown_text()
        prefix = split_frontmatter(updated).prefix
        body = split_frontmatter(current).body
        text = prefix + body
        if text == current:
            return
        self._replace_source_text(text)
        self._render_source(text)
        if self.edit_button.isChecked() and self.active_editor() is self.formatted_editor:
            self._load_formatted()
        self._modified_changed(True)

    def open_document(self, path, *, fragment=''):
        if not self._confirm_leave():
            return False
        try:
            url = qt.QUrl.fromLocalFile(str(Path(path).expanduser().resolve()))
            url.setFragment(fragment)
        except (OSError, RuntimeError, ValueError) as error:
            self.status.setText(f'Cannot open {path}: {error}')
            return False
        self._remember_scroll()
        if not self._render(url):
            return False
        del self.history[self.history_index + 1:]
        self.history.append({'url': url, 'scroll': self.browser.verticalScrollBar().value()})
        self.history_index = len(self.history) - 1
        self._update_buttons()
        self._update_edit_actions()
        self.path_changed.emit(self.current_path)
        return True

    def follow_link(self, link):
        url = qt.QUrl(link)
        if url.scheme().lower() in ('https', 'http', 'mailto'):
            if not qt.QDesktopServices.openUrl(url):
                self.status.setText('Could not open the link in your default application.')
            return
        if self.current_path is None:
            return
        base = qt.QUrl.fromLocalFile(str(self.current_path))
        url = base.resolved(url)
        if not url.isLocalFile():
            self.status.setText(f'Unsupported link: {url.toString()}')
            return
        if Path(url.toLocalFile()) == self.current_path:
            self._remember_scroll()
            self._render_source(self.markdown_text())
            self.browser.scrollToAnchor(url.fragment())
            del self.history[self.history_index + 1:]
            self.history.append({'url': url, 'scroll': self.browser.verticalScrollBar().value()})
            self.history_index = len(self.history) - 1
            self._update_buttons()
            self.path_changed.emit(self.current_path)
        else:
            self.open_document(url.toLocalFile(), fragment=url.fragment())

    def _navigate_history(self, offset):
        index = self.history_index + offset
        if not 0 <= index < len(self.history):
            return
        entry = self.history[index]
        same_document = Path(entry['url'].toLocalFile()) == self.current_path
        if not same_document and not self._confirm_leave():
            return
        self._remember_scroll()
        if same_document:
            self._render_source(self.markdown_text())
            self.browser.verticalScrollBar().setValue(entry['scroll'])
        if same_document or self._render(entry['url'], entry['scroll']):
            self.history_index = index
            self._update_buttons()
            self.path_changed.emit(self.current_path)

    def back(self):
        self._navigate_history(-1)

    def forward(self):
        self._navigate_history(1)


class MarkdownWindow(qt.QMainWindow):
    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.viewer = MarkdownViewer(parent=self)
        self.setCentralWidget(self.viewer)
        self.viewer.path_changed.connect(lambda path: self._update_title())
        self.viewer.modified_changed.connect(lambda modified: self._update_title())
        file_menu = self.menuBar().addMenu('File')
        for action in (self.viewer.new_action, self.viewer.open_action, self.viewer.save_action, self.viewer.save_as_action):
            file_menu.addAction(action)
        file_menu.addSeparator()
        file_menu.addAction('Close', self.close, qt.QKeySequence(qt.QKeySequence.StandardKey.Close))
        edit_menu = self.menuBar().addMenu('Edit')
        for action in (self.viewer.undo_action, self.viewer.redo_action, self.viewer.cut_action,
                       self.viewer.copy_action, self.viewer.paste_action, self.viewer.select_all_action,
                       self.viewer.find_action):
            edit_menu.addAction(action)
        view_menu = self.menuBar().addMenu('View')
        view_menu.addAction('Edit / Read', self.viewer.edit_button.click)
        view_menu.addAction('Table of contents', self.viewer.show_contents)
        self.setWindowTitle('Documentation')
        self.resize(900, 700)
        self.viewer.open_document(path)

    def _update_title(self):
        path = self.viewer.current_path
        title = path.name if path else 'Markdown'
        self.setWindowTitle(f'{title}{" *" if self.viewer.is_modified else ""} — Markdown')

    def closeEvent(self, event):
        if self.viewer.can_close():
            super().closeEvent(event)
        else:
            event.ignore()


_windows = set()


def open_markdown(path, *, parent=None):
    """Show and retain an independent viewer window until it closes; requires Qt app."""
    window = MarkdownWindow(path, parent)
    _windows.add(window)
    window.destroyed.connect(lambda: _windows.discard(window))
    window.show()
    return window
