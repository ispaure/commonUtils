"""YAML properties and lossless frontmatter across formatted Markdown edits."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import patch
from commonUtils.markdownUtils import split_frontmatter, parse_properties, replace_property, replace_frontmatter
from commonUtils.ui import pyside as qt
from commonUtils.ui.markdown import MarkdownViewer
from commonUtils.ui.markdown.properties import typed_value, property_type


HEADER = ('---\n# Important metadata comment\ntitle: "A: title"\n'
          'tags: [comics, library]\npublished: true\nrating: 4.5\n'
          'date: 2026-10-08\naliases:\n  - "[[Related note]]"\n'
          'description: |\n  First line\n  Second line\n'
          'nested:\n  keep: value\n---\n')


class FrontmatterTests(QtTestCase):
    def test_boundaries_start_only_empty_unclosed_and_body_rule(self):
        for text in ('# Heading\n---\nbody', '\n---\ntitle: value\n---\nbody'):
            self.assertFalse(split_frontmatter(text).present)
        parts = split_frontmatter(HEADER + '# Body\n\n---\nText')
        self.assertEqual(parts.prefix, HEADER)
        self.assertEqual(parts.body, '# Body\n\n---\nText')
        self.assertEqual(parse_properties(split_frontmatter('---\n---\nbody')), {})
        with self.assertRaises(ValueError):
            parse_properties(split_frontmatter('---\ntitle: value\n'))

    def test_typed_yaml_comments_quotes_multiline_and_body_preserved(self):
        original = HEADER + '# Body\n\nExact body whitespace  \n'
        updated = replace_property(original, 'published', False)
        self.assertEqual(split_frontmatter(updated).body, split_frontmatter(original).body)
        self.assertIn('# Important metadata comment', updated)
        self.assertIn('title: "A: title"', updated)
        data = parse_properties(split_frontmatter(updated))
        self.assertEqual(data['description'].text, '|\n  First line\n  Second line\n')
        self.assertIn('keep: value', data['nested'].text)
        self.assertEqual(data['aliases'], ['[[Related note]]'])
        self.assertFalse(data['published'])
        self.assertEqual(property_type(data['date']), 'Date')
        self.assertEqual(replace_property(original, 'published', True), original)
        self.assertNotIn('rating', parse_properties(split_frontmatter(replace_property(original, 'rating', remove=True))))

    def test_invalid_duplicate_nonmapping_and_unsafe_tags(self):
        for yaml in ('title: [unfinished', 'a: 1\na: 2', '- item', '1: invalid-name'):
            with self.subTest(yaml=yaml), self.assertRaises(ValueError):
                replace_frontmatter('# Body', yaml)
        text = '---\nvalue: !!python/object/apply:os.system ["echo should-never-run"]\n---\nBody'
        with patch('os.system') as execute:
            parse_properties(split_frontmatter(text))
            execute.assert_not_called()

    def test_basic_text_quotes_comments_zero_and_no_yaml_dependency(self):
        text = ("---\ntitle: Don't drop apostrophes # retained\n"
                "tags: ['Bob''s, note', \"A, B\", https://example.com/#fragment]\n"
                "zero: 0\nempty: ''\n---\nBody")
        data = parse_properties(split_frontmatter(text))
        self.assertEqual(data['title'], "Don't drop apostrophes")
        self.assertEqual(data['tags'], ["Bob's, note", 'A, B', 'https://example.com/#fragment'])
        self.assertEqual(data['zero'], 0)
        self.assertEqual(data['empty'], '')
        updated = replace_property(text, 'zero', 2)
        self.assertIn("title: Don't drop apostrophes # retained", updated)
        self.assertIn("tags: ['Bob''s, note', \"A, B\", https://example.com/#fragment]", updated)
        self.assertEqual(split_frontmatter(updated).body, 'Body')

    def test_typed_value_conversion_and_numeric_validation(self):
        self.assertEqual(typed_value('Tags', 'first\nsecond\n'), ['first', 'second'])
        self.assertEqual(typed_value('Text', 'true'), 'true')
        self.assertEqual(typed_value('Checkbox', 'false'), False)
        self.assertEqual(typed_value('Number', '0'), 0)
        self.assertEqual(typed_value('Date', '2026-10-08').isoformat(), '2026-10-08')
        for kind, text in (('Number', 'true'), ('Number', '2+2'), ('Checkbox', 'yes'), ('Date', 'not a date')):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                typed_value(kind, text)


class FrontmatterWidgetTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'note.md'
        self.path.write_text(HEADER + '# Body\n\nA paragraph.\n', encoding='utf-8')
        self.viewer = MarkdownViewer(self.path, allow_edit=True)
        self.viewer.set_editing(False)
        self.viewer.show()
        self.addCleanup(self.viewer.deleteLater)
        self.app.processEvents()

    def test_properties_separated_from_body_and_contents(self):
        self.assertTrue(self.viewer.properties.isVisible())
        self.assertEqual(self.viewer.properties.table.topLevelItemCount(), 8)
        self.assertNotIn('Important metadata', self.viewer.browser.toPlainText())
        self.assertNotIn('published', self.viewer.browser.toPlainText())
        self.assertEqual([title for _, title, _ in self.viewer.headings], ['Body'])
        original = self.path.read_bytes()
        self.viewer.set_editing(True)
        self.assertNotIn('published', self.viewer.formatted_editor.toPlainText())
        self.assertTrue(self.viewer.save_document())
        self.assertEqual(self.path.read_bytes(), original)

    def test_rich_body_edits_preserve_exact_yaml_and_property_edits_preserve_body(self):
        self.viewer.set_editing(True)
        self.viewer.formatted_editor.insertPlainText('Edited ')
        self.assertEqual(split_frontmatter(self.viewer.markdown_text()).prefix, HEADER)
        self.viewer.formatted_editor.insertPlainText('Fresh unsynced ')
        self.assertTrue(self.viewer.properties.apply_property('published', False))
        self.assertIn('Fresh unsynced', self.viewer.formatted_editor.toPlainText())
        self.assertTrue(self.viewer.is_modified)
        self.assertTrue(self.viewer.save_document())
        saved = self.path.read_text()
        self.assertFalse(parse_properties(split_frontmatter(saved))['published'])
        self.assertIn('# Important metadata comment', saved)
        self.assertIn('Fresh unsynced', split_frontmatter(saved).body)

    def test_checkbox_click_changes_yaml_only_in_edit_mode(self):
        self.viewer.set_editing(True)
        table = self.viewer.properties.table
        item = next(table.topLevelItem(i) for i in range(table.topLevelItemCount())
                    if table.topLevelItem(i).text(0) == 'published')
        item.setCheckState(2, qt.Qt.CheckState.Unchecked)
        from shiboken6 import isValid
        self.assertTrue(isValid(item))  # Do not delete the item inside its change signal.
        self.assertFalse(parse_properties(split_frontmatter(self.viewer.markdown_text()))['published'])
        self.assertTrue(self.viewer.is_modified)

    def test_complex_list_cannot_be_coerced_to_text_by_property_dialog(self):
        self.viewer.set_editing(True)
        self.viewer.properties.apply_property('mixed', [1, 'two'])
        table = self.viewer.properties.table
        item = next(table.topLevelItem(i) for i in range(table.topLevelItemCount())
                    if table.topLevelItem(i).text(0) == 'mixed')
        before = self.viewer.markdown_text()
        with patch.object(qt, 'QDialog') as dialog:
            self.viewer.properties.edit_property(item)
            dialog.assert_not_called()
        self.assertEqual(self.viewer.markdown_text(), before)
        self.assertIn('Source mode', self.viewer.properties.error.text())

    def test_add_remove_source_switch_and_undo_property(self):
        self.assertFalse(self.viewer.properties.apply_property('new', 'value'))
        self.viewer.set_editing(True)
        self.assertTrue(self.viewer.properties.apply_property('new', ['one', 'two']))
        self.viewer.set_edit_mode('source')
        self.assertIn('new:', self.viewer.editor.toPlainText())
        self.viewer.undo_action.trigger()
        self.assertNotIn('new:', self.viewer.editor.toPlainText())
        self.viewer.set_edit_mode('formatted')
        self.assertTrue(self.viewer.properties.apply_property('tags', remove=True))
        self.assertNotIn('tags', parse_properties(split_frontmatter(self.viewer.markdown_text())))

    def test_empty_properties_hide_and_corner_menu_can_create_first_property(self):
        self.path.write_text('# Body\n\nA paragraph.\n')
        self.viewer.open_document(self.path)
        self.viewer.set_editing(True)
        self.assertFalse(self.viewer.properties.isVisible())
        self.assertTrue(self.viewer.properties_button.isVisible())
        self.assertTrue(self.viewer.add_property_action.isEnabled())
        with patch.object(self.viewer.properties, 'edit_property') as edit:
            self.viewer.add_property_action.trigger()
            edit.assert_called_once_with()
        self.viewer.formatted_editor.insertPlainText('Unsaved body ')
        self.assertTrue(self.viewer.properties.apply_property('title', 'New note'))
        self.assertTrue(self.viewer.properties.isVisible())
        self.assertIn('Unsaved body', split_frontmatter(self.viewer.markdown_text()).body)
        table = self.viewer.properties.table
        table.setCurrentItem(table.topLevelItem(0))
        self.assertTrue(self.viewer.properties.remove_button.isEnabled())
        self.viewer.properties.remove_button.click()
        self.assertFalse(self.viewer.properties.isVisible())
        self.assertEqual(parse_properties(split_frontmatter(self.viewer.markdown_text())), {})
        self.assertIn('Unsaved body', split_frontmatter(self.viewer.markdown_text()).body)

    def test_property_controls_follow_edit_permission_and_selection(self):
        self.assertFalse(self.viewer.add_property_action.isEnabled())
        self.viewer.set_editing(True)
        self.assertTrue(self.viewer.add_property_action.isEnabled())
        self.assertFalse(self.viewer.properties.remove_button.isEnabled())
        self.viewer.properties.table.setCurrentItem(self.viewer.properties.table.topLevelItem(0))
        self.assertTrue(self.viewer.properties.edit_button.isEnabled())
        self.assertTrue(self.viewer.properties.remove_button.isEnabled())
        self.viewer.set_edit_mode('source')
        self.assertFalse(self.viewer.add_property_action.isEnabled())
        self.assertFalse(self.viewer.edit_yaml_action.isEnabled())
        self.viewer.set_edit_mode('formatted')
        self.viewer.set_editing(False)
        self.assertFalse(self.viewer.add_property_action.isEnabled())
        preview = MarkdownViewer(self.path)
        self.addCleanup(preview.deleteLater)
        preview.show()
        self.assertFalse(preview.properties_button.isVisible())
        self.assertFalse(preview.properties.apply_property('title', 'Blocked'))

    def test_empty_yaml_panel_hides_but_invalid_yaml_error_stays_visible(self):
        self.path.write_text('---\n---\n# Body\n')
        self.viewer.open_document(self.path)
        self.viewer.set_editing(True)
        self.assertFalse(self.viewer.properties.isVisible())
        self.assertTrue(self.viewer.add_property_action.isEnabled())
        self.path.write_text('---\ntags: [unfinished\n---\n# Body\n')
        self.viewer.open_document(self.path)
        self.assertTrue(self.viewer.properties.isVisible())
        self.assertTrue(self.viewer.properties.error.isVisible())
        self.assertIn('Invalid YAML', self.viewer.properties.error.text())

    def test_invalid_yaml_is_retained_during_body_edit_and_unclosed_uses_source(self):
        bad = '---\ntags: [unfinished\n---\n# Body\n'
        self.path.write_text(bad)
        self.viewer.open_document(self.path)
        self.assertIn('Invalid YAML', self.viewer.properties.error.text())
        self.viewer.set_editing(True)
        self.viewer.formatted_editor.insertPlainText('Edited ')
        self.assertTrue(self.viewer.save_document())
        self.assertEqual(split_frontmatter(self.path.read_text()).prefix, split_frontmatter(bad).prefix)
        self.path.write_text('---\ntitle: unclosed\n')
        self.viewer.open_document(self.path)
        self.assertEqual(self.viewer.edit_mode.currentData(), 'source')
        self.assertIn('title: unclosed', self.viewer.editor.toPlainText())
