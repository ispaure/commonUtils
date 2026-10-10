"""Reusable Qt dock-backed document tabs with cooperative view shutdown."""
from . import pyside as qt
from weakref import WeakSet
from shiboken6 import isValid
from .workspace_policy import WorkspacePolicy, header_visible
from .workspace_drag import WorkspaceDragMixin, register_dock

_workspaces = WeakSet()
_DOCK_AREAS = (qt.Qt.DockWidgetArea.LeftDockWidgetArea |
               qt.Qt.DockWidgetArea.RightDockWidgetArea |
               qt.Qt.DockWidgetArea.TopDockWidgetArea)


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
    button.setFixedSize(28, 28)
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
        self.title = qt.QLabel(dock.windowTitle(), self)
        self.title.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        self.title.setMinimumWidth(0)
        self.title.setSizePolicy(qt.QSizePolicy.Policy.Ignored, qt.QSizePolicy.Policy.Preferred)
        self.title.setAttribute(qt.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.new_button = _tab_button('+', 'New tab', self, lambda: dock.workspace.request_new_view())
        self.new_button.setVisible(dock.workspace.allow_new_tabs)
        layout.addWidget(self.close_button)
        layout.addWidget(self.title, 1)
        layout.addWidget(self.new_button)
        dock.windowTitleChanged.connect(self.title.setText)
        font = self.title.font(); font.setBold(True); self.title.setFont(font)
        self.setFixedHeight(30)
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
        reserve = 32 if self.parentWidget().workspace.allow_new_tabs else 0
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


class WorkspaceDock(qt.QDockWidget):
    owner_changed = qt.Signal(object)

    @property
    def is_detached(self):
        return self.workspace.is_detached or self.isFloating()

    def setFloating(self, floating):
        # Opt-in containers also honor policy through the historical entry point.
        if self.workspace.policy is None:
            return super().setFloating(floating)
        if floating:
            return self.workspace.detach_dock(self)
        if self.workspace.is_detached:
            return self.workspace.main_workspace.adopt(self)
        return super().setFloating(False)

    def __init__(self, workspace, view, title):
        super().__init__(title, workspace)
        self.workspace = workspace
        self.setWidget(view)
        # A floating tab is a document/tool window, never the application's quit owner.
        self.setAttribute(qt.Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setFeatures(qt.QDockWidget.DockWidgetFeature.DockWidgetClosable |
                         qt.QDockWidget.DockWidgetFeature.DockWidgetMovable |
                         qt.QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        if workspace.policy is not None:
            self.setFeatures(self.features() & ~qt.QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.setAllowedAreas(_DOCK_AREAS)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.tab_header = DockTabHeader(self)
        self.setTitleBarWidget(self.tab_header)
        self.topLevelChanged.connect(self._native_window)
        register_dock(self)
        self.setObjectName('workspace.tab.' + self.drag_id)
        self.setAcceptDrops(True)
        self.installEventFilter(workspace)
        view.setProperty('workspaceView', True)
        view.setAttribute(qt.Qt.WidgetAttribute.WA_StyledBackground, True)
        view.setStyleSheet(view.styleSheet() + '\nQWidget[workspaceView="true"] { border: 1px solid palette(mid); border-radius: 5px; }')

    def _native_window(self, floating):
        if not floating:
            return
        # Qt defaults floating docks to tool palettes. A regular window gives
        # the window manager native borders, snapping and minimize/maximize.
        geometry = self.geometry()
        visible = self.isVisible()
        self.setWindowFlags(qt.Qt.WindowType.Window |
                            qt.Qt.WindowType.WindowTitleHint |
                            qt.Qt.WindowType.WindowSystemMenuHint |
                            qt.Qt.WindowType.WindowMinMaxButtonsHint |
                            qt.Qt.WindowType.WindowCloseButtonHint)
        self.setGeometry(geometry)
        if visible:
            self.show()
        if self.windowHandle() is not None:
            self.windowHandle().setTransientParent(None)

    def contextMenuEvent(self, event):
        self.workspace._activate(self)
        menu = qt.QMenu(self)
        self.workspace.populate_tab_menu(menu, self)
        menu.exec(event.globalPos())
        menu.deleteLater()

    def closeEvent(self, event):
        if not self.workspace.can_close_tab(self):
            event.ignore()
            return
        if getattr(self.widget(), 'close_in_background', False):
            self.workspace.retire_view(self)
            qt.QTimer.singleShot(0, self.workspace, lambda: self.workspace._retry_view_close(self))
            event.ignore()
            return
        if not getattr(self.widget(), 'prepare_close', lambda: True)():
            if getattr(self.widget(), 'can_retire', False):
                self.workspace.retire_view(self)
            event.ignore()
            return
        self.workspace.remove_view(self)
        event.accept()


class Workspace(WorkspaceDragMixin, qt.QMainWindow):
    """Views expose prepare_close() and idle; their application state stays in the view."""
    active_changed = qt.Signal(object)
    tabs_changed = qt.Signal()

    def __init__(self, factory, parent=None, *, allow_new_tabs=True, dock_group='browser', keep_one_tab=False,
                 policy=None, main_workspace=None, new_view=None, setup_container=None):
        super().__init__(parent)
        self.setWindowFlags(qt.Qt.WindowType.Widget)
        self.factory = factory
        self.policy = policy
        self.main_workspace = main_workspace or self
        self.is_detached = main_workspace is not None
        self.drop_reveal = None
        self.new_view = new_view
        self.setup_container = setup_container
        self.detached_windows = []
        self._transferring = False
        self.allow_new_tabs = allow_new_tabs
        self.keep_one_tab = keep_one_tab
        self.dock_group = dock_group
        self.docks = []
        self._retiring = []
        self.setAcceptDrops(True)
        self._drag_press = None
        self._drop_preview = qt.QRubberBand(qt.QRubberBand.Shape.Rectangle, self)
        self.active_dock = None
        self._closing = False
        self._window_drag = None
        self._headers_pending = False
        self._drop_target = qt.QDockWidget('Return a detached tab', self)
        self._drop_target.setObjectName('workspace.emptyDropTarget')
        self._drop_target.setFeatures(qt.QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self._drop_target.toggleViewAction().setVisible(False)
        self._drop_target.setAllowedAreas(_DOCK_AREAS)
        empty_header = qt.QWidget(self._drop_target)
        empty_layout = qt.QHBoxLayout(empty_header)
        empty_layout.setContentsMargins(2, 0, 2, 0)
        empty_layout.addStretch()
        self.empty_new_button = _tab_button('+', 'New tab', empty_header, lambda: self.request_new_view())
        self.empty_new_button.setVisible(allow_new_tabs)
        empty_layout.addWidget(self.empty_new_button)
        empty_header.setFixedHeight(30)
        self._drop_target.setTitleBarWidget(empty_header)
        hint = qt.QLabel('Open a tab with +, or drop a detached tab here to return it to this window.')
        hint.setWordWrap(True)
        hint.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        hint.setForegroundRole(qt.QPalette.ColorRole.PlaceholderText)
        hint.setMinimumSize(200, 150)
        hint.setAccessibleName('Empty workspace docking area')
        self._drop_target.setWidget(hint)
        _workspaces.add(self)
        self.setDockOptions(qt.QMainWindow.DockOption.AllowTabbedDocks |
                            qt.QMainWindow.DockOption.AllowNestedDocks |
                            qt.QMainWindow.DockOption.AnimatedDocks)
        qt.QApplication.instance().focusChanged.connect(self._focus_changed)
        self.setTabPosition(qt.Qt.DockWidgetArea.AllDockWidgetAreas, qt.QTabWidget.TabPosition.North)
        self.new_action = qt.QAction('New tab', self)
        self.new_action.triggered.connect(lambda: self.request_new_view())
        self.addAction(self.new_action)
        self.new_action.setShortcut(qt.QKeySequence(qt.QKeySequence.StandardKey.AddTab))
        self.new_action.setShortcutContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.new_action.setEnabled(allow_new_tabs)
        self.close_action = qt.QAction('Close tab', self)
        self.close_action.triggered.connect(self.close_active)
        self.addAction(self.close_action)
        self.close_action.setShortcut(qt.QKeySequence(qt.QKeySequence.StandardKey.Close))
        self.close_action.setShortcutContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        # Retain programmatic actions and layout operations without a button row.
        self.reattach_action = qt.QAction('Reattach', self)
        self.reattach_action.triggered.connect(self.reattach_active)
        self.installEventFilter(self)
        self.active_changed.connect(self._sync_document_menus)
        self._update_drop_target()

    def _sync_document_menus(self, view):
        # Adoption activates the first tab before its new container is shown.
        if self.isVisible() or self.is_detached:
            from .workspace_menus import sync_native_menus
            sync_native_menus(self.window(), view if isinstance(view, qt.QMainWindow) else getattr(view, 'document', None))

    def _schedule_tab_headers(self):
        if not self._headers_pending:
            self._headers_pending = True
            qt.QTimer.singleShot(0, self._refresh_tab_headers)

    def _tab_dock(self, bar, index):
        # Native dock bars store the dock's C++ identity. Compare identities only;
        # never dereference Qt's private tab data or replace it with our own data.
        from shiboken6 import getCppPointer
        identity = bar.tabData(index)
        return next((dock for dock in self.docks if getCppPointer(dock)[0] == identity), None)

    def _refresh_tab_headers(self):
        self._headers_pending = False
        if self._closing:
            return
        for dock in self.docks:
            grouped = not dock.isFloating() and bool(self.tabifiedDockWidgets(dock))
            visible = self.policy is None or header_visible(self.policy, len(self.docks), self.is_detached)
            height = 30 if visible and not grouped else 0
            self._refresh_view_controls(dock, not visible)
            if dock.tab_header.minimumHeight() != height or dock.tab_header.maximumHeight() != height:
                dock.tab_header.setFixedHeight(height)
            dock.tab_header.close_button.setVisible(self.can_close_tab(dock))
            dock.tab_header.close_button.setEnabled(self.can_close_tab(dock))
        for bar in self.findChildren(qt.QTabBar):
            # Limit styling to Qt's dock bars, leaving views' own tab widgets alone.
            if bar.parent() is not self or not bar.count() or not self._tab_dock(bar, 0):
                continue
            visible = self.policy is None or header_visible(self.policy, bar.count(), self.is_detached)
            bar.setFixedHeight(30 if visible else 0)
            bar.setVisible(visible)
            bar.installEventFilter(self)
            bar.setExpanding(False)
            bar.setMovable(True)
            self._tab_order_changed(bar)
            bar.setElideMode(qt.Qt.TextElideMode.ElideRight)
            bar.setUsesScrollButtons(True)
            if not hasattr(bar, 'workspace_plus'):
                bar.workspace_style = _DockTabStyle()
                bar.workspace_style.setParent(bar)
                bar.setStyle(bar.workspace_style)
                bar.workspace_plus = _tab_button('+', 'New tab', bar, lambda: self.request_new_view())
                bar.currentChanged.connect(self._schedule_tab_headers)
                bar.tabMoved.connect(lambda source, target, owner=bar: self._tab_order_changed(owner))
                bar.currentChanged.connect(lambda index, owner=bar: self._activate(self._tab_dock(owner, index)))
            if self.active_dock in [self._tab_dock(bar, index) for index in range(bar.count())]:
                self._activate(self._tab_dock(bar, bar.currentIndex()))
            reserve = 32 if self.allow_new_tabs else 0
            width = max(60, (bar.width() - reserve) // bar.count())
            style = (f'QTabBar::tab {{ width: {width}px; height: 30px; padding: 0px; }} '
                     'QTabBar::scroller { width: 96px; } '
                     'QTabBar::tab:selected { background: palette(base); color: palette(text); '
                     'border-bottom: 3px solid palette(highlight); font-weight: bold; }')
            if bar.styleSheet() != style:
                bar.setStyleSheet(style)
            for index in range(bar.count()):
                dock = self._tab_dock(bar, index)
                if dock is None:
                    continue
                button = bar.tabButton(index, qt.QTabBar.ButtonPosition.LeftSide)
                if button is None:
                    button = _tab_button('×', 'Close tab', bar)
                    button.clicked.connect(lambda checked=False, owner=button: owner.dock.close())
                    bar.setTabButton(index, qt.QTabBar.ButtonPosition.LeftSide, button)
                button.dock = dock
                button.setVisible(self.can_close_tab(dock))
                button.setEnabled(self.can_close_tab(dock))
            arrows = [bar.findChild(qt.QToolButton, name)
                      for name in ('ScrollLeftButton', 'ScrollRightButton')]
            overflow = all(arrow is not None and arrow.isVisible() for arrow in arrows)
            # Keep + available even when native overflow arrows appear. Qt reserves
            # 96 pixels for these controls; the remaining tabs scroll as usual.
            for index, arrow in enumerate(arrows):
                if arrow is not None:
                    if not hasattr(arrow, 'workspace_connected'):
                        arrow.clicked.connect(self._schedule_tab_headers)
                        arrow.workspace_connected = True
                    if overflow:
                        arrow.setFixedSize(28, 28)
                        arrow.move(bar.width() - 62 + index * 32, 1)
            bar.workspace_plus.move(bar.width() - (94 if overflow else 30), max(0, (bar.height() - 28) // 2))
            bar.workspace_plus.setVisible(self.allow_new_tabs)
            bar.workspace_plus.raise_()

    def _tab_order_changed(self, bar):
        group = [self._tab_dock(bar, index) for index in range(bar.count())]
        group = [dock for dock in group if dock is not None]
        positions = [index for index, dock in enumerate(self.docks) if dock in group]
        changed = any(self.docks[index] is not dock for index, dock in zip(positions, group))
        for index, dock in zip(positions, group):
            self.docks[index] = dock
        if changed:
            self._schedule_tab_headers()

    def eventFilter(self, watched, event):
        if isinstance(watched, WorkspaceDock) and self.handle_tab_drop(watched, event):
            return True
        if watched is self or isinstance(watched, qt.QTabBar) and watched.parent() is self:
            if event.type() in (qt.QEvent.Type.Resize, qt.QEvent.Type.LayoutRequest):
                self._schedule_tab_headers()
            if isinstance(watched, qt.QTabBar) and event.type() == qt.QEvent.Type.ContextMenu:
                dock = self._tab_dock(watched, watched.tabAt(event.pos()))
                if dock:
                    event.accept()
                    menu = qt.QMenu(watched)
                    self.populate_tab_menu(menu, dock)
                    menu.exec(event.globalPos())
                    menu.deleteLater()
                    return True
            if isinstance(watched, qt.QTabBar):
                if event.type() == qt.QEvent.Type.MouseButtonPress and event.button() == qt.Qt.MouseButton.LeftButton:
                    self._drag_press = (watched, event.position().toPoint(), self._tab_dock(watched, watched.tabAt(event.position().toPoint())))
                elif event.type() == qt.QEvent.Type.MouseButtonRelease:
                    self._drag_press = None
                elif event.type() == qt.QEvent.Type.MouseMove and self._drag_press:
                    bar, start, dock = self._drag_press
                    point = event.position().toPoint()
                    if (dock and event.buttons() & qt.Qt.MouseButton.LeftButton
                            and (point - start).manhattanLength() >= qt.QApplication.startDragDistance()
                            and not bar.rect().contains(point)):
                        self._drag_press = None
                        self.begin_window_drag(dock, event.globalPosition().toPoint(), bar.mapToGlobal(start))
                        return True
        return super().eventFilter(watched, event)

    def _hide_drop_target(self):
        self._drop_target.hide()
        self.removeDockWidget(self._drop_target)

    def _update_drop_target(self):
        """Give Qt a full-size native docking anchor when all real views are floating.

        Run after native docking completes: changing dock layout inside Qt's
        topLevelChanged signal would disturb an in-progress native drop.
        """
        floating = [dock for dock in self.all_docks if dock.is_detached] if self.policy is not None else [dock for dock in self.docks if dock.isFloating()]
        self._schedule_tab_headers()
        self.reattach_action.setEnabled(bool(floating) and not self._closing)
        if self._closing or any(not dock.isFloating() for dock in self.docks):
            self._hide_drop_target()
        else:
            self.addDockWidget(qt.Qt.DockWidgetArea.LeftDockWidgetArea, self._drop_target)
            self._drop_target.show()

    def _docking_changed(self, floating):
        qt.QTimer.singleShot(0, self._update_drop_target)

    def _dock_location_changed(self, dock, area):
        if area == qt.Qt.DockWidgetArea.TopDockWidgetArea:
            # Wait for Qt to finish its native drop before changing the layout.
            qt.QTimer.singleShot(0, lambda: dock.workspace._finish_top_docking(dock))

    def _finish_top_docking(self, dock):
        if (self._closing or dock not in self.docks or dock.isFloating()
                or self.dockWidgetArea(dock) != qt.Qt.DockWidgetArea.TopDockWidgetArea):
            return
        anchor = self._docked_anchor(excluding=dock)
        if anchor and self.dockWidgetArea(anchor) == qt.Qt.DockWidgetArea.TopDockWidgetArea:
            # A whole tab group may arrive together. Move its anchor too, so
            # tabifying cannot put the returning dock back into the top area.
            self.addDockWidget(qt.Qt.DockWidgetArea.LeftDockWidgetArea, anchor)
        self.adopt(dock)

    def _docked_anchor(self, excluding=None):
        if self.active_dock is not excluding and self.active_dock and not self.active_dock.isFloating():
            return self.active_dock
        return next((dock for dock in self.docks if dock is not excluding and not dock.isFloating()), None)

    @property
    def active_view(self):
        return self.active_dock.widget() if self.active_dock else None

    @property
    def all_docks(self):
        main = self.main_workspace
        return list(main.docks) + [dock for window in main.detached_windows
                                   if isValid(window) for dock in window.workspace.docks]

    def request_new_view(self):
        if not self.allow_new_tabs or self._closing:
            return None
        return self.new_view(self) if self.new_view is not None else self.add_view()

    def _refresh_view_controls(self, dock, single):
        layout = getattr(dock.widget(), 'workspace_controls', None)
        if layout is None:
            return
        if not hasattr(dock, 'workspace_buttons'):
            dock.workspace_buttons = qt.QWidget(dock.widget())
            row = qt.QHBoxLayout(dock.workspace_buttons)
            row.setContentsMargins(0, 0, 0, 0)
            dock.return_button = _tab_button('↩', 'Dock to Main Window', dock.workspace_buttons,
                                            lambda: dock.workspace.return_to_main(dock))
            dock.local_new_button = _tab_button('+', 'New tab', dock.workspace_buttons,
                                                lambda: dock.workspace.request_new_view())
            row.addWidget(dock.return_button)
            row.addWidget(dock.local_new_button)
            layout.addWidget(dock.workspace_buttons)
        dock.return_button.setVisible(self.is_detached and self.can_move_tab(dock))
        dock.local_new_button.setVisible(self.allow_new_tabs)
        dock.workspace_buttons.setVisible(single and (self.allow_new_tabs or self.is_detached))
        controls_widget = getattr(dock.widget(), 'workspace_controls_widget', None)
        if controls_widget is not None:
            controls_widget.setVisible(single and (self.allow_new_tabs or self.is_detached))

    def populate_tab_menu(self, menu, dock):
        action = menu.addAction('Close tab', dock.close)
        if self.policy is not None:
            action.setEnabled(self.can_close_tab(dock))
        if self.policy is not None:
            if self.is_detached:
                menu.addAction('Dock to Main Window', lambda: self.return_to_main(dock)).setEnabled(self.can_move_tab(dock))
            else:
                menu.addAction('Detach tab', lambda: self.detach_dock(dock)).setEnabled(self.can_move_tab(dock))

    def can_move_tab(self, dock, *, destination=None):
        if self._closing or dock not in self.docks:
            return False
        if destination is self:
            return True
        return self.is_detached or self.policy is None or self.policy.allow_last_tab_detach or len(self.docks) > 1

    def toggle_detach(self, dock):
        if self.policy is None:
            dock.setFloating(not dock.isFloating())
            dock.show()
        elif self.is_detached:
            self.return_to_main(dock)
        else:
            self.detach_dock(dock)

    def detach_dock(self, dock):
        if not self.can_move_tab(dock):
            return None
        if self.policy is None:
            dock.setFloating(True)
            dock.show()
            return dock
        from .workspace_window import WorkspaceWindow
        main = self.main_workspace
        window = WorkspaceWindow(main)
        main.detached_windows.append(window)
        window.destroyed.connect(lambda: main.detached_windows.remove(window)
                                 if window in main.detached_windows else None)
        if not window.workspace.adopt(dock):
            window.deleteLater()
            return None
        window.show()
        window.raise_()
        window.update_title()
        return window

    def _cleanup_empty_container(self):
        if self.is_detached and not self.docks and not self._retiring and not self._transferring:
            qt.QTimer.singleShot(0, self, self._close_empty_container)

    def _close_empty_container(self):
        if not self.docks and not self._retiring and not self._transferring:
            self.window().close()

    def add_view(self, argument=None):
        if self._closing or (self.policy and self.policy.max_tabs is not None
                             and len(self.docks) >= self.policy.max_tabs):
            return None
        view = self.factory(argument)
        dock = WorkspaceDock(self, view, getattr(view, 'view_title', 'View'))
        previous = self._docked_anchor()
        self._hide_drop_target()
        self.docks.append(dock)
        self.addDockWidget(qt.Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        if previous:
            self.tabifyDockWidget(previous, dock)
        dock.topLevelChanged.connect(lambda floating: dock.workspace._docking_changed(floating))
        dock.dockLocationChanged.connect(lambda area: dock.workspace._dock_location_changed(dock, area))
        dock.visibilityChanged.connect(lambda visible: dock.workspace._activate(dock) if visible else None)
        dock.windowTitleChanged.connect(lambda title: dock.workspace.tabs_changed.emit())
        signal = getattr(view, 'title_changed', None)
        if signal is not None:
            signal.connect(dock.setWindowTitle)
        signal = getattr(view, 'idle', None)
        if signal is not None:
            signal.connect(lambda: dock.workspace._retry_view_close(dock))
        dock.show()
        dock.raise_()
        self._activate(dock)
        self._update_drop_target()
        self.tabs_changed.emit()
        return view

    def _activate(self, dock):
        if self._transferring:
            return
        if dock in self.docks and dock is not self.active_dock:
            # Repolishing can emit visibility/focus changes for an obscured dock.
            # Qt's selected native tab remains the authority for that group.
            if not dock.isFloating():
                for bar in self.findChildren(qt.QTabBar):
                    if bar.parent() is self and any(self._tab_dock(bar, index) is dock for index in range(bar.count())):
                        if self._tab_dock(bar, bar.currentIndex()) is not dock:
                            return
            self.active_dock = dock
            self.active_changed.emit(dock.widget())

    def _focus_changed(self, old, current):
        if current is None:
            return
        for dock in self.docks:
            if current is dock.widget() or dock.widget().isAncestorOf(current):
                self._activate(dock)
                break

    def detach_active(self):
        if self.active_dock:
            return self.detach_dock(self.active_dock)

    def reattach_active(self):
        if self.policy is not None:
            dock = self.active_dock if self.is_detached else next(
                (item for item in reversed(self.all_docks) if item.workspace is not self), None)
        else:
            dock = self.active_dock if self.active_dock and self.active_dock.isFloating() else next(
                (item for item in reversed(self.docks) if item.isFloating()), None)
        if dock:
            self.return_to_main(dock)

    def arrange(self, dock, placement, anchor=None):
        if dock is None or dock not in self.docks:
            return
        other = anchor if anchor is not dock else None
        other = other or self._docked_anchor(excluding=dock)
        self._hide_drop_target()
        qt.QDockWidget.setFloating(dock, False)
        if other is None:
            self.addDockWidget(qt.Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        elif placement == 'tabs':
            self.tabifyDockWidget(other, dock)
        else:
            # Qt treats splitDockWidget's first argument as a whole tab group.
            # Remove both anchors to dissolve that group before splitting them.
            self.removeDockWidget(dock)
            self.removeDockWidget(other)
            first, second = (dock, other) if placement == 'left' else (other, dock)
            self.addDockWidget(qt.Qt.DockWidgetArea.LeftDockWidgetArea, first)
            self.addDockWidget(qt.Qt.DockWidgetArea.LeftDockWidgetArea, second)
            first.show()
            second.show()
            self.splitDockWidget(first, second, qt.Qt.Orientation.Horizontal)
        dock.show()
        dock.raise_()
        self._activate(dock)

    def adopt(self, dock, *, force=False, placement='tabs', anchor=None):
        """Transfer an existing dock atomically; rollback restores its previous owner.

        force is reserved for explicit return/container close, so a last browser
        tab can return home without permitting its source to become orphaned.
        """
        if (not isValid(self) or self._closing or not isValid(dock) or not isValid(dock.workspace)
                or dock.workspace._closing or placement not in ('tabs', 'left', 'right')
                or (anchor is not None and (anchor not in self.docks or anchor is dock))
                or self.dock_group != dock.workspace.dock_group):
            return False
        source = dock.workspace
        if (source is not self and self.policy and self.policy.max_tabs is not None
                and len(self.docks) >= self.policy.max_tabs):
            return False
        if dock not in source.docks or (source is not self and not force
                                       and not source.can_move_tab(dock, destination=self)):
            return False
        if source is self:
            state, active = self.saveState(), self.active_dock
            try:
                self.arrange(dock, placement, anchor=anchor)
            except Exception:
                self.restoreState(state)
                self.active_dock = active
                return False
            self._update_drop_target()
            return True
        index, active = source.docks.index(dock), source.active_dock
        state = source.saveState()
        destination_state = self.saveState()
        floating, geometry = dock.isFloating(), dock.geometry()
        previous = self._docked_anchor()
        source._transferring = self._transferring = True
        try:
            # Suppress Qt's transient visibility changes while ownership changes.
            with qt.QSignalBlocker(dock):
                source.removeDockWidget(dock)
                source.docks.remove(dock)
                dock.removeEventFilter(source)
                dock.setParent(self)
                dock.workspace = self
                dock.installEventFilter(self)
                self.docks.append(dock)
                self._hide_drop_target()
                self.addDockWidget(qt.Qt.DockWidgetArea.LeftDockWidgetArea, dock)
                qt.QDockWidget.setFloating(dock, False)
                if previous and placement == 'tabs':
                    self.tabifyDockWidget(previous, dock)
                if placement != 'tabs':
                    self.arrange(dock, placement, anchor=anchor or previous)
                if dock.parentWidget() is not self or dock not in self.docks:
                    raise RuntimeError('Destination did not retain the tab')
        except Exception:
            if dock in self.docks:
                self.docks.remove(dock)
            self.removeDockWidget(dock)
            self.restoreState(destination_state)
            dock.removeEventFilter(self)
            dock.setParent(source)
            dock.workspace = source
            dock.installEventFilter(source)
            if dock not in source.docks:
                source.docks.insert(index, dock)
            source.addDockWidget(qt.Qt.DockWidgetArea.LeftDockWidgetArea, dock)
            source.restoreState(state)
            qt.QDockWidget.setFloating(dock, floating)
            dock.setGeometry(geometry)
            source.active_dock = active
            dock.show()
            return False
        finally:
            source._transferring = self._transferring = False
            source._update_drop_target()
            self._update_drop_target()
        if source.active_dock is dock:
            source.active_dock = source.docks[min(index, len(source.docks)-1)] if source.docks else None
            if source.active_dock:
                source.active_dock.raise_()
            source.active_changed.emit(source.active_view)
        dock.show()
        dock.raise_()
        self._activate(dock)
        dock.owner_changed.emit(self)
        source.tabs_changed.emit()
        self.tabs_changed.emit()
        source._cleanup_empty_container()
        return True

    def return_to_main(self, dock):
        main = self.main_workspace
        restore = main.reveal_for_drop(main.window().frameGeometry().center())
        accepted = main.adopt(dock)
        if not accepted and callable(restore):
            restore()
        return accepted

    def reveal_for_drop(self, point):
        """Reveal a destination; return an undo callback for an abandoned preview."""
        main = self.main_workspace
        if main.drop_reveal is not None and main.window().frameGeometry().contains(point):
            return main.drop_reveal()
        if self.is_detached:
            return main.reveal_for_drop(point)

    def can_close_tab(self, dock):
        if dock not in self.docks:
            return False
        if self._closing or not self.keep_one_tab or (self.policy is None and dock.isFloating()):
            return True
        return sum(not item.isFloating() for item in self.docks) > 1

    def close_active(self):
        if self.active_dock:
            self.active_dock.close()

    def _retry_view_close(self, dock):
        if dock in self._retiring:
            if getattr(dock.widget(), 'prepare_close', lambda: True)():
                self._retiring.remove(dock)
                dock.deleteLater()
                self._cleanup_empty_container()
                if self._closing:
                    self.window().close()
            return
        if dock not in self.docks:
            return
        if self._closing:
            self.window().close()
        elif getattr(dock.widget(), 'closing', False):
            dock.close()

    def remove_view(self, dock):
        self.docks.remove(dock)
        self.removeDockWidget(dock)
        if self.active_dock is dock:
            self.active_dock = self.docks[-1] if self.docks else None
            if self.active_dock:
                self.active_dock.raise_()
            self.active_changed.emit(self.active_view)
        self._update_drop_target()
        self.tabs_changed.emit()
        self._cleanup_empty_container()

    def retire_view(self, dock):
        """Remove the visible tab immediately, retaining its worker owners until idle."""
        if dock not in self.docks:
            return
        self._retiring.append(dock)
        dock.hide()
        self.remove_view(dock)

    def prepare_close(self):
        self._closing = True
        self._update_drop_target()
        ready = True
        windows = self.detached_windows if self.main_workspace is self else []
        for window in tuple(windows):
            if isValid(window) and not window.workspace.prepare_close():
                ready = False
        for dock in tuple(self.docks + self._retiring):
            if not getattr(dock.widget(), 'prepare_close', lambda: True)():
                ready = False
        return ready

    def closeEvent(self, event):
        if self.prepare_close():
            event.accept()
        else:
            event.ignore()
