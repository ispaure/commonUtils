"""Pointer-bound local-file snippets for Markdown reading mode."""
from pathlib import Path
from shiboken6 import isValid

from .. import pyside as qt
from ...filesystem.local_access import check_local_path
from ...formats.markdown.wiki import resolve_document_path
from ...persistence.text import likely_binary
from ...formats.markdown import split_frontmatter
from .extensions import reading_source
from .links import render_links
from .presentation import style_document


class _PreviewDocument(qt.QTextDocument):
    def loadResource(self, kind, url):
        # Hovering must not load embedded images or other local/remote resources.
        return None


class LinkPreview(qt.QObject):
    def __init__(self, viewer):
        super().__init__(viewer)
        self.viewer = viewer
        self.link = ''
        self.popup = qt.QFrame(viewer, qt.Qt.WindowType.ToolTip)
        self.popup.setAttribute(qt.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.popup.setAttribute(qt.Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.popup.setWindowFlag(qt.Qt.WindowType.WindowDoesNotAcceptFocus)
        self.popup.setFrameShape(qt.QFrame.Shape.StyledPanel)
        self.popup.setAccessibleName('Linked file preview')
        layout = qt.QVBoxLayout(self.popup)
        self.title = qt.QLabel()
        self.title.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.title.setWordWrap(True)
        self.snippet = qt.QTextBrowser()
        self.snippet.setDocument(_PreviewDocument(self.snippet))
        self.snippet.setOpenLinks(False)
        self.snippet.setOpenExternalLinks(False)
        self.snippet.setTextInteractionFlags(qt.Qt.TextInteractionFlag.NoTextInteraction)
        self.snippet.setReadOnly(True)
        self.snippet.setAccessibleName('Linked file snippet')
        self.snippet.setFont(qt.QFontDatabase.systemFont(qt.QFontDatabase.SystemFont.FixedFont))
        self.snippet.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.snippet.setVerticalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.snippet.setLineWrapMode(qt.QTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self.title)
        layout.addWidget(self.snippet)
        self.popup.resize(460, 260)
        viewport = viewer.browser.viewport()
        viewport.setMouseTracking(True)
        viewport.installEventFilter(self)
        viewer.browser.installEventFilter(self)
        viewer.installEventFilter(self)
        viewer.edit_button.toggled.connect(self.hide)
        viewer.path_changed.connect(self.hide)
        viewer.browser.textChanged.connect(self.hide)
        viewer.browser.verticalScrollBar().valueChanged.connect(self.hide)
        viewer.browser.horizontalScrollBar().valueChanged.connect(self.hide)
        app = qt.QApplication.instance()
        app.applicationStateChanged.connect(self.hide)

    def hide(self, *args):
        self.link = ''
        if isValid(self.popup):
            self.popup.hide()
        if isValid(self.title):
            self.title.clear()
        if isValid(self.snippet):
            self.snippet.clear()

    def show_link(self, link, position):
        if (not link or self.viewer.edit_button.isChecked() or self.viewer.storage is not None
                or self.viewer.current_path is None):
            self.hide()
            return
        if link == self.link:
            return
        self.hide()
        try:
            url = qt.QUrl.fromLocalFile(str(self.viewer.current_path)).resolved(qt.QUrl(link))
            if not url.isLocalFile():
                return
            path = Path(url.toLocalFile())
            check_local_path(path)
            path = resolve_document_path(path)
            check_local_path(path)
            # Sniff and read one bounded prefix. Never execute code, fetch links,
            # load images, or modify the document/history to show a preview.
            with path.open('rb') as stream:
                data = stream.read(16385)
            if likely_binary(data[:8192]):
                return
            text = data[:16384].decode('utf-8-sig', errors='replace')
            lines = text.splitlines()
            snippet = '\n'.join(lines[:18])[:2400]
            if len(data) > 16384 or len(lines) > 18 or len(snippet) > 2399:
                snippet += '\n…'
        except (OSError, ValueError):
            return
        self.link = link
        self.title.setText(path.name)
        if path.suffix.lower() in ('.md', '.markdown'):
            font = self.viewer.browser.font()
            self.snippet.setFont(font)
            self.snippet.document().setDefaultFont(font)
            rendered, callouts = reading_source(split_frontmatter(snippet).body)
            self.snippet.document().setMarkdown(render_links(rendered or '(Empty file)'),
                qt.QTextDocument.MarkdownFeature.MarkdownDialectGitHub |
                qt.QTextDocument.MarkdownFeature.MarkdownNoHTML)
            style_document(self.snippet.document(), self.viewer.browser.palette(), callouts=callouts)
        else:
            font = qt.QFontDatabase.systemFont(qt.QFontDatabase.SystemFont.FixedFont)
            self.snippet.setFont(font)
            self.snippet.document().setDefaultFont(font)
            self.snippet.setPlainText(snippet or '(Empty file)')
        self.snippet.verticalScrollBar().setValue(0)
        self.snippet.horizontalScrollBar().setValue(0)
        screen = qt.QGuiApplication.screenAt(position) or self.viewer.screen()
        bounds = screen.availableGeometry()
        self.popup.resize(min(460, bounds.width()), min(260, bounds.height()))
        x, y = position.x() + 16, position.y() + 20
        if y + self.popup.height() > bounds.bottom():
            y = position.y() - self.popup.height() - 12
        self.popup.move(max(bounds.left(), min(x, bounds.right() - self.popup.width() + 1)),
                        max(bounds.top(), min(y, bounds.bottom() - self.popup.height() + 1)))
        self.popup.show()

    def eventFilter(self, watched, event):
        if not isValid(self.viewer.browser) or not isValid(self.popup):
            return False
        kind = event.type()
        viewport = self.viewer.browser.viewport()
        if watched is viewport and kind == qt.QEvent.Type.MouseMove:
            self.show_link(self.viewer.browser.anchorAt(event.position().toPoint()),
                           event.globalPosition().toPoint())
        elif kind in (qt.QEvent.Type.Leave, qt.QEvent.Type.Hide,
                      qt.QEvent.Type.WindowDeactivate, qt.QEvent.Type.MouseButtonPress):
            self.hide()
        elif watched is viewport and kind == qt.QEvent.Type.ToolTip and self.link:
            return True
        return super().eventFilter(watched, event)
