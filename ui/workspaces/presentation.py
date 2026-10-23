"""Qt tab/header reconciliation separate from dock transfer and retirement."""
from .. import pyside as qt
from shiboken6 import isValid
from .workspace_policy import header_visible
from .headers import TAB_BUTTON_SIZE, TAB_HEADER_HEIGHT, TAB_PLUS_RESERVE, _DockTabStyle, _tab_button


class WorkspaceHeaderPresentation:
    def __init__(self, workspace):
        self.workspace = workspace
        self.pending = False

    def refresh(self):
        workspace = self.workspace
        if not isValid(workspace):
            return
        self.pending = False
        if workspace._closing:
            return
        for dock in workspace.docks:
            grouped = not dock.isFloating() and bool(workspace.tabifiedDockWidgets(dock))
            visible = workspace.policy is None or header_visible(workspace.policy, len(workspace.docks), workspace.is_detached)
            visible = visible or (workspace.allow_new_tabs and getattr(dock.widget(), 'workspace_controls', None) is None)
            height = TAB_HEADER_HEIGHT if visible and not grouped else 0
            self.view_controls(dock, not visible)
            if dock.tab_header.minimumHeight() != height or dock.tab_header.maximumHeight() != height:
                dock.tab_header.setFixedHeight(height)
            # Qt collapses dock title widgets instead of hiding them. Explicitly
            # hide their controls too; otherwise native layout transitions can
            # leave a child + painted at the header's default position.
            dock.tab_header.new_button.setVisible(height > 0 and workspace.allow_new_tabs)
            dock.tab_header.title.setVisible(height > 0)
            dock.tab_header.close_button.setVisible(height > 0 and workspace.can_close_tab(dock))
            dock.tab_header.close_button.setEnabled(workspace.can_close_tab(dock))
        for bar in workspace.findChildren(qt.QTabBar):
            # Limit styling to Qt's dock bars, leaving views' own tab widgets alone.
            if bar.parent() is not workspace:
                continue
            if not bar.count() or not workspace._tab_dock(bar, 0):
                if hasattr(bar, 'workspace_plus'):
                    bar.workspace_plus.hide()
                continue
            visible = workspace.policy is None or header_visible(workspace.policy, bar.count(), workspace.is_detached)
            bar.setFixedHeight(TAB_HEADER_HEIGHT if visible else 0)
            bar.setVisible(visible)
            bar.installEventFilter(workspace)
            bar.setExpanding(False)
            bar.setMovable(True)
            workspace._tab_order_changed(bar)
            bar.setElideMode(qt.Qt.TextElideMode.ElideRight)
            bar.setUsesScrollButtons(True)
            if not hasattr(bar, 'workspace_plus'):
                bar.workspace_style = _DockTabStyle()
                bar.workspace_style.setParent(bar)
                bar.setStyle(bar.workspace_style)
                bar.workspace_plus = _tab_button('+', 'New tab', bar, lambda: workspace.request_new_view())
                bar.currentChanged.connect(workspace._schedule_tab_headers)
                bar.tabMoved.connect(lambda source, target, owner=bar: workspace._tab_order_changed(owner))
                bar.currentChanged.connect(lambda index, owner=bar: workspace._activate(workspace._tab_dock(owner, index)))
            if workspace.active_dock in [workspace._tab_dock(bar, index) for index in range(bar.count())]:
                workspace._activate(workspace._tab_dock(bar, bar.currentIndex()))
            reserve = TAB_PLUS_RESERVE if workspace.allow_new_tabs else 0
            width = max(60, (bar.width() - reserve) // bar.count())
            style = (f'QTabBar::tab {{ width: {width}px; height: {TAB_HEADER_HEIGHT}px; padding: 0px; }} '
                     'QTabBar::scroller { width: 96px; } '
                     'QTabBar::tab:selected { background: palette(base); color: palette(text); '
                     'border-bottom: 3px solid palette(highlight); font-weight: bold; }')
            if bar.styleSheet() != style:
                bar.setStyleSheet(style)
            for index in range(bar.count()):
                dock = workspace._tab_dock(bar, index)
                if dock is None:
                    continue
                if dock.property('workspace_show_icon'):
                    bar.setTabIcon(index, dock.windowIcon())
                button = bar.tabButton(index, qt.QTabBar.ButtonPosition.RightSide)
                if button is None:
                    button = _tab_button('×', 'Close tab', bar)
                    button.clicked.connect(lambda checked=False, owner=button: owner.dock.close())
                    bar.setTabButton(index, qt.QTabBar.ButtonPosition.RightSide, button)
                button.dock = dock
                button.setVisible(workspace.can_close_tab(dock))
                button.setEnabled(workspace.can_close_tab(dock))
            arrows = [bar.findChild(qt.QToolButton, name)
                      for name in ('ScrollLeftButton', 'ScrollRightButton')]
            overflow = all(arrow is not None and arrow.isVisible() for arrow in arrows)
            # Keep + available even when native overflow arrows appear. Qt reserves
            # 96 pixels for these controls; the remaining tabs scroll as usual.
            for index, arrow in enumerate(arrows):
                if arrow is not None:
                    if not hasattr(arrow, 'workspace_connected'):
                        arrow.clicked.connect(workspace._schedule_tab_headers)
                        arrow.workspace_connected = True
                    if overflow:
                        arrow.setFixedSize(28, 28)
                        arrow.move(bar.width() - 62 + index * 32, 1)
            bar.workspace_plus.move(bar.width() - (94 if overflow else TAB_BUTTON_SIZE + 2), max(0, (bar.height() - TAB_BUTTON_SIZE) // 2))
            bar.workspace_plus.setVisible(visible and workspace.allow_new_tabs)
            bar.workspace_plus.raise_()


    def view_controls(self, dock, single):
        workspace = self.workspace
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
        dock.return_button.setVisible(workspace.is_detached and workspace.can_move_tab(dock))
        dock.local_new_button.setVisible(workspace.allow_new_tabs)
        dock.workspace_buttons.setVisible(single and (workspace.allow_new_tabs or workspace.is_detached))
        controls_widget = getattr(dock.widget(), 'workspace_controls_widget', None)
        if controls_widget is not None:
            controls_widget.setVisible(single and (workspace.allow_new_tabs or workspace.is_detached))

