"""Typed INI settings stay Logistics-owned and preserve explicit-save behavior."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import patch

from commonUtils.ui import pyside as qt
from commonUtils.ui.ini_editor import INISettingsEditor
from commonUtils.configuration.ini_schema import key_type, parse_value, string_list, validate_values
from commonUtils.fileTypes.iniType import INIFile


class SchemaTests(QtTestCase):
    def test_scalar_list_and_mode_types(self):
        self.assertEqual(key_type('count_list-int'), ('count', 'list-int'))
        self.assertEqual(parse_value('int', '9000000000'), 9000000000)
        self.assertEqual(parse_value('float', '1.25'), 1.25)
        self.assertTrue(parse_value('bool', 'true'))
        self.assertEqual(string_list('[choiceA,choiceB]'), ['choiceA', 'choiceB'])
        self.assertEqual(string_list('["a,b", "c"]'), ['a,b', 'c'])
        self.assertEqual(parse_value('list-int', '[1,2]'), [1,2])
        self.assertEqual(parse_value('list-float', '[1,2.5]'), [1,2.5])
        self.assertEqual(parse_value('mode', 'a', choices=['a','b']), 'a')

    def test_invalid_types_are_rejected_without_coercion(self):
        for kind, value in [('int','1.2'), ('float','nan'), ('bool','maybe'),
                            ('list-int','[true]'), ('list-str','[1]'),
                            ('list-float','[NaN]'), ('list-bool','[1]')]:
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                parse_value(kind, value)
        with self.assertRaisesRegex(ValueError, 'Choose'):
            validate_values(INIFile.parse('[S]\nview_mode=c\nview_choices_list-str=[a,b]\n'))


class EditorTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'config.ini'
        self.original = '# keep me\n[General]\ncount_int = 2\non_bool = true\nview_mode = a\nview_choices_list-str = [a,b]\n\n[Other]\nlegacy = value\n'
        self.path.write_text(self.original)
        self.editor = INISettingsEditor(self.path, typed_keys=True)
        self.addCleanup(self.editor.deleteLater)

    def test_tabs_controls_and_explicit_save(self):
        self.assertEqual(self.editor.sections.count(), 2)
        self.assertIsInstance(self.editor.fields['General','on_bool'], qt.QCheckBox)
        combo = self.editor.fields['General','view_mode']
        self.assertIsInstance(combo, qt.QComboBox)
        combo.setCurrentText('b')
        self.editor.fields['General','count_int'].setText('9000000000')
        self.assertEqual(self.path.read_text(), self.original)
        self.assertTrue(self.editor.is_modified)
        self.assertTrue(self.editor.save())
        self.assertIn('# keep me', self.path.read_text())
        self.assertEqual(INIFile(self.path).read().get('General','count_int'), '9000000000')

    def test_invalid_field_blocks_save_and_source_switch_until_fixed(self):
        self.editor.fields['General','count_int'].setText('wrong')
        self.assertFalse(self.editor.save())
        self.editor.tabs.setCurrentIndex(1)
        self.assertEqual(self.editor.tabs.currentIndex(), 0)
        self.assertEqual(self.path.read_text(), self.original)
        self.editor.fields['General','count_int'].setText('4')
        self.assertTrue(self.editor.save())

    def test_source_edits_refresh_forms_and_validate_before_save(self):
        self.editor.tabs.setCurrentIndex(1)
        self.editor.text.setPlainText('[General]\ncount_int = 5\n')
        self.editor.tabs.setCurrentIndex(0)
        self.assertEqual(self.editor.fields['General','count_int'].text(), '5')
        self.editor.tabs.setCurrentIndex(1)
        self.editor.text.setPlainText('[General]\ncount_int = wrong\n')
        self.editor.text.document().setModified(True)
        self.assertFalse(self.editor.save())
        self.assertEqual(self.path.read_text(), self.original)

    def test_invalid_ini_has_source_fallback(self):
        self.path.write_text('invalid INI')
        editor = INISettingsEditor(self.path, typed_keys=True)
        self.addCleanup(editor.deleteLater)
        self.assertEqual(editor.tabs.currentIndex(), 1)
        self.assertIn('Source', editor.status.text())
        self.assertFalse(editor.save())

    def test_external_changes_and_unsaved_cancel(self):
        self.editor.fields['General','count_int'].setText('8')
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel):
            self.assertFalse(self.editor.can_close())
        self.path.write_text('[External]\nkey = value\n')
        self.assertFalse(self.editor.save())
        self.assertIn('[External]', self.path.read_text())

    def test_untyped_editor_does_not_interpret_suffixes(self):
        self.path.write_text('[S]\nquantity_int = not a number\non_bool = maybe\n')
        editor = INISettingsEditor(self.path)
        self.addCleanup(editor.deleteLater)
        self.assertIsInstance(editor.fields['S','on_bool'], qt.QLineEdit)
        editor.fields['S','quantity_int'].setText('still text')
        self.assertTrue(editor.save())
        self.assertEqual(INIFile(self.path).read().get('S','quantity_int'), 'still text')


if __name__ == '__main__':
    unittest.main()
