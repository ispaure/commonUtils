"""Shared category sidebar and retained page stack, with host-owned categories."""
from ...runtime.platform.capabilities import Capability, require_capability

require_capability(Capability.QT_UI, 'ui.settings.navigation')

from PySide6.QtWidgets import QSplitter, QStackedWidget, QTreeWidget


class SettingsNavigation(QSplitter):
    """Hosts populate sidebar items and select retained pages in the stack.

    Keeping selection policy in the host permits lazy feature pages and static
    forms to use the same organization without sharing their persistence policy.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.sidebar = QTreeWidget(self)
        self.sidebar.setHeaderHidden(True)
        self.sidebar.setAccessibleName('Settings categories')
        self.stack = QStackedWidget(self)
        self.addWidget(self.sidebar)
        self.addWidget(self.stack)
        self.setStretchFactor(0, 0)
        self.setStretchFactor(1, 1)
        self.setChildrenCollapsible(False)
        self.setSizes([210, 650])
