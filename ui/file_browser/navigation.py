"""Root-bounded folder breadcrumbs and back/forward history."""

from pathlib import Path
from .. import pyside as qt
from .controls import navigation_button


class BreadcrumbSeparator(qt.QWidget):
    """Font-independent chevron, vertically centered on every platform."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(14)
        self.setSizePolicy(qt.QSizePolicy.Policy.Fixed, qt.QSizePolicy.Policy.Expanding)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter = qt.QPainter(self)
        painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
        painter.setPen(qt.QPen(self.palette().color(qt.QPalette.ColorRole.PlaceholderText), 1.5))
        x, y = self.width()/2, self.height()/2
        painter.drawLine(qt.QPointF(x-2,y-4), qt.QPointF(x+2,y))
        painter.drawLine(qt.QPointF(x+2,y), qt.QPointF(x-2,y+4))


class BreadcrumbBar(qt.QWidget):
    requested = qt.Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.buttons = []
        self.paths = []
        self.icons = qt.QFileIconProvider()
        self.layout = qt.QHBoxLayout(self)
        self.layout.setContentsMargins(5, 2, 5, 2)
        self.layout.setSpacing(2)
        self.root_button = qt.QToolButton()
        self.root_button.setAutoRaise(True)
        self.root_button.setToolButtonStyle(qt.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.layout.addWidget(self.root_button)
        self.root_button.clicked.connect(lambda: self.requested.emit(self.paths[0]) if self.paths else None)
        self.scroll = qt.QScrollArea()
        self.scroll.setFrameShape(qt.QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setSizePolicy(qt.QSizePolicy.Policy.Expanding, qt.QSizePolicy.Policy.Fixed)
        self.scroll.viewport().setAutoFillBackground(False)
        self.scroll.setAutoFillBackground(False)
        self.content = qt.QWidget()
        self.content.setAutoFillBackground(False)
        self.crumbs = qt.QHBoxLayout(self.content)
        self.crumbs.setContentsMargins(0, 0, 0, 0)
        self.crumbs.setSpacing(2)
        self.scroll.setWidget(self.content)
        self.layout.addWidget(self.scroll, 1)
        self.setAccessibleName('Folder path')
        self.set_paths([])

    def paintEvent(self, event):
        painter = qt.QPainter(self)
        painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
        painter.setPen(qt.QPen(self.palette().color(qt.QPalette.ColorRole.Mid), 1))
        painter.setBrush(self.palette().brush(qt.QPalette.ColorRole.AlternateBase))
        painter.drawRoundedRect(qt.QRectF(self.rect()).adjusted(.5,.5,-.5,-.5), 5, 5)

    def set_paths(self, paths):
        self.paths = list(paths)
        self.buttons = []
        while self.crumbs.count():
            item = self.crumbs.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
        self.root_button.setVisible(bool(paths))
        if paths:
            root = paths[0]
            self._configure(self.root_button, root)
            self.buttons.append(self.root_button)
            for path in paths[1:]:
                arrow = BreadcrumbSeparator(self.content)
                self.crumbs.addWidget(arrow)
                button = qt.QToolButton()
                button.setAutoRaise(True)
                button.setToolButtonStyle(qt.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                self._configure(button, path)
                button.clicked.connect(lambda checked=False, directory=path: self.requested.emit(directory))
                self.crumbs.addWidget(button)
                self.buttons.append(button)
            self.setToolTip(str(paths[-1]))
        else:
            self.setToolTip('')
        self.crumbs.addStretch()
        self.scroll.setFixedHeight(max(30, self.root_button.sizeHint().height() + 4))
        qt.QTimer.singleShot(0, self._show_current)

    def _configure(self, button, path):
        button.setText(path.name or str(path))
        button.setToolTip(str(path))
        button.setAccessibleName(f'Go to folder {path.name or path}')
        button.setIcon(self.icons.icon(qt.QFileInfo(str(path))))
        button.setIconSize(qt.QSize(18, 18))

    def _show_current(self):
        if len(self.buttons) > 1:
            self.scroll.ensureWidgetVisible(self.buttons[-1], 0, 0)


class NavigationBar(qt.QWidget):
    requested = qt.Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.library = None
        self.directory = None
        self.history = []
        self.position = -1
        layout = qt.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.back = navigation_button(self, 'Back', qt.QStyle.StandardPixmap.SP_ArrowBack)
        self.forward = navigation_button(self, 'Forward', qt.QStyle.StandardPixmap.SP_ArrowForward)
        self.up = navigation_button(self, 'Up one folder', qt.QStyle.StandardPixmap.SP_ArrowUp)
        self.breadcrumbs = BreadcrumbBar(self)
        for button in (self.back, self.forward, self.up):
            layout.addWidget(button)
        layout.addWidget(self.breadcrumbs, 1)
        self.back.clicked.connect(lambda: self._history(-1))
        self.forward.clicked.connect(lambda: self._history(1))
        self.up.clicked.connect(lambda: self.requested.emit(self.directory.parent))
        self.breadcrumbs.requested.connect(self.requested)
        self.set_library(None)

    def set_library(self, path, *, directory=None):
        self.library = Path(path) if path is not None else None
        self.directory = None
        self.history = []
        self.position = -1
        self.set_directory(Path(directory) if directory is not None else self.library)

    def set_directory(self, path):
        if path is not None:
            path = Path(path)
            if (self.library is None or not path.is_dir()
                    or (path != self.library and self.library not in path.parents)):
                return
        self.directory = path
        if path is not None and (self.position < 0 or self.history[self.position] != path):
            self.history = self.history[:self.position + 1] + [path]
            self.position += 1
        parents = []
        if path is not None:
            parents = [path]
            while parents[-1] != self.library:
                parents.append(parents[-1].parent)
        self.breadcrumbs.set_paths(list(reversed(parents)))
        self.up.setEnabled(path is not None and path != self.library)
        self.back.setEnabled(self.position > 0)
        self.forward.setEnabled(self.position >= 0 and self.position < len(self.history) - 1)
        self.breadcrumbs.setEnabled(path is not None)

    def _history(self, offset):
        position = self.position + offset
        if 0 <= position < len(self.history):
            self.position = position
            self.requested.emit(self.history[position])
