"""Local Markdown reading with Qt rendering, link navigation and document history."""
from pathlib import Path
import re

from . import pyside as qt


class MarkdownViewer(qt.QWidget):
    """Embeddable Markdown viewer; failed navigation leaves the current page intact."""
    path_changed = qt.Signal(object)

    def __init__(self, path=None, parent=None):
        super().__init__(parent)
        self.history = []
        self.history_index = -1
        layout = qt.QVBoxLayout(self)
        toolbar = qt.QHBoxLayout()
        self.back_button = qt.QPushButton('Back')
        self.forward_button = qt.QPushButton('Forward')
        self.back_button.setToolTip('Previous document or heading (Alt+Left)')
        self.forward_button.setToolTip('Next document or heading (Alt+Right)')
        self.location = qt.QLabel()
        self.location.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.location.setTextInteractionFlags(qt.Qt.TextInteractionFlag.TextSelectableByMouse)
        toolbar.addWidget(self.back_button)
        toolbar.addWidget(self.forward_button)
        toolbar.addWidget(self.location, 1)
        layout.addLayout(toolbar)
        self.browser = qt.QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        self.browser.setAccessibleName('Markdown document')
        self.browser.anchorClicked.connect(self.follow_link)
        layout.addWidget(self.browser, 1)
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
            text = path.read_text(encoding='utf-8-sig')
        except (OSError, UnicodeError, ValueError) as error:
            self.status.setText(f'Cannot open {path}: {error}')
            return False
        self.browser.document().setBaseUrl(qt.QUrl.fromLocalFile(str(path.parent) + '/'))
        self.browser.setMarkdown(text)
        # Qt renders headings but does not supply GitHub-style fragment names.
        used = {}
        block = self.browser.document().begin()
        while block.isValid():
            if block.blockFormat().headingLevel():
                slug = re.sub(r'[^\w\- ]', '', block.text().lower()).replace(' ', '-')
                count = used.get(slug, 0)
                used[slug] = count + 1
                anchor = f'{slug}-{count}' if count else slug
                cursor = qt.QTextCursor(block)
                cursor.movePosition(qt.QTextCursor.MoveOperation.NextCharacter, qt.QTextCursor.MoveMode.KeepAnchor)
                fmt = qt.QTextCharFormat()
                fmt.setAnchor(True)
                fmt.setAnchorNames([anchor])
                cursor.mergeCharFormat(fmt)
            block = block.next()
        self.location.setText(str(path))
        self.status.clear()
        if scroll is not None:
            self.browser.verticalScrollBar().setValue(scroll)
        elif url.fragment():
            self.browser.scrollToAnchor(url.fragment())
        else:
            self.browser.verticalScrollBar().setValue(0)
        return True

    def open_document(self, path, *, fragment=''):
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
        self.open_document(url.toLocalFile(), fragment=url.fragment())

    def _navigate_history(self, offset):
        index = self.history_index + offset
        if not 0 <= index < len(self.history):
            return
        self._remember_scroll()
        entry = self.history[index]
        if self._render(entry['url'], entry['scroll']):
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
        self.viewer.path_changed.connect(lambda path: self.setWindowTitle(f'{path.name} — Documentation'))
        self.setWindowTitle('Documentation')
        self.resize(900, 700)
        self.viewer.open_document(path)


_windows = set()


def open_markdown(path, *, parent=None):
    """Show and retain an independent viewer window until it closes; requires Qt app."""
    window = MarkdownWindow(path, parent)
    _windows.add(window)
    window.destroyed.connect(lambda: _windows.discard(window))
    window.show()
    return window
