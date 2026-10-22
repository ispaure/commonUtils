"""Tab gestures confined to an explicit widget boundary; never create windows."""
from .. import pyside as qt
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
        self._observing_gesture = False
        self.preview = qt.QRubberBand(qt.QRubberBand.Shape.Rectangle, group)
        self.destroyed.connect(self.preview.deleteLater)
        self.setFocusPolicy(qt.Qt.FocusPolicy.StrongFocus)
        self.setElideMode(qt.Qt.TextElideMode.ElideRight)
        self.setUsesScrollButtons(True)

    def tabInserted(self, index):
        super().tabInserted(index)
        if not self.tabsClosable():
            return
        from .headers import _tab_button
        button = _tab_button('×', 'Close tab', self)
        def close():
            current = self.tabAt(button.pos() + button.rect().center())
            if current >= 0:
                self.tabCloseRequested.emit(current)
        button.clicked.connect(close)
        self.setTabButton(index, qt.QTabBar.ButtonPosition.LeftSide, None)
        self.setTabButton(index, qt.QTabBar.ButtonPosition.RightSide, button)

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
            self.cancel_drag()
            self.setFocus(qt.Qt.FocusReason.MouseFocusReason)
            index = self.tabAt(event.position().toPoint())
            self.press = event.globalPosition().toPoint()
            self.view = self.group.widget(index) if index >= 0 else None
            if self.view is not None:
                qt.QApplication.instance().installEventFilter(self)
                self._observing_gesture = True
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.view is not None and not event.buttons() & qt.Qt.MouseButton.LeftButton:
            self.cancel_drag()
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
        if self._observing_gesture:
            qt.QApplication.instance().removeEventFilter(self)
            self._observing_gesture = False
        self.preview.hide()
        if self.preview.parentWidget() is not self.group:
            self.preview.setParent(self.group)
        self.press = self.view = None
        self.dragging = False

    def eventFilter(self, watched, event):
        # Native capture can transfer when the pointer crosses child widgets.
        # Observe only this press/release sequence, so the destination cannot
        # consume its release and leave the source's snap preview stranded.
        if self.view is not None:
            kind = event.type()
            if kind == qt.QEvent.Type.Hide and watched in (self, self.group, self.boundary):
                self.cancel_drag()
            elif kind == qt.QEvent.Type.WindowDeactivate and watched is self.window():
                self.cancel_drag()
            elif kind == qt.QEvent.Type.KeyPress and event.key() == qt.Qt.Key.Key_Escape:
                self.cancel_drag()
                event.accept()
                return True
            elif watched is not self:
                if kind == qt.QEvent.Type.MouseMove:
                    if not event.buttons() & qt.Qt.MouseButton.LeftButton:
                        self.cancel_drag()
                    else:
                        self.mouseMoveEvent(self._source_mouse_event(event))
                        return self.dragging
                elif kind == qt.QEvent.Type.MouseButtonRelease and event.button() == qt.Qt.MouseButton.LeftButton:
                    dragging = self.dragging
                    self.mouseReleaseEvent(self._source_mouse_event(event))
                    return dragging
                elif kind == qt.QEvent.Type.MouseButtonPress:
                    self.cancel_drag()
        return super().eventFilter(watched, event)

    def _source_mouse_event(self, event):
        return qt.QMouseEvent(event.type(),
            qt.QPointF(self.mapFromGlobal(event.globalPosition().toPoint())),
            event.globalPosition(), event.button(), event.buttons(), event.modifiers())

    def keyPressEvent(self, event):
        if event.key() == qt.Qt.Key.Key_Escape:
            self.cancel_drag()
            event.accept()
        else:
            super().keyPressEvent(event)
