"""Tab gestures confined to an explicit widget boundary; never create windows."""
from . import pyside as qt
from .workspace_drag import horizontal_drop_location


class ScopedTabBar(qt.QTabBar):
    """Host owns moves/buffers. groups() returns current QTabWidgets in boundary.

    move_tab(view, target, placement, index) accepts/rejects the final operation.
    A drop on a header inserts/reorders; content uses shared side snap geometry.
    """
    def __init__(self, group, boundary, groups, move_tab, can_move=None):
        super().__init__(group)
        self.group, self.boundary = group, boundary
        self.groups, self.move_tab = groups, move_tab
        self.can_move = can_move
        self.press = self.view = None
        self.dragging = False
        self.preview = qt.QRubberBand(qt.QRubberBand.Shape.Rectangle, group)
        self.destroyed.connect(self.preview.deleteLater)
        self.setFocusPolicy(qt.Qt.FocusPolicy.StrongFocus)
        self.setElideMode(qt.Qt.TextElideMode.ElideRight)
        self.setUsesScrollButtons(True)

    def target(self, global_point):
        point = self.boundary.mapFromGlobal(global_point)
        if not self.boundary.rect().contains(point):
            return None
        for group in self.groups():
            if not group.isVisible() or not self.boundary.isAncestorOf(group):
                continue
            local = group.mapFromGlobal(global_point)
            if not group.rect().contains(local):
                continue
            bar = group.tabBar()
            on_bar = bar.mapFromGlobal(global_point)
            rect = qt.QRect(group.mapTo(self.boundary, qt.QPoint()), group.size())
            if not group.count() or 0 <= on_bar.y() < bar.height():
                index = bar.tabAt(on_bar)
                result = (group, 'tabs', index if index >= 0 else group.count(), rect)
            else:
                placement, preview = horizontal_drop_location(rect, point)
                result = (group, placement, group.count(), preview)
            if self.view is not None and self.can_move is not None and not self.can_move(self.view, *result[:3]):
                return None
            return result
        return None

    def mousePressEvent(self, event):
        if event.button() == qt.Qt.MouseButton.LeftButton:
            self.setFocus(qt.Qt.FocusReason.MouseFocusReason)
            index = self.tabAt(event.position().toPoint())
            self.press = event.globalPosition().toPoint()
            self.view = self.group.widget(index) if index >= 0 else None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.view is not None and event.buttons() & qt.Qt.MouseButton.LeftButton:
            point = event.globalPosition().toPoint()
            if self.dragging or (point - self.press).manhattanLength() >= qt.QApplication.startDragDistance():
                self.dragging = True
                target = self.target(point)
                if target:
                    group, _, _, rect = target
                    if self.preview.parentWidget() is not group:
                        self.preview.setParent(group)
                    local = group.mapFrom(self.boundary, rect.topLeft())
                    self.preview.setGeometry(qt.QRect(local, rect.size()))
                    self.preview.show()
                    self.preview.raise_()
                else:
                    self.preview.hide()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() != qt.Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        target = self.target(event.globalPosition().toPoint()) if self.dragging else None
        view = self.view
        self.cancel_drag()
        super().mouseReleaseEvent(event)
        if target and view is not None and self.group.indexOf(view) >= 0:
            self.move_tab(view, *target[:3])

    def cancel_drag(self):
        self.preview.hide()
        if self.preview.parentWidget() is not self.group:
            self.preview.setParent(self.group)
        self.press = self.view = None
        self.dragging = False

    def keyPressEvent(self, event):
        if event.key() == qt.Qt.Key.Key_Escape:
            self.cancel_drag()
            event.accept()
        else:
            super().keyPressEvent(event)
