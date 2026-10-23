"""Settings scope navigation retains live controls and avoids redundant nesting."""
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.settings.settings_sections import ScopedSettings, SettingsSection


class SettingsSectionsTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.panel = ScopedSettings()
        self.panel.resize(700, 500)
        self.panel.show()
        self.addCleanup(self.panel.deleteLater)

    def test_single_custom_panel_is_direct_but_ini_keeps_its_section(self):
        credentials = qt.QLineEdit('kept')
        ini = qt.QLineEdit('unsaved config')
        self.panel.set_sections([SettingsSection('personal', 'credentials', 'Credential packages', credentials),
                                 SettingsSection('application', 'ini', 'INI files', ini, nested=True)])
        self.assertEqual([self.panel.tabs.tabText(i) for i in range(2)], ['Application Settings', 'Personal'])
        personal = self.panel.pages['personal']
        self.assertIs(personal.direct, credentials)
        self.assertEqual(personal.tabs.count(), 0)
        self.assertEqual(self.panel.pages['application'].tabs.tabText(0), 'INI files')

    def test_hidden_scope_keeps_selected_section_and_state_across_updates(self):
        first, second, ini = qt.QLineEdit('first'), qt.QLineEdit('second'), qt.QLineEdit('ini')
        sections = [SettingsSection('application', 'ini', 'INI files', ini, nested=True),
                    SettingsSection('personal', 'first', 'First', first),
                    SettingsSection('personal', 'second', 'Second', second)]
        self.panel.set_sections(sections)
        personal = self.panel.pages['personal']
        personal.tabs.setCurrentWidget(second)
        second.setText('pending edits')
        self.panel.set_sections(sections + [SettingsSection('application', 'extra', 'Extra', qt.QLabel('extra'))])
        self.assertIs(personal.tabs.currentWidget(), second)
        self.assertEqual(second.text(), 'pending edits')
        self.panel.set_sections(sections[:1])
        self.assertEqual(self.panel.tabs.count(), 1)
        self.panel.set_sections(sections)
        self.assertEqual(second.text(), 'pending edits')

    def test_ambiguous_scopes_and_duplicate_sections_are_rejected(self):
        section = SettingsSection('application', 'ini', 'INI files', qt.QWidget())
        with self.assertRaises(ValueError):
            self.panel.set_sections([section, section])
        with self.assertRaises(ValueError):
            self.panel.set_sections([SettingsSection('unknown', 'other', 'Other', qt.QWidget())])
