"""Mixed field callbacks keep sparse overrides and reset identities independent."""
from pathlib import Path
from unittest.mock import patch

from commonUtils.configuration.layered import LayeredSettings, read_values
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.settings.layered_settings import LayeredSettingsEditor


class LayeredSettingsEditorTests(QtTestCase):
    def test_save_retains_form_focus_scroll_and_conflict_baselines_in_both_scopes(self):
        app = qt.QApplication.instance() or qt.QApplication([])
        for scope in ('personal', 'application'):
            with self.subTest(scope=scope), self.temporary_directory() as directory:
                defaults, personal = (Path(directory) / name for name in ('defaults.ini', 'personal.ini'))
                defaults.write_text('[First]\nname_str = First\n[Other]\nname_str = Second\n' +
                                    ''.join(f'field_{i}_str = value\n' for i in range(35)))
                editor = LayeredSettingsEditor(LayeredSettings(defaults, personal), scope=scope)
                editor.resize(500, 300)
                editor.sections.setCurrentIndex(1)
                editor.show()
                field = editor.fields['Other', 'name_str']
                field.setText('Saved value')
                field.setFocus()
                field.setSelection(1, 4)
                app.processEvents()
                scroll = editor.sections.currentWidget().verticalScrollBar()
                scroll.setValue(30)
                position = scroll.value()
                self.assertGreater(position, 0)
                fields = dict(editor.fields)
                page = editor.sections.currentWidget()
                with patch.object(editor, '_build', wraps=editor._build) as build:
                    self.assertTrue(editor.save(), editor.status.text())
                    build.assert_not_called()
                app.processEvents()
                self.assertEqual(editor.fields, fields)
                self.assertIs(editor.sections.currentWidget(), page)
                self.assertIs(app.focusWidget(), field)
                self.assertEqual(field.selectedText(), 'aved')
                self.assertEqual(scroll.value(), position)
                self.assertFalse(editor.pending)
                self.assertFalse(editor.save_button.isEnabled())
                field.setText('Second save')
                self.assertTrue(editor.save(), editor.status.text())
                self.assertEqual(read_values(editor.path)['Other', 'name_str'], 'Second save')
                editor.resets['Other', 'name_str'].click()
                if scope == 'personal':
                    self.assertTrue(editor.save())
                    self.assertNotIn(('Other', 'name_str'), read_values(personal))
                    self.assertEqual(field.text(), 'Second')
                    self.assertEqual(editor.indicators['Other', 'name_str'].text(), 'Inherited')
                field.setText('Must not overwrite external edit')
                editor.path.write_text(editor.path.read_text() + '\n[External]\nname_str = external\n')
                self.assertFalse(editor.save())
                self.assertTrue(editor.pending)
                self.assertIn('reload', editor.status.text().lower())
                editor.pending.clear()
                self.assertTrue(editor.reload(initial=True))
                self.assertIsNot(editor.fields['Other', 'name_str'], field)

    def test_rejected_save_keeps_unsaved_text_and_controls(self):
        with self.temporary_directory() as directory:
            defaults, personal = (Path(directory) / name for name in ('defaults.ini', 'personal.ini'))
            defaults.write_text('[Options]\nname_str = initial\n')
            editor = LayeredSettingsEditor(LayeredSettings(defaults, personal))
            field = editor.fields['Options', 'name_str']
            field.setText('  trim outer whitespace  ')
            self.assertFalse(editor.save())
            self.assertIs(editor.fields['Options', 'name_str'], field)
            self.assertEqual(field.text(), '  trim outer whitespace  ')
            self.assertTrue(editor.pending)
            self.assertFalse(personal.exists())

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
