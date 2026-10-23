"""Mixed field callbacks keep sparse overrides and reset identities independent."""
from pathlib import Path

from commonUtils.configuration.layered import LayeredSettings, read_values
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.settings.layered_settings import LayeredSettingsEditor


class LayeredSettingsEditorTests(QtTestCase):
    def test_mixed_controls_and_resets_keep_their_section_and_field(self):
        app = qt.QApplication.instance() or qt.QApplication([])
        with self.temporary_directory() as directory:
            defaults, personal = (Path(directory) / name for name in ('defaults.ini', 'personal.ini'))
            defaults.write_text('[Options]\nenabled_bool = true\nname_str = First\n'
                                'choice_mode = one\nchoice_choices_list-str = ["one", "two"]\n'
                                'note_str = first\n second\n[Other]\nname_str = Second\n')
            personal.write_text('[Options]\nenabled_bool = false\n')
            original = defaults.read_bytes()
            editor = LayeredSettingsEditor(LayeredSettings(defaults, personal))
            self.assertEqual(editor.pending, {})
            self.assertNotIn(('Options', 'choice_choices_list-str'), editor.fields)
            editor.fields['Options', 'name_str'].setText('Options edit')
            editor.fields['Other', 'name_str'].setText('Other edit')
            editor.fields['Options', 'choice_mode'].setCurrentText('two')
            editor.fields['Options', 'note_str'].setPlainText('Multiple\nlines')
            editor.fields['Options', 'enabled_bool'].setChecked(True)
            editor.resets['Options', 'enabled_bool'].click()
            self.assertTrue(editor.fields['Options', 'enabled_bool'].isChecked())
            self.assertEqual(editor.pending, {
                ('Options', 'name_str'): 'Options edit', ('Other', 'name_str'): 'Other edit',
                ('Options', 'choice_mode'): 'two', ('Options', 'note_str'): 'Multiple\nlines',
                ('Options', 'enabled_bool'): None,
            })
            self.assertTrue(editor.save(), editor.status.text())
            self.assertEqual(read_values(personal), {
                ('Options', 'name_str'): 'Options edit', ('Other', 'name_str'): 'Other edit',
                ('Options', 'choice_mode'): 'two', ('Options', 'note_str'): 'Multiple\nlines',
            })
            self.assertEqual(defaults.read_bytes(), original)
            saved = personal.read_bytes()
            self.assertTrue(editor.save())
            self.assertEqual(personal.read_bytes(), saved)
            app.processEvents()
