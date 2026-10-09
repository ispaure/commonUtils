"""Explicit tab drop targets supplement Qt's platform-dependent dock dragging."""
from weakref import WeakValueDictionary
from uuid import uuid4
from . import pyside as qt

MIME = 'application/x-commonutils-workspace-tab'
_docks = WeakValueDictionary()


def register_dock(dock):
    dock.drag_id = uuid4().hex
    _docks[dock.drag_id] = dock


def tab_mime(dock):
    data = qt.QMimeData()
    data.setData(MIME, dock.drag_id.encode('ascii'))
    return data


class WorkspaceDragMixin:
    def drag_tab(self, dock):
        drag = qt.QDrag(self)
        drag.setMimeData(tab_mime(dock))
        result = drag.exec(qt.Qt.DropAction.MoveAction)
        self._drop_preview.hide()
        if result == qt.Qt.DropAction.IgnoreAction and not qt.QApplication.mouseButtons():
            from .workspace import _workspaces
            point = qt.QCursor.pos()
            if not any(workspace.isVisible() and qt.QRect(workspace.mapToGlobal(qt.QPoint()), workspace.size()).contains(point)
                       for workspace in tuple(_workspaces)):
                dock.setFloating(True)
                dock.move(point - qt.QPoint(40, 15))
                dock.show()

    def _drop_dock(self, event):
        if not event.mimeData().hasFormat(MIME) or self._closing:
            return None
        key = bytes(event.mimeData().data(MIME)).decode('ascii', errors='ignore')
        dock = _docks.get(key)
        return dock if dock is not None and dock in dock.workspace.docks else None

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
