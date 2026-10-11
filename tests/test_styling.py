"""Live font roles, Markdown code, palette contrast and per-field inheritance."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.styling import styling, STYLE_FIELDS
from commonUtils.ui.theme import configured_colors
from commonUtils.ui.layered_settings import LayeredSettingsEditor
from commonUtils.configuration.layered import register_settings
from commonUtils.configuration.settings import settings_path


class StylingTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.defaults = self.root / 'defaults.ini'
        self.defaults.write_bytes(settings_path().read_bytes())
        self.store = register_settings(self.defaults, self.root / 'personal.ini')
        patcher = patch('commonUtils.configuration.settings.settings_path', return_value=self.defaults)
        patcher.start(); self.addCleanup(patcher.stop)
        self.previous = getattr(self.app, '_commonutils_styling', None)
        if self.previous:
            self.previous.timer.stop()
            del self.app._commonutils_styling
        self.controller = styling()
        self.controller.timer.stop()
        self.addCleanup(self._restore)

    def _restore(self):
        self.controller.timer.stop()
        self.controller.deleteLater()
        if self.previous:
            self.app._commonutils_styling = self.previous
            self.previous.timer.start()
        else:
            del self.app._commonutils_styling

    def test_code_and_reading_fonts_update_live_and_keep_text_and_modified_state(self):
        from commonUtils.ui.code_editor import CodeEdit
        from commonUtils.ui.markdown.presentation import configure_text, style_document
        editor = CodeEdit()
        reading = qt.QTextBrowser()
        for widget in (editor, reading):
            self.addCleanup(widget.deleteLater)
        editor.setPlainText('print(1)')
        editor.document().setModified(False)
        reading.setMarkdown('Read this.\n\n```python\nprint(1)\n```')
        configure_text(reading)
        style_document(reading.document(), reading.palette())
        reading.document().setModified(False)
        self.controller.code_font.bind(editor)
        original = reading.toPlainText()
        self.store.save({('Styling', 'reading_font_size_int'): '19', ('Styling', 'code_font_size_int'): '13',
                         ('Styling', 'code_font_family_str'): 'Courier New'})
        self.controller.reload()
        self.assertEqual(editor.font().pointSize(), 13)
        self.assertEqual(editor.font().family(), 'Courier New')
        self.assertEqual(reading.font().pointSize(), 19)
        self.assertEqual(reading.toPlainText(), original)
        self.assertFalse(editor.document().isModified())
        self.assertFalse(reading.document().isModified())
        block = reading.document().lastBlock()
        self.assertEqual(block.begin().fragment().charFormat().fontPointSize(), 13)
        self.assertEqual(block.begin().fragment().charFormat().fontFamilies(), ['Courier New'])

    def test_reset_removes_personal_key_and_default_editor_changes_repository_file(self):
        self.store.save({('Styling', 'code_font_size_int'): '17'})
        personal = LayeredSettingsEditor(self.store, scope='personal', sections=('Styling',))
        defaults = LayeredSettingsEditor(self.store, scope='application', sections=('Styling',))
        for widget in (personal, defaults):
            self.addCleanup(widget.deleteLater)
        identity = 'Styling', 'code_font_size_int'
        self.assertEqual(len(personal.fields), len(STYLE_FIELDS))
        self.assertEqual(personal.indicators[identity].text(), 'Override')
        personal.resets[identity].click()
        self.assertEqual(personal.fields[identity].value(), 11)
        self.assertEqual(personal.indicators[identity].text(), 'Inherited')
        self.assertTrue(personal.save())
        self.assertNotIn(identity, self.store.overrides())
        defaults.fields[identity].setValue(12)
        self.assertTrue(defaults.save())
        self.assertIn('code_font_size_int = 12', self.defaults.read_text())
        self.assertNotIn(identity, self.store.overrides())
        self.controller.reload()
        self.assertEqual(self.controller.code_font.size, 12)

    def test_accent_tints_dark_surfaces_and_selection_has_contrasting_text(self):
        self.store.save({('Styling', 'accent_color_str'): '#ff8800', ('Styling', 'dark_tint_int'): '20'})
        warm = configured_colors(True)
        self.assertEqual(warm.accent, '#ff8800')
        self.assertGreater(qt.QColor(warm.surface).red(), qt.QColor(warm.surface).blue())
        self.assertEqual(warm.selected_text, '#000000')
        self.store.save({('Styling', 'accent_color_str'): '#000044'})
        self.assertEqual(configured_colors(True).selected_text, '#ffffff')

    def test_invalid_color_and_conflicting_software_save_preserve_files(self):
        editor = LayeredSettingsEditor(self.store, scope='application', sections=('Styling',))
        self.addCleanup(editor.deleteLater)
        original = self.defaults.read_bytes()
        editor.fields['Styling', 'accent_color_str'].setText('not a color')
        self.assertFalse(editor.save())
        self.assertEqual(self.defaults.read_bytes(), original)
        editor.fields['Styling', 'accent_color_str'].setText('#123456')
        self.store.save({('Styling', 'code_font_size_int'): '14'}, scope='application')
        newer = self.defaults.read_bytes()
        self.assertFalse(editor.save())
        self.assertEqual(self.defaults.read_bytes(), newer)

    def test_live_styling_preserves_formatted_markdown_source_and_dirty_state(self):
        from commonUtils.ui.markdown.viewer import MarkdownViewer
        source = '---\ntitle: Preserve\n---\n\n# Heading\n\nRead **this** and `inline`.\n\n```python\nprint(1)\n```\n'
        path = self.root / 'source.md'
        path.write_text(source)
        viewer = MarkdownViewer(path, allow_edit=True)
        self.addCleanup(viewer.deleteLater)
        viewer.edit_button.setChecked(True)
        before = viewer.markdown_text()
        self.assertFalse(viewer.is_modified)
        self.store.save({('Styling', 'reading_font_size_int'): '18', ('Styling', 'code_font_size_int'): '14',
                         ('Styling', 'code_font_family_str'): 'Courier New'})
        self.controller.reload()
        self.assertEqual(viewer.markdown_text(), before)
        self.assertFalse(viewer.is_modified)
        self.assertEqual(path.read_text(), source)
