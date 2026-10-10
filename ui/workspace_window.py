"""A detached container owns tabs, while closing it restores them to its main host."""
from . import pyside as qt


class WorkspaceWindow(qt.QMainWindow):
    def __init__(self, main):
        super().__init__(main.window())
        from .workspace import Workspace
        self.setWindowFlag(qt.Qt.WindowType.Window, True)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.workspace = Workspace(main.factory, self, allow_new_tabs=main.allow_new_tabs,
                                   dock_group=main.dock_group, keep_one_tab=main.keep_one_tab,
                                   policy=main.policy, main_workspace=main,
                                   new_view=main.new_view, setup_container=main.setup_container)
        self.setCentralWidget(self.workspace)
        self.workspace.close_action.setEnabled(main.close_action.isEnabled())
        self.resize(1000, 700)
        self.workspace.active_changed.connect(self.update_title)
        self.workspace.tabs_changed.connect(self.update_title)
        if main.setup_container is not None:
            main.setup_container(self.workspace)

    def update_title(self, *args):
        dock = self.workspace.active_dock
        title = dock.windowTitle() if dock else ''
        self.setWindowTitle(self.workspace.policy.detached_title.format(title=title))

    def closeEvent(self, event):
        main = self.workspace.main_workspace
        # A container close is not a tab close. Restore content without asking
        # readers to discard edits or stopping browser workers.
        if not main._closing:
            for dock in tuple(self.workspace.docks):
                if not main.adopt(dock, force=True):
                    event.ignore()
                    return
        if self.workspace.docks or self.workspace._retiring:
            event.ignore()
            return
        event.accept()
