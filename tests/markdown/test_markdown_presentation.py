"""Reading extensions remain presentation-only and use palette-aware formats."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import sys
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import patch

from commonUtils.ui import pyside as qt
from commonUtils.ui.markdown import MarkdownViewer
from commonUtils.ui.markdown.extensions import reading_source, mermaid_blocks
from commonUtils.ui.markdown.presentation import ACCENT, CODE_LANGUAGE, tables
from commonUtils.ui.markdown.diagrams import MermaidRenderer, safe_diagram
from commonUtils.ui.appearance.theme import apply_theme, theme_palette, SLATE_DARK, SLATE_LIGHT


class MarkdownPresentationTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'note.md'

    def python_process(self, executable):
        original = qt.QProcess.start
        def start(process, program, arguments):
            return original(process, sys.executable, [str(executable), *arguments])
        return patch.object(qt.QProcess, 'start', start)

    def viewer(self, source, *, edit=False):
        self.path.write_text(source, encoding='utf-8')
        viewer = MarkdownViewer(self.path, allow_edit=edit)
        viewer.resize(800, 700)
        viewer.show(); self.app.processEvents()
        self.addCleanup(viewer.deleteLater)
        return viewer

    def test_foldable_nested_callouts_quotes_and_noop_save_preserve_source(self):
        source = '# Title\n\n> [!warning]- Watch out\n> Hidden body\n>\n> > [!note] Nested\n> > Nested body\n\n> A normal quote\n\nTail\n'
        viewer = self.viewer(source, edit=True)
        self.assertEqual(viewer.edit_mode.currentData(), 'source')
        viewer.set_editing(False)
        self.assertNotIn('Hidden body', viewer.browser.toPlainText())
        self.assertIn('A normal quote', viewer.browser.toPlainText())
        viewer.follow_link(qt.QUrl('callout:2'))
        self.assertIn('Hidden body', viewer.browser.toPlainText())
        self.assertIn('Nested body', viewer.browser.toPlainText())
        frames = [frame for frame in viewer.browser.document().rootFrame().childFrames() if frame.format().hasProperty(ACCENT)]
        self.assertEqual(len(frames), 2)
        self.assertNotEqual(frames[0].format().property(ACCENT), frames[1].format().property(ACCENT))
        self.assertFalse(viewer.is_modified)
        viewer.save_document()
        self.assertEqual(self.path.read_text(), source)

    def test_callout_examples_in_fences_and_mermaid_extraction_are_literal(self):
        source = '````md\n> [!tip]- Example\n```mermaid\ngraph TD\n```\n````\n\n> [!done]+ Finished\n> Body\n'
        rendered, callouts = reading_source(source)
        self.assertEqual(len(callouts), 1)
        self.assertEqual(next(iter(callouts.values())).kind, 'success')
        self.assertIn('> [!tip]- Example', rendered)
        self.assertEqual(mermaid_blocks(source), [])
        self.assertEqual(mermaid_blocks('~~~mermaid\ngraph TD\nA-->B\n~~~')[0][2], 'graph TD\nA-->B')
        rendered, callouts = reading_source('    > [!tip] Indented code\n\n> ```md\n> [!note] Example\n\n> [!info] Actual callout')
        self.assertIn('    > [!tip] Indented code', rendered)
        # An unquoted blank ends the quoted fence; the next callout is real.
        self.assertEqual(len(callouts), 1)
        rendered, callouts = reading_source('> ```md\n> [!note] Example\n\nOutside\n\n> [!info] Actual callout')
        self.assertEqual(len(callouts), 1)

    def test_reading_measure_tracks_window_and_zoom_without_changing_source(self):
        source = '# Heading\n\n' + ('A readable paragraph with `inline code`. ' * 30) + '\n\n```python\nprint(1)\n```\n'
        viewer = self.viewer(source)
        browser = viewer.browser
        document = browser.document()
        viewer.resize(1600, 700)
        self.app.processEvents()
        wide_margin = document.rootFrame().frameFormat().leftMargin()
        self.assertGreater(wide_margin, 28)
        measure = qt.QFontMetricsF(browser.font()).horizontalAdvance('n') * 88
        self.assertAlmostEqual(browser.viewport().width() - 2 * wide_margin, measure, delta=1)
        viewer.set_reading_size(18)
        self.app.processEvents()
        self.assertLess(document.rootFrame().frameFormat().leftMargin(), wide_margin)
        code_sizes = []
        block = document.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                if fragment.charFormat().fontFixedPitch():
                    code_sizes.append(fragment.charFormat().fontPointSize())
                it += 1
            block = block.next()
        self.assertGreater(len(code_sizes), 1)
        self.assertTrue(all(size == browser.font().pointSizeF() for size in code_sizes))
        viewer.resize(520, 700)
        self.app.processEvents()
        self.assertEqual(document.rootFrame().frameFormat().leftMargin(), 28)
        self.assertEqual(document.rootFrame().frameFormat().rightMargin(), 28)
        self.assertEqual(viewer.markdown_text(), source)
        self.assertFalse(viewer.is_modified)
        self.assertEqual(self.path.read_text(), source)

    def test_table_formatting_and_theme_change_do_not_dirty_source(self):
        source = '# Heading\n\n| A | B |\n| --- | --- |\n| One | Two |\n| Three | Four |\n'
        viewer = self.viewer(source, edit=True)
        viewer.set_editing(False)
        viewer.setPalette(theme_palette(SLATE_DARK)); self.app.processEvents()
        table = next(tables(viewer.browser.document().rootFrame()))
        self.assertEqual(table.format().border(), 0)
        self.assertGreaterEqual(table.format().cellPadding(), 8)
        dark = table.cellAt(0, 0).format().background().color()
        viewer.setPalette(theme_palette(SLATE_LIGHT)); self.app.processEvents()
        table = next(tables(viewer.browser.document().rootFrame()))
        self.assertNotEqual(dark, table.cellAt(0, 0).format().background().color())
        self.assertFalse(viewer.is_modified)
        self.assertEqual(viewer.markdown_text(), source)

    def test_multiline_vbnet_fences_are_continuous_and_preserve_source(self):
        for fence in ('```', '````'):
            source = f'{fence}vbnet\nDim name As String = "Hello 🌍"\n\n    Console.WriteLine(name)\n{fence}\n\nAfter\n'
            viewer = self.viewer(source)
            frames = [frame for frame in viewer.browser.document().rootFrame().childFrames()
                      if frame.format().hasProperty(CODE_LANGUAGE)]
            self.assertEqual(len(frames), 1)
            self.assertEqual(frames[0].format().property(CODE_LANGUAGE), 'vbnet')
            self.assertIn('    Console.WriteLine(name)', viewer.browser.toPlainText())
            self.assertIn('Hello 🌍', viewer.browser.toPlainText())
            self.assertIn('After', viewer.browser.toPlainText())
            self.assertFalse(viewer.is_modified)
            self.assertEqual(viewer.markdown_text(), source)
            self.assertEqual(self.path.read_text(), source)

    def test_reading_code_syntax_colors_handle_unicode_and_unknown_languages(self):
        source = '```vbnet\nDim emoji As String = "🌍"\nDim count As Integer = 1\n```\n\n```unknown-language\nKeep this literal\n```\n'
        viewer = self.viewer(source)
        document = viewer.browser.document()
        position = document.toPlainText().index('Dim')
        cursor = qt.QTextCursor(document)
        cursor.setPosition(position)
        cursor.movePosition(qt.QTextCursor.MoveOperation.NextCharacter, qt.QTextCursor.MoveMode.KeepAnchor)
        self.assertNotEqual(cursor.charFormat().foreground().color(), viewer.browser.palette().color(qt.QPalette.ColorRole.Text))
        self.assertIn('Dim count As Integer = 1', viewer.browser.toPlainText())
        self.assertIn('Keep this literal', viewer.browser.toPlainText())
        self.assertEqual(viewer.markdown_text(), source)

    def test_python_fences_share_editor_accents_and_leave_names_neutral(self):
        from commonUtils.formats.code_syntax import syntax_style
        from commonUtils.ui.markdown.presentation import highlight_code
        from pygments.token import Keyword, String

        source = '```python\nfrom package.module import helper\ndef hello():\n    return "😀 text"\n```'
        for dark in (False, True):
            document = qt.QTextDocument()
            document.setMarkdown(source)
            palette = qt.QPalette()
            palette.setColor(qt.QPalette.ColorRole.Base, qt.QColor('#292d33' if dark else '#faf9f6'))
            original = document.toPlainText()
            highlight_code(document, palette)
            self.assertEqual(document.toPlainText(), original)

            def char_format(word):
                start = original.index(word)
                cursor = qt.QTextCursor(document)
                cursor.setPosition(start)
                cursor.setPosition(start + 1, qt.QTextCursor.MoveMode.KeepAnchor)
                return cursor.charFormat()

            for word, token in [('from', Keyword), ('return', Keyword), ('"', String)]:
                expected = '#' + syntax_style(dark).style_for_token(token)['color']
                self.assertEqual(char_format(word).foreground().color().name(), expected)
            for word in ('package.module', 'helper', 'hello'):
                self.assertFalse(char_format(word).hasProperty(qt.QTextFormat.Property.ForegroundBrush))

    def test_missing_mermaid_renderer_keeps_code_and_explains_optional_install(self):
        source = '```mermaid\ngraph TD\nA-->B\n```\n'
        viewer = self.viewer(source)
        with patch('commonUtils.ui.markdown.diagrams.shutil.which', return_value=None), \
                patch.object(qt.QMessageBox, 'information') as message:
            viewer.render_diagrams()
        self.assertIn('Mermaid CLI', message.call_args.args[2])
        self.assertNotIn('Logistics', message.call_args.args[2])
        self.assertIn('A-->B', viewer.browser.toPlainText())
        self.assertEqual(viewer.markdown_text(), source)

    def test_async_renderer_inserts_bounded_image_and_preserves_source(self):
        source = '```mermaid\ngraph TD\nA-->B\n```\n\nTail'
        viewer = self.viewer(source)
        # An actual QProcess exercises lifecycle and resource insertion without
        # depending on npm/Chromium or touching the user's Temp/cache folders.
        picture = qt.QImage(1200, 600, qt.QImage.Format.Format_ARGB32)
        picture.fill(qt.QColor('blue')); picture.save(str(self.root / 'fixture.png'))
        executable = self.root / 'mmdc'
        executable.write_text('#!/usr/bin/env python3\nimport sys,shutil\nshutil.copyfile(' +
            repr(str(self.root / 'fixture.png')) + ',sys.argv[sys.argv.index("-o")+1])\n')
        executable.chmod(0o700)
        with self.python_process(executable), patch('commonUtils.ui.markdown.diagrams.shutil.which', return_value=str(executable)), \
                patch('commonUtils.ui.markdown.diagrams.temporary_workspace', side_effect=lambda **kw: TemporaryDirectory(dir=self.root)):
            viewer.render_diagrams()
            deadline = time.monotonic() + 5
            while not viewer.diagrams_button.isEnabled():
                self.assertLess(time.monotonic(), deadline)
                self.app.processEvents(); time.sleep(.01)
        self.assertIn('Tail', viewer.browser.toPlainText())
        self.assertNotIn('A-->B', viewer.browser.toPlainText())
        self.assertEqual(viewer.markdown_text(), source)
        block = viewer.browser.document().begin()
        found = False
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                if fragment.isValid() and fragment.charFormat().isImageFormat():
                    found = True
                    self.assertLessEqual(fragment.charFormat().toImageFormat().width(), viewer.browser.viewport().width())
                it += 1
            block = block.next()
        self.assertTrue(found)

    def test_renderer_rejects_external_resources_and_note_configuration(self):
        for source in ('%%{init: {"securityLevel":"loose"}}%%\ngraph TD',
                       'graph TD\nA[<img src="https://example.com/image">]', 'x' * 50_001):
            with self.assertRaises(ValueError):
                safe_diagram(source)
        self.assertEqual(safe_diagram('graph TD\nA-->B'), 'graph TD\nA-->B')

    def test_authored_links_using_internal_scheme_do_not_crash_or_hide_text(self):
        viewer = self.viewer('[Keep this](callout:not-an-id)\n\n[Also keep this](callout-end:0)\n\nTail')
        self.assertIn('Keep this', viewer.browser.toPlainText())
        self.assertIn('Also keep this', viewer.browser.toPlainText())
        self.assertIn('Tail', viewer.browser.toPlainText())
        viewer.follow_link(qt.QUrl('callout:not-an-id'))

    def test_application_palette_plus_stylesheet_transition_uses_final_colors(self):
        viewer = self.viewer('| A | B |\n| --- | --- |\n| One | Two |\n')
        palette, stylesheet = self.app.palette(), self.app.styleSheet()
        try:
            controller = apply_theme(self.app, mode='dark')
            for _ in range(3):
                self.app.processEvents()
            table = next(tables(viewer.browser.document().rootFrame()))
            self.assertLess(table.cellAt(0, 0).format().background().color().lightness(), 100)
            controller.set_mode('light')
            for _ in range(3):
                self.app.processEvents()
            table = next(tables(viewer.browser.document().rootFrame()))
            self.assertGreater(table.cellAt(0, 0).format().background().color().lightness(), 200)
            self.assertFalse(viewer.is_modified)
        finally:
            self.app.setPalette(palette)
            self.app.setStyleSheet(stylesheet)

    def test_reading_font_size_and_popup_escape_never_modify_markdown(self):
        source = '# Heading\n\nBody with `code`.\n'
        viewer = self.viewer(source)
        self.assertEqual(viewer.document_title.text(), self.path.name)
        viewer.set_reading_size(19)
        self.assertEqual(viewer.browser.font().pointSizeF(), 19)
        self.assertEqual(viewer.markdown_text(), source)
        self.assertFalse(viewer.is_modified)
        viewer.show_reading_appearance()
        self.assertTrue(viewer.appearance_popup.isVisible())
        viewer._escape()
        self.assertFalse(viewer.appearance_popup.isVisible())

    def test_timeout_and_close_stop_diagram_process_without_losing_code(self):
        source = '```mermaid\ngraph TD\nA-->B\n```\n'
        viewer = self.viewer(source)
        executable = self.root / 'slow-mmdc'
        executable.write_text('#!/usr/bin/env python3\nimport time\ntime.sleep(5)\n')
        executable.chmod(0o700)
        with self.python_process(executable), patch('commonUtils.ui.markdown.diagrams.shutil.which', return_value=str(executable)), \
                patch('commonUtils.ui.markdown.diagrams.temporary_workspace', side_effect=lambda **kw: TemporaryDirectory(dir=self.root)):
            renderer = viewer._diagram_renderer = MermaidRenderer(viewer)
            renderer.timer.setInterval(50)
            renderer.render()
            deadline = time.monotonic() + 3
            while not viewer.diagrams_button.isEnabled():
                self.assertLess(time.monotonic(), deadline)
                self.app.processEvents(); time.sleep(.01)
            self.assertIn('timed out', viewer.status.text())
            self.assertIn('A-->B', viewer.browser.toPlainText())
            self.assertIsNone(renderer.workspace)
            renderer.timer.setInterval(5000)
            renderer.render()
            viewer.close(); self.app.processEvents()
            self.assertEqual(renderer.process.state(), qt.QProcess.ProcessState.NotRunning)
            self.assertIsNone(renderer.workspace)
        self.assertEqual(viewer.markdown_text(), source)

    def test_fullscreen_action_matches_readers_and_escape_restores_window(self):
        from PySide6.QtTest import QTest
        viewer = self.viewer('# Title\n\nBody\n')
        viewer.fullscreen_action.trigger(); self.app.processEvents()
        self.assertTrue(viewer.isFullScreen())
        self.assertEqual(viewer.fullscreen_action.text(), 'Exit full screen')
        QTest.keyClick(viewer.browser, qt.Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertFalse(viewer.isFullScreen())
        self.assertEqual(viewer.fullscreen_action.text(), 'Full screen')
