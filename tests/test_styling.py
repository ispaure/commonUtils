"""Live font roles, Markdown code, palette contrast and per-field inheritance."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.appearance.styling import apply_styling, styling, STYLE_FIELDS, validate_style
from commonUtils.ui.appearance.theme import configured_colors
from commonUtils.ui.settings.layered_settings import LayeredSettingsEditor
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
            self.previous._settings_subscription.stop()
            del self.app._commonutils_styling
        self.controller = styling()
        self.code_families = [family for family in qt.QFontDatabase.families()
                              if qt.QFontDatabase.isFixedPitch(family)]
        self.controller._settings_subscription.stop()
        self.addCleanup(self._restore)

    def _restore(self):
        self.controller._settings_subscription.stop()
        self.controller.deleteLater()
        if self.previous:
            self.app._commonutils_styling = self.previous
            self.previous._settings_subscription.start()
        else:
            del self.app._commonutils_styling

    def _code_family(self, index=0):
        if not self.code_families:
            self.skipTest('No installed monospace fonts')
        return self.code_families[index % len(self.code_families)]

    def test_pending_font_previews_and_selected_fields_do_not_apply_or_save(self):
        if not self.code_families:
            self.skipTest('No installed monospace fonts')
        panel = LayeredSettingsEditor(self.store)
        self.addCleanup(panel.deleteLater)
        before = dict(self.controller.values)
        identity = 'Styling', 'code_font_family_str'
        field = panel.fields[identity]
        families = [field.itemData(index) for index in range(1, field.count())]
        self.assertEqual(families, self.code_families)
        family = families[0]
        field.setCurrentIndex(field.findData(family))
        panel.fields['Styling', 'code_font_size_int'].setValue(20)
        preview = panel.font_previews['code'].editor
        self.assertEqual(field.lineEdit().font().family(), family)
        self.assertEqual(preview.font().family(), family)
        self.assertEqual(preview.font().pointSize(), 20)
        self.assertEqual(self.controller.values, before)
        self.assertFalse(self.store.personal.exists())
        panel._reset(identity)
        panel._reset(('Styling', 'code_font_size_int'))
        self.assertFalse(panel.pending)
        self.assertEqual(preview.font().pointSize(), int(panel.defaults['Styling', 'code_font_size_int']))

    def test_code_fonts_reject_proportional_and_unknown_families(self):
        proportional = next((family for family in qt.QFontDatabase.families()
                             if not qt.QFontDatabase.isFixedPitch(family)), None)
        if proportional:
            with self.assertRaisesRegex(ValueError, 'monospace'):
                validate_style('code_font_family_str', proportional)
        validate_style('code_font_family_str', '')
        for family in self.code_families:
            validate_style('code_font_family_str', family)
        with self.assertRaisesRegex(ValueError, 'monospace'):
            validate_style('code_font_family_str', 'Missing font for test 123456')

    def test_buttons_follow_saved_roles_without_overwriting_pending_previews(self):
        panel = LayeredSettingsEditor(self.store)
        self.addCleanup(panel.deleteLater)
        browser = qt.QWidget()
        self.addCleanup(browser.deleteLater)
        self.controller.bind(browser, 'browser')
        sidebar = qt.QTreeWidget()
        self.addCleanup(sidebar.deleteLater)
        self.controller.bind(sidebar, 'ui')
        browser_button = qt.QPushButton('Refresh', browser)
        apply_styling(self.app)
        new_button = qt.QToolButton()
        self.addCleanup(new_button.deleteLater)
        new_button.ensurePolished()
        panel.ensurePolished()
        panel.fields['Styling', 'ui_font_family_str'].setEditText('Courier New')
        panel.fields['Styling', 'ui_font_size_int'].setValue(24)
        preview_buttons = panel.font_previews['ui'].findChildren(qt.QPushButton)
        self.store.save({('Styling', 'ui_font_family_str'): 'Georgia',
                         ('Styling', 'ui_font_size_int'): '18',
                         ('Styling', 'browser_font_family_str'): 'Arial',
                         ('Styling', 'browser_font_size_int'): '13'})
        self.controller.reload()
        self.app.processEvents()
        for button in (panel.save_button, panel.reload_button, new_button):
            self.assertEqual(button.font().family(), 'Georgia')
            self.assertEqual(button.font().pointSize(), 18)
        self.assertEqual(browser_button.font().family(), 'Arial')
        self.assertEqual(browser_button.font().pointSize(), 13)
        self.assertEqual(sidebar.font().family(), 'Georgia')
        self.assertEqual(sidebar.font().pointSize(), 18)
        self.assertEqual(browser.font().family(), 'Arial')
        self.assertEqual(browser.font().pointSize(), 13)
        self.assertTrue(preview_buttons)
        for button in preview_buttons:
            self.assertEqual(button.font().family(), 'Courier New')
            self.assertEqual(button.font().pointSize(), 24)
            self.assertNotIn(button, self.controller.views)

    def test_interface_fonts_reach_existing_and_new_menus_and_legacy_controls(self):
        from commonUtils.ui.appearance.theme import apply_theme
        menu = qt.QMenu('Existing')
        bar = qt.QMenuBar()
        for widget in (menu, bar):
            self.addCleanup(widget.deleteLater)
        apply_theme(self.app, mode='light')
        apply_styling(self.app)
        button = qt.QPushButton('Legacy')
        self.addCleanup(button.deleteLater)
        qt.set_font(button)
        self.store.save({('Styling', 'ui_font_family_str'): 'Courier New',
                         ('Styling', 'ui_font_size_int'): '18'})
        self.controller.reload()
        new_menu = qt.QMenu('New')
        self.addCleanup(new_menu.deleteLater)
        new_menu.ensurePolished()
        self.app.processEvents()
        for widget in (menu, bar, new_menu, button):
            self.assertEqual(widget.font().family(), 'Courier New', widget.metaObject().className())
            self.assertEqual(widget.font().pointSize(), 18)
        self.assertEqual(self.app.font().family(), 'Courier New')

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
        self.assertEqual(reading.document().lastBlock().begin().fragment().charFormat().fontFamilies(),
                         [editor.font().family()])
        original = reading.toPlainText()
        self.store.save({('Styling', 'reading_font_size_int'): '19', ('Styling', 'code_font_size_int'): '13',
                         ('Styling', 'code_font_family_str'): self._code_family()})
        self.controller.reload()
        self.assertEqual(editor.font().pointSize(), 13)
        self.assertEqual(editor.font().family(), self._code_family())
        self.assertEqual(reading.font().pointSize(), 19)
        self.assertEqual(reading.toPlainText(), original)
        self.assertFalse(editor.document().isModified())
        self.assertFalse(reading.document().isModified())
        block = reading.document().lastBlock()
        self.assertEqual(block.begin().fragment().charFormat().fontPointSize(), 13)
        self.assertEqual(block.begin().fragment().charFormat().fontFamilies(), [self._code_family()])

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
                         ('Styling', 'code_font_family_str'): self._code_family()})
        self.controller.reload()
        self.assertEqual(viewer.markdown_text(), before)
        self.assertFalse(viewer.is_modified)
        self.assertEqual(path.read_text(), source)

    def test_formatted_code_uses_shared_size_immediately_and_preserves_undo_on_reload(self):
        from commonUtils.ui.markdown.viewer import MarkdownViewer
        self.store.save({('Styling', 'code_font_family_str'): self._code_family(),
                         ('Styling', 'code_font_size_int'): '20'})
        self.controller.reload()
        path = self.root / 'live-code.md'
        path.write_text('Read `inline`.\n\n```python\nprint(1)\n```\n')
        viewer = MarkdownViewer(path, allow_edit=True)
        self.addCleanup(viewer.deleteLater)
        viewer.edit_button.setChecked(True)
        self.app.processEvents()
        document = viewer.formatted_editor.document()
        original = viewer.markdown_text()
        undo = document.availableUndoSteps()
        def code_formats():
            block = document.begin()
            result = []
            while block.isValid():
                result.extend(qt.QTextCharFormat(item.format) for item in block.layout().formats()
                              if item.format.fontFixedPitch())
                block = block.next()
            return result
        self.assertTrue(code_formats())
        self.assertTrue(all(fmt.fontPointSize() == 20 and fmt.fontFamilies() == [self._code_family()]
                            for fmt in code_formats()))
        self.store.save({('Styling', 'code_font_size_int'): '21',
                         ('Styling', 'code_font_family_str'): self._code_family(1)})
        self.controller.reload()
        self.assertTrue(all(fmt.fontPointSize() == 21 and fmt.fontFamilies() == [self._code_family(1)]
                            for fmt in code_formats()))
        self.assertEqual(document.availableUndoSteps(), undo)
        self.assertEqual(viewer.markdown_text(), original)
        self.assertFalse(viewer.is_modified)
