"""Dock header presentation, buttons and painting."""
from .. import pyside as qt

TAB_BUTTON_SIZE = 28
TAB_HEADER_HEIGHT = 30
TAB_PLUS_RESERVE = 32


class _DockTabStyle(qt.QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, return_data=None):
        if hint == qt.QStyle.StyleHint.SH_TabBar_Alignment:
            # macOS centers native dock tabs, including our reserved + space.
            return qt.Qt.AlignmentFlag.AlignLeft.value
        return super().styleHint(hint, option, widget, return_data)


def _tab_button(text, tooltip, parent, callback=None):
    button = qt.QToolButton(parent)
    button.setText(text)
    button.setToolTip(tooltip)
    button.setAccessibleName(tooltip)
    button.setAutoRaise(True)
    button.setFixedSize(TAB_BUTTON_SIZE, TAB_BUTTON_SIZE)
    font = button.font(); font.setPointSizeF(font.pointSizeF() * 1.5); button.setFont(font)
    if text == '×':
        from ..appearance.icons import set_painted_icon
        from ..readers.reader_chrome import ReaderIcon
        button.setText('')
        button.setToolButtonStyle(qt.Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setIconSize(qt.QSize(20, 20))
        set_painted_icon(button, ReaderIcon, 'close')
    if callback is not None:
        button.clicked.connect(callback)
    return button


class DockTabHeader(qt.QWidget):
    """Single-tab header with the same opaque dragging as grouped tab bars."""
    def __init__(self, dock):
        super().__init__(dock)
        layout = qt.QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(0)
        self.close_button = _tab_button('×', 'Close tab', self, dock.close)
        self.icon = qt.QLabel(self)
        self.icon.setAttribute(qt.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        def update_icon(icon):
            self.icon.setPixmap(icon.pixmap(16, 16))
            self.icon.setVisible(bool(dock.property('workspace_show_icon')) and not icon.isNull())
        update_icon(dock.windowIcon())
        dock.windowIconChanged.connect(update_icon)
        self.title = qt.QLabel(dock.windowTitle(), self)
        self.title.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        self.title.setMinimumWidth(0)
        self.title.setSizePolicy(qt.QSizePolicy.Policy.Ignored, qt.QSizePolicy.Policy.Preferred)
        self.title.setAttribute(qt.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.new_button = _tab_button('+', 'New tab', self, lambda: dock.workspace.request_new_view())
        self.new_button.setVisible(dock.workspace.allow_new_tabs)
        layout.addWidget(self.icon)
        layout.addWidget(self.title, 1)
        layout.addWidget(self.close_button)
        layout.addWidget(self.new_button)
        dock.windowTitleChanged.connect(self.title.setText)
        font = self.title.font(); font.setBold(True); self.title.setFont(font)
        self.setFixedHeight(TAB_HEADER_HEIGHT)
        self._press = None

    def sizeHint(self):
        # QDockWidget reserves its title area from this hint, even when the
        # title widget itself has been assigned a fixed height of zero.
        hint = super().sizeHint()
        hint.setHeight(self.minimumHeight())
        return hint

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        hint.setHeight(self.minimumHeight())
        return hint

    def mousePressEvent(self, event):
        if event.button() == qt.Qt.MouseButton.LeftButton:
            self._press = event.globalPosition().toPoint()
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        if (self._press is not None and event.buttons() & qt.Qt.MouseButton.LeftButton
                and (event.globalPosition().toPoint() - self._press).manhattanLength() >= qt.QApplication.startDragDistance()):
            origin = self._press
            self._press = None
            self.parentWidget().workspace.begin_window_drag(self.parentWidget(), event.globalPosition().toPoint(), origin)
            event.accept()
        else:
            event.ignore()

    def mouseReleaseEvent(self, event):
        self._press = None
        if self.parentWidget().isFloating():
            event.ignore()
        else:
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == qt.Qt.MouseButton.LeftButton:
            dock = self.parentWidget()
            dock.workspace.toggle_detach(dock)
            event.accept()
        else:
            event.ignore()

    def paintEvent(self, event):
        option = qt.QStyleOptionTab()
        option.initFrom(self)
        reserve = TAB_PLUS_RESERVE if self.parentWidget().workspace.allow_new_tabs else 0
        option.rect = qt.QRect(0, 0, max(0, self.width() - reserve), self.height())
        option.shape = qt.QTabBar.Shape.RoundedNorth
        option.position = qt.QStyleOptionTab.TabPosition.OnlyOneTab
        option.state |= qt.QStyle.StateFlag.State_Selected
        painter = qt.QStylePainter(self)
        painter.drawControl(qt.QStyle.ControlElement.CE_TabBarTabShape, option)
        # Palette-based selection works with and without the opt-in shared theme.
        painter.fillRect(option.rect.adjusted(0, 0, 0, -3), self.palette().brush(qt.QPalette.ColorRole.Base))
        painter.fillRect(0, self.height() - 3, option.rect.width(), 3,
                         self.palette().brush(qt.QPalette.ColorRole.Highlight))


