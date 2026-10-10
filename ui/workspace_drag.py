"""Explicit tab drop targets supplement Qt's platform-dependent dock dragging."""
from weakref import WeakValueDictionary
from uuid import uuid4
from . import pyside as qt
from shiboken6 import isValid

MIME = 'application/x-commonutils-workspace-tab'
_docks = WeakValueDictionary()


class DockWindowDrag(qt.QObject):
    """Move the actual pane and resolve drops consistently on every platform."""
    def __init__(self, workspace, dock, point, origin):
        super().__init__(workspace)
        self.workspace, self.dock = workspace, dock
        self.hotspot = dock.mapFromGlobal(origin)
        self.hotspot.setY(max(15, self.hotspot.y()))
        size = dock.size()
        dock.setFloating(True)
        dock.resize(size)
        dock.show(); dock.raise_()
        dock.tab_header.grabMouse()
        qt.QApplication.instance().installEventFilter(self)
        self.move(point)

    def target(self, point):
        from .workspace import _workspaces
        page = getattr(self.workspace, 'page', None)
        if page is not None and page.window().frameGeometry().contains(point):
            page.activate()
        for workspace in tuple(_workspaces):
            if (isValid(workspace) and workspace.isVisible() and not workspace._closing
                    and workspace.dock_group == self.workspace.dock_group):
                local = workspace.mapFromGlobal(point)
                if workspace.rect().contains(local):
                    anchor, placement, preview = workspace._drop_location(local, self.dock)
                    return workspace, anchor, placement, preview
        return None

    def clear_preview(self):
        from .workspace import _workspaces
        for workspace in tuple(_workspaces):
            if isValid(workspace):
                workspace._drop_preview.hide()

    def move(self, point):
        self.dock.move(point - self.hotspot)
        self.clear_preview()
        target = self.target(point)
        if target:
            workspace, anchor, placement, preview = target
            workspace._drop_preview.setGeometry(preview)
            workspace._drop_preview.show(); workspace._drop_preview.raise_()
        self.dock.raise_()

    def finish(self, point, *, cancel=False):
        qt.QApplication.instance().removeEventFilter(self)
        alive = isValid(self.dock) and self.dock in self.workspace.docks
        target = None if cancel or not alive else self.target(point)
        self.clear_preview()
        if isValid(self.dock.tab_header):
            self.dock.tab_header.releaseMouse()
        self.workspace._window_drag = None
        if target:
            workspace, anchor, placement, preview = target
            if self.dock.workspace is not workspace:
                workspace.adopt(self.dock)
            workspace.arrange(self.dock, placement, anchor=anchor)
            workspace._update_drop_target()
        self.deleteLater()

    def eventFilter(self, watched, event):
        if not isValid(self.dock) or self.dock not in self.workspace.docks or self.workspace._closing:
            self.finish(qt.QCursor.pos(), cancel=True)
            return False
        if event.type() == qt.QEvent.Type.MouseMove:
            if not event.buttons() & qt.Qt.MouseButton.LeftButton:
                self.finish(event.globalPosition().toPoint())
                return True
            self.move(event.globalPosition().toPoint())
            return True
        if event.type() == qt.QEvent.Type.MouseButtonRelease and event.button() == qt.Qt.MouseButton.LeftButton:
            self.finish(event.globalPosition().toPoint())
            return True
        if event.type() == qt.QEvent.Type.KeyPress and event.key() == qt.Qt.Key.Key_Escape:
            self.finish(qt.QCursor.pos(), cancel=True)
            return True
        return False


def register_dock(dock):
    dock.drag_id = uuid4().hex
    _docks[dock.drag_id] = dock


def tab_mime(dock):
    data = qt.QMimeData()
    data.setData(MIME, dock.drag_id.encode('ascii'))
    return data


class WorkspaceDragMixin:
    def begin_window_drag(self, dock, point, origin):
        if self._closing:
            return
        self._window_drag = DockWindowDrag(self, dock, point, origin)

    def drag_tab(self, dock):
        drag = qt.QDrag(self)
        drag.setMimeData(tab_mime(dock))
        drag.setPixmap(dock.grab())
        point = dock.mapFromGlobal(qt.QCursor.pos())
        drag.setHotSpot(qt.QPoint(max(0, min(point.x(), dock.width() - 1)),
                                max(0, min(point.y(), dock.height() - 1))))
        result = drag.exec(qt.Qt.DropAction.MoveAction)
        self._drop_preview.hide()
        if result == qt.Qt.DropAction.IgnoreAction and not qt.QApplication.mouseButtons():
            from .workspace import _workspaces
            point = qt.QCursor.pos()
            if not any(isValid(workspace) and workspace.isVisible() and qt.QRect(workspace.mapToGlobal(qt.QPoint()), workspace.size()).contains(point)
                       for workspace in tuple(_workspaces)):
                dock.setFloating(True)
                dock.move(point - qt.QPoint(40, 15))
                dock.show()

    def _drop_dock(self, event):
        if not event.mimeData().hasFormat(MIME) or self._closing:
            return None
        key = bytes(event.mimeData().data(MIME)).decode('ascii', errors='ignore')
        dock = _docks.get(key)
        return dock if (dock is not None and isValid(dock) and isValid(dock.workspace) and dock in dock.workspace.docks
                        and dock.workspace.dock_group == self.dock_group) else None

    def _drop_location(self, point, moving):
        target = next((dock for dock in self.docks if dock is not moving
                       and not dock.isFloating() and dock.isVisible()
                       and dock.geometry().contains(point)), None)
        if target is None:
            target = self._docked_anchor(excluding=moving)
        rect = target.geometry() if target else self.contentsRect()
        fraction = (point.x() - rect.left()) / max(1, rect.width())
        placement = 'left' if fraction < .25 else 'right' if fraction > .75 else 'tabs'
        preview = qt.QRect(rect)
        if placement != 'tabs':
            preview.setWidth(rect.width() // 2)
            if placement == 'right':
                preview.moveRight(rect.right())
        return target, placement, preview

    def handle_tab_drop(self, watched, event):
        kind = event.type()
        if kind == qt.QEvent.Type.DragLeave:
            self._drop_preview.hide()
            return False
        if kind not in (qt.QEvent.Type.DragEnter, qt.QEvent.Type.DragMove, qt.QEvent.Type.Drop):
            return False
        dock = self._drop_dock(event)
        if dock is None:
            return False
        point = watched.mapTo(self, event.position().toPoint())
        target, placement, preview = self._drop_location(point, dock)
        event.setDropAction(qt.Qt.DropAction.MoveAction)
        event.accept()
        if kind == qt.QEvent.Type.Drop:
            self._drop_preview.hide()
            if dock.workspace is not self:
                self.adopt(dock)
            self.arrange(dock, placement, anchor=target)
            self._update_drop_target()
        else:
            self._drop_preview.setGeometry(preview)
            self._drop_preview.show()
            self._drop_preview.raise_()
        return True

    def dragEnterEvent(self, event):
        if not self.handle_tab_drop(self, event):
            event.ignore()

    def dragMoveEvent(self, event):
        if not self.handle_tab_drop(self, event):
            event.ignore()

    def dragLeaveEvent(self, event):
        self._drop_preview.hide()
        event.accept()

    def dropEvent(self, event):
        if not self.handle_tab_drop(self, event):
            event.ignore()
