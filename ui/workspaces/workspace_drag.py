"""Explicit tab drop targets supplement Qt's platform-dependent dock dragging."""
from weakref import WeakValueDictionary
from uuid import uuid4
from .. import pyside as qt
from shiboken6 import isValid

MIME = 'application/x-commonutils-workspace-tab'
_docks = WeakValueDictionary()


def horizontal_drop_location(rect, point):
    """Shared left/center/right snapping geometry, in the caller's coordinates."""
    fraction = (point.x() - rect.left()) / max(1, rect.width())
    placement = 'left' if fraction < .25 else 'right' if fraction > .75 else 'tabs'
    preview = qt.QRect(rect)
    if placement != 'tabs':
        preview.setWidth(rect.width() // 2)
        if placement == 'right':
            preview.moveRight(rect.right())
    return placement, preview


class DockWindowDrag(qt.QObject):
    """Move the actual pane and resolve drops consistently on every platform."""
    def __init__(self, workspace, dock, point, origin):
        super().__init__(workspace)
        self.workspace, self.dock = workspace, dock
        self.original_state = workspace.saveState()
        self.original_geometry = dock.geometry()
        self.original_floating = dock.isFloating()
        self.original_active = workspace.active_dock
        self._finished = False
        self._restore_destination = None
        self.hotspot = dock.mapFromGlobal(origin)
        self.hotspot.setY(max(15, self.hotspot.y()))
        size = dock.size()
        qt.QDockWidget.setFloating(dock, True)
        dock.resize(size)
        dock.show(); dock.raise_()
        dock.tab_header.grabMouse()
        qt.QApplication.instance().installEventFilter(self)
        self.move(point)

    def target(self, point):
        from .workspace import _workspaces
        self.preview_destination(point)
        candidates = sorted(tuple(_workspaces), key=lambda owner: owner is not self.workspace.main_workspace)
        for workspace in candidates:
            if (isValid(workspace) and workspace.isVisible() and not workspace._closing
                    and workspace.dock_group == self.workspace.dock_group
                    and self.dock.workspace.can_move_tab(self.dock, destination=workspace)):
                local = workspace.mapFromGlobal(point)
                if workspace.rect().contains(local):
                    anchor, placement, preview = workspace._drop_location(local, self.dock)
                    return workspace, anchor, placement, preview
        return None

    def preview_destination(self, point):
        main = self.workspace.main_workspace
        inside = main.window().frameGeometry().contains(point)
        if not inside and self._restore_destination is not None:
            self._restore_destination()
            self._restore_destination = None
        elif inside and self._restore_destination is None:
            self._restore_destination = self.workspace.reveal_for_drop(point)

    def finish_destination(self, committed):
        if self._restore_destination is not None:
            restore, self._restore_destination = self._restore_destination, None
            if not committed:
                restore()

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
        if self._finished:
            return
        self._finished = True
        qt.QApplication.instance().removeEventFilter(self)
        alive = isValid(self.dock) and self.dock in self.workspace.docks
        target = None if cancel or not alive else self.target(point)
        self.clear_preview()
        if isValid(self.dock) and isValid(self.dock.tab_header):
            self.dock.tab_header.releaseMouse()
        self.workspace._window_drag = None
        completed = False
        if target:
            workspace, anchor, placement, preview = target
            if workspace.adopt(self.dock, placement=placement, anchor=anchor):
                workspace._update_drop_target()
                completed = True
        elif alive and not cancel:
            from .workspace import _workspaces
            # An incompatible/closing workspace is a rejected destination, not
            # empty desktop space. Do not detach on an invalid drop.
            occupied = any(isValid(owner) and owner.isVisible()
                           and owner.rect().contains(owner.mapFromGlobal(point))
                           for owner in tuple(_workspaces))
            if not occupied:
                if self.workspace.policy is not None:
                    window = self.workspace.detach_dock(self.dock)
                    if window:
                        window.move(point - self.hotspot)
                        completed = True
                else:
                    completed = True
        if alive and not completed and self.dock.workspace is self.workspace:
            self.workspace.restoreState(self.original_state)
            qt.QDockWidget.setFloating(self.dock, self.original_floating)
            self.dock.setGeometry(self.original_geometry)
            self.dock.show()
            if self.original_active in self.workspace.docks:
                self.original_active.raise_()
                self.workspace._activate(self.original_active)
            self.workspace._update_drop_target()
        self.finish_destination(bool(target and completed and target[0] is self.workspace.main_workspace))
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
        if self._closing or not self.can_move_tab(dock):
            return
        if self._window_drag is not None:
            self._window_drag.finish(point, cancel=True)
        self._window_drag = DockWindowDrag(self, dock, point, origin)

    def drag_tab(self, dock):
        if not self.can_move_tab(dock):
            return
        drag = qt.QDrag(self)
        drag.setMimeData(tab_mime(dock))
        drag.setPixmap(dock.grab())
        point = dock.mapFromGlobal(qt.QCursor.pos())
        drag.setHotSpot(qt.QPoint(max(0, min(point.x(), dock.width() - 1)),
                                max(0, min(point.y(), dock.height() - 1))))
        # IgnoreAction includes Escape and rejected targets. Ownership stays put;
        # desktop detachment is handled by the explicit window-drag controller.
        drag.exec(qt.Qt.DropAction.MoveAction)
        self._drop_preview.hide()

    def _drop_dock(self, event):
        if not event.mimeData().hasFormat(MIME) or self._closing:
            return None
        key = bytes(event.mimeData().data(MIME)).decode('ascii', errors='ignore')
        dock = _docks.get(key)
        return dock if (dock is not None and isValid(dock) and isValid(dock.workspace) and dock in dock.workspace.docks
                        and dock.workspace.dock_group == self.dock_group
                        and dock.workspace.can_move_tab(dock, destination=self)) else None

    def _drop_location(self, point, moving):
        target = next((dock for dock in self.docks if dock is not moving
                       and not dock.isFloating() and dock.isVisible()
                       and dock.geometry().contains(point)), None)
        if target is None:
            target = self._docked_anchor(excluding=moving)
        rect = target.geometry() if target else self.contentsRect()
        placement, preview = horizontal_drop_location(rect, point)
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
            if not self.adopt(dock, placement=placement, anchor=target):
                event.ignore()
                return True
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


class NativeWindowDrag(DockWindowDrag):
    """Observe OS title-bar moves without replacing the platform's window dragging."""
    def __init__(self, window, geometry):
        qt.QObject.__init__(self, window)
        self.window = window
        self.workspace = window.workspace
        self._restore_destination = None
        self.original_geometry = qt.QRect(geometry)
        self._finished = False
        self.timer = qt.QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self.poll)
        qt.QApplication.instance().installEventFilter(self)
        self.timer.start()

    def target(self, point):
        main = self.workspace.main_workspace
        self.preview_destination(point)
        if (main.isVisible() and not main._closing and self.workspace.docks
                and main.rect().contains(main.mapFromGlobal(point))):
            dock = self.workspace.active_dock or self.workspace.docks[0]
            anchor, placement, preview = main._drop_location(main.mapFromGlobal(point), dock)
            return main, anchor, placement, preview
        return None

    def move(self, point):
        self.clear_preview()
        target = self.target(point)
        if target:
            owner, _, _, preview = target
            owner._drop_preview.setGeometry(preview)
            owner._drop_preview.show()
            owner._drop_preview.raise_()

    def poll(self):
        point = qt.QCursor.pos()
        from .workspace_cocoa import left_button_pressed
        if left_button_pressed():
            self.move(point)
        else:
            self.finish(point)

    def finish(self, point, *, cancel=False):
        if self._finished:
            return
        self._finished = True
        self.timer.stop()
        qt.QApplication.instance().removeEventFilter(self)
        target = None if cancel else self.target(point)
        self.clear_preview()
        committed = False
        if target:
            main, anchor, placement, _ = target
            docks = tuple(self.workspace.docks)
            capacity = main.policy.max_tabs if main.policy else None
            if capacity is None or len(main.docks) + len(docks) <= capacity:
                for dock in docks:
                    if not main.adopt(dock, placement=placement, anchor=anchor):
                        break
                    anchor, placement = dock, 'tabs'
                    committed = True
        self.finish_destination(committed)
        if cancel:
            self.window._native_drag_blocked = True
            self.window.setGeometry(self.original_geometry)
        self.window._native_drag = None
        self.deleteLater()

    def eventFilter(self, watched, event):
        if event.type() == qt.QEvent.Type.KeyPress and event.key() == qt.Qt.Key.Key_Escape:
            self.finish(qt.QCursor.pos(), cancel=True)
            return True
        if event.type() in (qt.QEvent.Type.MouseButtonRelease, qt.QEvent.Type.NonClientAreaMouseButtonRelease):
            if event.button() == qt.Qt.MouseButton.LeftButton:
                self.finish(event.globalPosition().toPoint())
        return False
