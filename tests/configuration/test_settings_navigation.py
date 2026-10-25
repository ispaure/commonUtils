"""Category navigation keeps page ownership and selection policy with its host."""
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui.settings.navigation import SettingsNavigation
from PySide6.QtWidgets import QLineEdit, QTreeWidgetItem
from PySide6.QtCore import Qt


class SettingsNavigationTests(QtTestCase):
    def test_categories_switch_retained_pages_without_changing_edits(self):
        panel = SettingsNavigation()
        self.addCleanup(panel.deleteLater)
        first, second = QLineEdit('first'), QLineEdit('second')
        for index, field in enumerate((first, second)):
            panel.stack.addWidget(field)
            item = QTreeWidgetItem([str(index)])
            item.setData(0, Qt.ItemDataRole.UserRole, index)
            panel.sidebar.addTopLevelItem(item)
        panel.sidebar.currentItemChanged.connect(
            lambda item, previous: panel.stack.setCurrentIndex(item.data(0, Qt.ItemDataRole.UserRole)))
        first.setText('unsaved edit')
        panel.sidebar.setCurrentItem(panel.sidebar.topLevelItem(1))
        self.assertIs(panel.stack.currentWidget(), second)
        panel.sidebar.setCurrentItem(panel.sidebar.topLevelItem(0))
        self.assertEqual(first.text(), 'unsaved edit')
        self.assertFalse(panel.childrenCollapsible())
        self.assertEqual(panel.sidebar.accessibleName(), 'Settings categories')
