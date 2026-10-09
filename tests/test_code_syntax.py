import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor import CodeEdit
from commonUtils.ui.code_editor.syntax import (
    SyntaxHighlighter,
    detect_language,
    LANGUAGES,
)


class SyntaxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

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
