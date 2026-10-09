"""Reusable Markdown reading/editing, heading navigation and document history."""
from pathlib import Path

from .. import pyside as qt
from ..reader_chrome import READER_MARGINS, READER_SPACING, ReaderLabel, ReaderFullscreen, reader_button
from .editing import MarkdownEditingMixin
from .formatted import MarkdownFormattedMixin
from .properties import MarkdownProperties
from .headings import _iter_headings
from .presentation import MarkdownBrowser, configure_text
from .reading import MarkdownReadingMixin
from .links import render_links
from .tables import MarkdownTablesMixin
from .live_edit import SourceMarkdownEdit, FormattedMarkdownEdit
from ...markdownUtils import split_frontmatter


class MarkdownViewer(MarkdownReadingMixin, MarkdownFormattedMixin, MarkdownEditingMixin, MarkdownTablesMixin, qt.QWidget):
    """Preview-only by default; allow_edit=True enables optional Markdown editing."""
    path_changed = qt.Signal(object)
    modified_changed = qt.Signal(bool)

    def __init__(self, path=None, parent=None, *, allow_edit=False):
        super().__init__(parent)
        self.allow_edit = bool(allow_edit)
        self.history = []
        self.history_index = -1
        self._source_bytes = None
        self._loaded_path = None
        self.headings = []
        self.toc_popup = None
        self._rich_snapshot = None
        self._rich_source = None
        self._folded_callouts = {}
        self._callouts = {}
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(*READER_MARGINS)
        layout.setSpacing(READER_SPACING)
        toolbar = qt.QHBoxLayout()
        toolbar.setSpacing(READER_SPACING)
        self.back_button = reader_button(self, 'Back', icon='previous')
        self.forward_button = reader_button(self, 'Forward', icon='next')
        self.back_button.setToolTip('Previous document or heading (Alt+Left)')
        self.forward_button.setToolTip('Next document or heading (Alt+Right)')
        self.location = qt.QLabel(self)
        self.location.hide()
        self.location.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.location.setTextInteractionFlags(qt.Qt.TextInteractionFlag.TextSelectableByMouse)
        toolbar.addWidget(self.back_button)
        toolbar.addWidget(self.forward_button)
        self.document_title = ReaderLabel('Markdown')
        self.document_title.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        toolbar.addWidget(self.document_title, 1)
        self.edit_button = qt.QPushButton('Edit')
        self.edit_button.setCheckable(True)
        self.edit_button.setToolTip('Switch between reading and editing Markdown')
        self.edit_button.toggled.connect(self.set_editing)
        self.edit_button.setVisible(self.allow_edit)
        self.edit_button.setEnabled(self.allow_edit)
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
        self.browser = MarkdownBrowser()
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        self.browser.setAccessibleName('Markdown document')
        self.browser.anchorClicked.connect(self.follow_link)
        self.editor = SourceMarkdownEdit()
        self.editor.setReadOnly(not self.allow_edit)
        self.editor.setAccessibleName('Markdown source')
        self.editor.setFont(qt.QFontDatabase.systemFont(qt.QFontDatabase.SystemFont.FixedFont))
        self.editor.document().modificationChanged.connect(self._modified_changed)
        self.formatted_editor = FormattedMarkdownEdit()
        for widget in (self.browser, self.formatted_editor):
            configure_text(widget)
        configure_text(self.editor, source=True)
        self.formatted_editor.linkActivated.connect(self.follow_link)
        self.formatted_editor.setReadOnly(not self.allow_edit)
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
        self.properties_button = qt.QToolButton(self)
        self.properties_button.setText('…')
        self.properties_button.setAccessibleName('Markdown document options')
        self.properties_button.setToolTip('Document properties')
        self.properties_button.setPopupMode(qt.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.properties_menu = qt.QMenu(self.properties_button)
        self.add_property_action = self.properties_menu.addAction('Add YAML property…', lambda: self.properties.edit_property())
        self.edit_yaml_action = self.properties_menu.addAction('Edit YAML…', self.properties.edit_yaml)
        self.properties_button.setMenu(self.properties_menu)
        self.properties_button.setVisible(self.allow_edit)
        self.add_property_action.setEnabled(False)
        self.edit_yaml_action.setEnabled(False)
        self.properties.editable_changed.connect(self.add_property_action.setEnabled)
        self.properties.editable_changed.connect(self.edit_yaml_action.setEnabled)
        toolbar.addWidget(self.properties_button)
        self._properties_timer = qt.QTimer(self)
        self._properties_timer.setSingleShot(True)
        self._properties_timer.setInterval(200)
        self._properties_timer.timeout.connect(lambda: self.properties.refresh(self.editor.toPlainText()))
        self.editor.textChanged.connect(lambda: self._properties_timer.start())
        self._build_editor_actions(layout)
        self.diagrams_button = reader_button(self, 'Render Mermaid diagrams', text='Diagrams')
        self.diagrams_button.clicked.connect(self.render_diagrams)
        self.diagrams_button.hide()
        toolbar.addWidget(self.diagrams_button)
        self._build_reading_appearance(toolbar)
        from ..read_aloud import ReadAloud, reader_text
        self.speech = ReadAloud(self, lambda: reader_text(self.browser))
        toolbar.addWidget(reader_button(self, 'Read aloud', action=self.speech.action, text='Read aloud'))
        self.browser.textChanged.connect(self.speech.stop)
        self.edit_button.toggled.connect(self.speech.stop)
        self.edit_button.toggled.connect(lambda editing: self.speech.action.setEnabled(not editing))
        self.fullscreen_action = self._action('Full screen', lambda: self.fullscreen.toggle(), extra=('F11',))
        self.fullscreen_action.setCheckable(True)
        self.fullscreen = ReaderFullscreen(self, self.fullscreen_action)
        toolbar.addWidget(reader_button(self, 'Full screen', action=self.fullscreen_action, icon='fullscreen'))
        self.escape_shortcut = qt.QShortcut(qt.QKeySequence('Escape'), self)
        self.escape_shortcut.setContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.escape_shortcut.activated.connect(self._escape)
        self.status = ReaderLabel('', muted=True)
        layout.addWidget(self.status)
        self.back_button.clicked.connect(self.back)
        self.forward_button.clicked.connect(self.forward)
        self.back_shortcut = qt.QShortcut(qt.QKeySequence('Alt+Left'), self)
        self.forward_shortcut = qt.QShortcut(qt.QKeySequence('Alt+Right'), self)
        for shortcut, callback in ((self.back_shortcut, self.back), (self.forward_shortcut, self.forward)):
            shortcut.setContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(callback)
        self._update_buttons()
        self._diagram_renderer = None
        self._reading_palette_timer = qt.QTimer(self)
        self._reading_palette_timer.setSingleShot(True)
        self._reading_palette_timer.setInterval(0)
        self._reading_palette_timer.timeout.connect(lambda: self._render_source(self.editor.toPlainText()))
        self.browser.installEventFilter(self)
        if path is not None:
            self.open_document(path)
        if self.allow_edit:
            error = self.status.text()
            self.set_editing(True)
            if error:
                self.status.setText(error)

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
        if path != self._loaded_path:
            self._folded_callouts.clear()
        self._loaded_path = path
        self.document_title.setText(path.name)
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

    def _apply_properties(self, updated):
        if not self.allow_edit:
            return
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
        if url.scheme() == 'callout':
            try:
                callout = self._callouts[int(url.path())]
            except (KeyError, ValueError):
                return
            if callout.foldable:
                self._folded_callouts[callout.key] = not callout.collapsed
                self._render_source(self.markdown_text())
            return
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

    def _escape(self):
        if self.toc_popup is not None and self.toc_popup.isVisible():
            self.toc_popup.close()
        elif self.appearance_popup is not None and self.appearance_popup.isVisible():
            self.appearance_popup.close()
        elif self.find_bar.isVisible():
            self.find_bar.hide()
            (self.active_editor() if self.edit_button.isChecked() else self.browser).setFocus()
        else:
            self.fullscreen.leave()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == qt.QEvent.Type.PaletteChange and hasattr(self, '_reading_palette_timer'):
            # Restyle the preview only: palette changes never dirty an editor or
            # replace an undo stack. Rich editing keeps its imported styles;
            # reopening a document adopts the current palette.
            self._reading_palette_timer.start()

    def eventFilter(self, watched, event):
        if watched is self.browser and event.type() == qt.QEvent.Type.PaletteChange:
            # Application palette and stylesheet updates arrive separately.
            # Wait for the child text widget's final palette before importing.
            self._reading_palette_timer.start()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_diagram_renderer'):
            self._fit_diagrams()

    def closeEvent(self, event):
        self.speech.stop()
        if self._diagram_renderer:
            self._diagram_renderer.cancel()
        super().closeEvent(event)
