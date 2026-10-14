"""Route native file drags through the browser's cancellable transfer service."""
from pathlib import Path
from uuid import uuid4
from .. import pyside as qt

MIME = 'application/x-commonutils-browser-drag'
SESSION = uuid4().hex.encode()


class FileDragDrop(qt.QObject):
    def __init__(self, actions):
        super().__init__(actions)
        self.actions = actions
        self.views = {}
        self.indicators = {}
        self.press = None
        browser = actions.browser
        for view in browser.views.navigation_views:
            self.install(view)
        if browser.views.columns is not None:
            browser.views.columns.column_created.connect(self.install)
            for view in browser.views.columns.findChildren(qt.QListView):
                self.install(view)

    def install(self, view):
        viewport = view.viewport()
        if viewport in self.views:
            return
        self.views[viewport] = view
        self.indicators[viewport] = qt.QRubberBand(qt.QRubberBand.Shape.Rectangle, viewport)
        view.destroyed.connect(lambda: self.indicators.pop(viewport, None))
        view.destroyed.connect(lambda: self.views.pop(viewport, None))
        viewport.setAcceptDrops(True)
        viewport.installEventFilter(self)
        view.setDragEnabled(False)  # Our QDrag never deletes source rows after an async drop.

    def destination(self, view, point):
        index = view.indexAt(point)
        if not index.isValid():
            index = view.rootIndex()
        index = self.actions.browser.views.source_index(index)
        if not index.isValid():
            return None
        path = Path(self.actions.browser.model.filePath(index))
        return path if path.is_dir() else path.parent

    def eventFilter(self, viewport, event):
        view = self.views.get(viewport)
        if view is None:
            return False
        kind = event.type()
        if kind == qt.QEvent.Type.MouseButtonPress:
            self.press = (viewport, event.position().toPoint()) if event.button() == qt.Qt.MouseButton.LeftButton else None
        elif kind == qt.QEvent.Type.MouseButtonRelease:
            self.press = None
        elif kind == qt.QEvent.Type.MouseMove and self.press and event.buttons() & qt.Qt.MouseButton.LeftButton:
            owner, start = self.press
            if owner is viewport and (event.position().toPoint() - start).manhattanLength() >= qt.QApplication.startDragDistance():
                self.press = None
                if self.actions.busy or self.actions.browser.stopping or not view.indexAt(start).isValid():
                    return False
                indices = view.selectionModel().selectedRows(0) or view.selectionModel().selectedIndexes()
                paths = tuple(dict.fromkeys(self.actions.browser.model.filePath(
                    self.actions.browser.views.source_index(index)) for index in indices if index.column() == 0))
                if not paths:
                    return False
                mime = qt.QMimeData()
                mime.setUrls([qt.QUrl.fromLocalFile(path) for path in paths])
                mime.setData(MIME, SESSION)
                drag = qt.QDrag(view)
                drag.setMimeData(mime)
                drag.exec(qt.Qt.DropAction.CopyAction | qt.Qt.DropAction.MoveAction, qt.Qt.DropAction.MoveAction)
                drag.deleteLater()
                return True
        elif kind == qt.QEvent.Type.DragLeave:
            self.indicators[viewport].hide()
        elif kind in (qt.QEvent.Type.DragEnter, qt.QEvent.Type.DragMove, qt.QEvent.Type.Drop):
            urls = event.mimeData().urls()
            directory = self.destination(view, event.position().toPoint())
            if (self.actions.busy or self.actions.browser.stopping or directory is None or not urls
                    or any(not url.isLocalFile() for url in urls)):
                self.indicators[viewport].hide()
                event.ignore()
                return True
            internal = bytes(event.mimeData().data(MIME)) == SESSION
            copy_modifier = event.modifiers() & (qt.Qt.KeyboardModifier.ControlModifier | qt.Qt.KeyboardModifier.AltModifier)
            move = internal and not copy_modifier
            action = qt.Qt.DropAction.MoveAction if move else qt.Qt.DropAction.CopyAction
            if not event.possibleActions() & action:
                self.indicators[viewport].hide()
                event.ignore()
                return True
            event.setDropAction(action)
            event.accept()
            if kind == qt.QEvent.Type.Drop:
                self.indicators[viewport].hide()
                self.actions.transfer(tuple(Path(url.toLocalFile()) for url in urls), directory, move=move)
            else:
                index = view.indexAt(event.position().toPoint())
                source = self.actions.browser.views.source_index(index)
                on_folder = source.isValid() and self.actions.browser.model.isDir(source)
                self.indicators[viewport].setGeometry(view.visualRect(index) if on_folder else viewport.rect())
                self.indicators[viewport].show()
            return True
        return False
