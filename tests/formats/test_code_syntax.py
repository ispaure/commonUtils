
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor import CodeEdit
from commonUtils.ui.code_editor.syntax import (
    SyntaxHighlighter,
    detect_language,
    LANGUAGES,
)


class SyntaxTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def test_shared_accents_preserve_host_colors_and_neutral_python_names(self):
        from commonUtils.formats.code_spans import syntax_spans
        from pygments.token import Comment, Keyword, Name, Number, Operator, String, Text

        source = ('from package.module import helper\n'
                  'def hello(self) -> int:\n'
                  '    # comment\n'
                  '    helper("😀 text", 42)\n'
                  '    return self\n')
        editor = CodeEdit()
        editor.setPlainText(source)
        editor.document().setModified(True)
        highlighter = SyntaxHighlighter(editor, 'python')
        colors = []
        for base, foreground, dark in [('#faf9f6', '#24262b', False),
                                       ('#292d33', '#d8dbe0', True)]:
            palette = editor.palette()
            palette.setColor(qt.QPalette.ColorRole.Base, qt.QColor(base))
            palette.setColor(qt.QPalette.ColorRole.Text, qt.QColor(foreground))
            editor.setPalette(palette)
            highlighter.refresh_theme()
            self.assertEqual(editor.palette(), palette)
            self.assertEqual(editor.toPlainText(), source)
            self.assertTrue(editor.document().isModified())
            for token in (Text, Name, Name.Namespace, Name.Function,
                          Name.Function.Magic, Name.Class, Name.Builtin.Pseudo, Operator):
                fmt = highlighter.token_format(token)
                self.assertFalse(fmt.hasProperty(qt.QTextFormat.Property.ForegroundBrush), token)
                self.assertFalse(fmt.hasProperty(qt.QTextFormat.Property.BackgroundBrush), token)
            colors.append([highlighter.token_format(token).foreground().color().name()
                           for token in (Keyword, String, Number, Name.Builtin, Comment)])
            self.assertTrue(highlighter.token_format(Comment).fontItalic())
            self.assertFalse(highlighter.token_format(Keyword).font().bold())
            self.assertEqual(highlighter.token_format(Name.Exception).foreground(),
                             highlighter.token_format(Name.Builtin).foreground())
            _, spans = syntax_spans(source, 'example.py', dark=dark)
            native = {pos: rgb for start, end, rgb in spans for pos in range(start, end)}
            desktop = {}
            block = editor.document().begin()
            while block.isValid():
                for span in block.layout().formats():
                    if span.format.hasProperty(qt.QTextFormat.Property.ForegroundBrush):
                        rgb = span.format.foreground().color().rgb() & 0xffffff
                        desktop.update({block.position() + pos: rgb
                                        for pos in range(span.start, span.start + span.length)})
                block = block.next()
            self.assertEqual(desktop, native)
            for word in ('package.module', 'helper', 'hello', 'self'):
                start = source.index(word)
                self.assertTrue(all(pos not in native for pos in range(start, start + len(word))), word)
        self.assertTrue(all(light != dark for light, dark in zip(*colors)))
        editor.close()

    def test_unchanged_palette_skips_relexing_but_language_changes_rehighlight(self):
        from unittest.mock import patch
        editor = CodeEdit()
        highlight = SyntaxHighlighter(editor, 'python')
        editor.setPlainText('value = 1\n' * 100)
        with patch.object(highlight, 'rehighlight', wraps=highlight.rehighlight) as rehighlight:
            for _ in range(20):
                highlight.refresh_theme()
            rehighlight.assert_not_called()
            highlight.configure('javascript')
            rehighlight.assert_called_once()

    def test_all_languages_and_plain_text(self):
        editor = CodeEdit()
        highlight = SyntaxHighlighter(editor)
        for _, alias in LANGUAGES:
            highlight.configure(alias)
            editor.setPlainText('value = "hello" # comment\n')
            highlight.rehighlight()
            self.assertEqual(highlight.language, alias)
        highlight.configure("text")
        highlight.rehighlight()
        self.assertFalse(editor.document().begin().layout().formats())
        editor.deleteLater()

    def test_multiline_python_states_unicode_and_palette(self):
        editor = CodeEdit()
        highlight = SyntaxHighlighter(editor, "python")
        editor.setPlainText('s = """first\n😀 second\nlast"""\nx = 1')
        highlight.rehighlight()
        first = editor.document().begin()
        second = first.next()
        third = second.next()
        fourth = third.next()
        self.assertNotEqual(first.userState(), 0)
        self.assertNotEqual(second.userState(), 0)
        self.assertEqual(third.userState(), 0)
        self.assertTrue(second.layout().formats())
        self.assertTrue(fourth.layout().formats())
        editor.document().setModified(False)
        palette = editor.palette()
        palette.setColor(qt.QPalette.ColorRole.Base, qt.QColor("#111111"))
        editor.setPalette(palette)
        self.app.processEvents()
        self.assertFalse(editor.document().isModified())
        editor.deleteLater()

    def test_language_detection_uses_definitions_and_shebang(self):
        for name, alias in [
            ("x.py", "python"),
            ("x.command", "bash"),
            ("x.ps1", "powershell"),
            ("x.json", "json"),
            (".env", "ini"),
        ]:
            self.assertEqual(detect_language(name), alias)
        self.assertEqual(detect_language(None, "#!/usr/bin/env python\n"), "python")
        self.assertEqual(detect_language("unknown.custom"), "text")
