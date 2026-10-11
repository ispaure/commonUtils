from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor import CodeEdit
from commonUtils.ui.code_editor.syntax import detect_language, SyntaxHighlighter


class SyntaxTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def test_compound_names_and_theme_rendering(self):
        for path, language in [('view.BLADE.PHP', 'blade'), ('types.pyi', 'python'), ('index.php', 'html+php')]:
            self.assertEqual(detect_language(path), language)
        editor = CodeEdit()
        editor.setPlainText('<div>@if($enabled) {{ $name }} @endif</div>')
        highlighter = SyntaxHighlighter(editor, 'blade')
        self.assertIsNotNone(highlighter.lexer)
        for color in ('#ffffff', '#202020'):
            palette = editor.palette()
            palette.setColor(qt.QPalette.ColorRole.Base, qt.QColor(color))
            editor.setPalette(palette)
            highlighter.refresh_theme()
            self.assertTrue(editor.document().firstBlock().layout().formats())
        editor.close()


    def test_php_and_html_states_survive_line_boundaries(self):
        from pygments.token import Keyword, Name
        editor = CodeEdit()
        editor.setPlainText('<?php\nclass Thing {}\n?>\n<h1>Title</h1>')
        highlighter = SyntaxHighlighter(editor, 'html+php')
        highlighter.rehighlight()
        php = editor.document().findBlockByNumber(1).layout().formats()
        self.assertTrue(any(span.start == 0 and span.length == 5 and
                            span.format == highlighter.token_format(Keyword) for span in php))
        html = editor.document().findBlockByNumber(3).layout().formats()
        self.assertTrue(any(span.start == 1 and span.length == 2 and
                            span.format == highlighter.token_format(Name.Tag) for span in html))
        editor.close()
