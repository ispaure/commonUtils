"""Reading presentation and optional diagrams, independent of editing/IO."""
from .. import pyside as qt
from ...markdownUtils import split_frontmatter
from .extensions import reading_source, mermaid_blocks
from .headings import _iter_headings
from .links import render_links
from .presentation import style_document
from ..reader_chrome import reader_button, reading_spin, show_reader_popup


class MarkdownReadingMixin:
    def _build_reading_appearance(self, toolbar):
        self.appearance_popup = None
        self.reading_size = 13
        self.appearance_button = reader_button(self, 'Reading appearance', icon='appearance')
        self.appearance_button.clicked.connect(self.show_reading_appearance)
        toolbar.addWidget(self.appearance_button)
        key = qt.QKeySequence.StandardKey
        self.text_larger_action = self._action('Larger text', lambda: self.set_reading_size(self.reading_size + 1), key.ZoomIn)
        self.text_smaller_action = self._action('Smaller text', lambda: self.set_reading_size(self.reading_size - 1), key.ZoomOut)
        self.text_reset_action = self._action('Reset text size', lambda: self.set_reading_size(13))

    def set_reading_size(self, size):
        self.reading_size = max(10, min(24, int(size)))
        font = self.browser.font()
        font.setPointSizeF(self.reading_size)
        self.browser.setFont(font)
        self._render_source(self.markdown_text())

    def show_reading_appearance(self):
        if self.appearance_popup is not None:
            self.appearance_popup.close()
            self.appearance_popup.deleteLater()
        popup = self.appearance_popup = qt.QFrame(self, qt.Qt.WindowType.Popup)
        popup.setFrameShape(qt.QFrame.Shape.StyledPanel)
        popup.setAccessibleName('Markdown reading appearance')
        layout = qt.QVBoxLayout(popup)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(qt.QLabel('Reading appearance'))
        form = qt.QFormLayout()
        spin = reading_spin(popup, minimum=10, maximum=24, value=self.reading_size,
                            label='Reading text size', suffix=' pt', changed=self.set_reading_size)
        form.addRow('Text size', spin)
        layout.addLayout(form)
        hint = qt.QLabel('Reading follows the application’s light/dark theme.')
        hint.setWordWrap(True)
        hint.setForegroundRole(qt.QPalette.ColorRole.PlaceholderText)
        layout.addWidget(hint)
        popup.resize(300, popup.sizeHint().height())
        show_reader_popup(popup, self.appearance_button, align_right=True)
        spin.setFocus()

    def _render_source(self, text):
        scroll = self.browser.verticalScrollBar().value()
        previous_cursor = self.browser.textCursor()
        cursor_position, cursor_anchor = previous_cursor.position(), previous_cursor.anchor()
        self.browser.document().setBaseUrl(qt.QUrl.fromLocalFile(str(self._loaded_path.parent) + '/')
                                         if self._loaded_path else qt.QUrl())
        self.properties.refresh(text)
        parts = split_frontmatter(text)
        # Qt's HTML-block importer can silently discard everything after a div.
        # Treat embedded HTML as literal Markdown rather than losing authored text.
        body = self._diagram_renderer.substitute(parts.body, self.browser.document()) if self._diagram_renderer else parts.body
        rendered, callouts = reading_source(body, self._folded_callouts)
        self.browser.document().setMarkdown(render_links(rendered),
            qt.QTextDocument.MarkdownFeature.MarkdownDialectGitHub | qt.QTextDocument.MarkdownFeature.MarkdownNoHTML)
        style_document(self.browser.document(), self.browser.palette(), callouts=callouts)
        self._callouts = callouts
        self.diagrams_button.setVisible(bool(mermaid_blocks(parts.body)) and not self.edit_button.isChecked())
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
        # Force lazy layout to settle before QTextEdit restores its scrollbar.
        self._fit_diagrams()
        cursor = qt.QTextCursor(self.browser.document())
        maximum = self.browser.document().characterCount() - 1
        cursor.setPosition(min(cursor_anchor, maximum))
        cursor.setPosition(min(cursor_position, maximum), qt.QTextCursor.MoveMode.KeepAnchor)
        self.browser.setTextCursor(cursor)
        self.browser.document().documentLayout().documentSize()
        self.browser.verticalScrollBar().setValue(scroll)


    def render_diagrams(self):
        from .diagrams import MermaidRenderer
        if self._diagram_renderer is None:
            self._diagram_renderer = MermaidRenderer(self)
        self._diagram_renderer.render()


    def _fit_diagrams(self):
        if self._diagram_renderer is None or not self._diagram_renderer.images:
            return
        block = self.browser.document().begin()
        width = max(120, self.browser.viewport().width() - 60)
        while block.isValid():
            fragment = block.begin()
            while not fragment.atEnd():
                item = fragment.fragment()
                if item.isValid() and item.charFormat().isImageFormat():
                    fmt = item.charFormat().toImageFormat()
                    if fmt.name().startswith('mermaid:') and self._diagram_renderer:
                        image = self._diagram_renderer.images.get(fmt.name().split(':')[1])
                        if image is not None:
                            displayed = min(width, image.width())
                            fmt.setWidth(displayed)
                            fmt.setHeight(displayed * image.height() / image.width())
                            cursor = qt.QTextCursor(self.browser.document())
                            cursor.setPosition(item.position())
                            cursor.setPosition(item.position() + item.length(), qt.QTextCursor.MoveMode.KeepAnchor)
                            cursor.setCharFormat(fmt)
                fragment += 1
            block = block.next()
