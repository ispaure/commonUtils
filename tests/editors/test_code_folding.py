import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor.views import EditorViews
from commonUtils.ui.code_editor.folding import fold_ranges
from commonUtils.ui.code_editor.widget import CodeEdit


class FoldingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def test_ranges_ignore_strings_comments_and_support_nested_blocks(self):
        self.assertEqual(fold_ranges('def a():\n    if x:\n        pass\nend', 'python'), {1: 2, 0: 2})
        ranges = fold_ranges('{\n "brace": "}",\n "nested": [\n  1\n ]\n}', 'json')
        self.assertEqual(ranges, {2: 4, 0: 5})
        self.assertEqual(fold_ranges('<r>\n<!-- <bad> -->\n<a>\nx\n</a>\n</r>', 'xml'), {2: 4, 0: 5})
        self.assertEqual(fold_ranges('x' * (256 * 1024 + 1), 'python'), {})

    def test_rendered_guides_stay_in_whitespace_with_fractional_fonts_tabs_and_zoom(self):
        editor = CodeEdit()
        try:
            palette = editor.palette()
            palette.setColor(qt.QPalette.ColorRole.Mid, qt.QColor('red'))
            editor.setPalette(palette)
            editor.resize(500, 160); editor.show()
            for size, prefix in ((13.5, ' ' * 16), (17.5, ' \t\t'), (10.5, '\t')):
                font = qt.QFont('Menlo'); font.setPointSizeF(size); editor.setFont(font)
                editor.setPlainText(prefix + 'WWWW')
                self.app.processEvents()
                image = editor.viewport().grab().toImage()
                scale = image.devicePixelRatio()
                pixels = [(x, y) for y in range(image.height()) for x in range(image.width())
                          if image.pixelColor(x, y) == qt.QColor('red')]
                self.assertTrue(pixels)
                line = editor.document().firstBlock().layout().lineAt(0)
                text_x = line.cursorToX(len(prefix))[0] + editor.contentOffset().x()
                self.assertLess(max(x for x, y in pixels), text_x * scale)
                self.assertAlmostEqual(editor.tabStopDistance(), qt.QFontMetricsF(font).horizontalAdvance(' ') * editor.indent_width)
        finally:
            editor.deleteLater()

    def test_wrapped_continuation_rows_do_not_receive_indentation_guides(self):
        editor = CodeEdit()
        try:
            palette = editor.palette(); palette.setColor(qt.QPalette.ColorRole.Mid, qt.QColor('red'))
            editor.setPalette(palette)
            editor.setLineWrapMode(qt.QPlainTextEdit.LineWrapMode.WidgetWidth)
            editor.setPlainText('    ' + 'WWWW ' * 30)
            editor.resize(190, 300); editor.show(); self.app.processEvents()
            layout = editor.document().firstBlock().layout()
            self.assertGreater(layout.lineCount(), 1)
            line = layout.lineAt(0)
            image = editor.viewport().grab().toImage()
            rows = [y for y in range(image.height()) if any(image.pixelColor(x, y) == qt.QColor('red') for x in range(image.width()))]
            self.assertTrue(rows)
            bottom = editor.contentOffset().y() + line.y() + line.height()
            self.assertLessEqual(max(rows), bottom * image.devicePixelRatio())
        finally:
            editor.deleteLater()

    def test_folds_share_views_reveal_search_and_expand_after_edit(self):
        views = EditorViews()
        try:
            primary = views.primary
            primary.setPlainText('{\n "a": [\n  1\n ]\n}')
            primary.folding.configure('json')
            views.set_split(qt.Qt.Orientation.Horizontal)
            primary.fold_all()
            self.assertFalse(primary.document().findBlockByNumber(2).isVisible())
            self.assertIs(primary.folding, views.secondary.folding)
            cursor = qt.QTextCursor(primary.document().findBlockByNumber(2))
            views.secondary.setTextCursor(cursor)
            self.assertTrue(primary.document().findBlockByNumber(2).isVisible())
            primary.fold_all()
            primary.insertPlainText(' ')
            self.app.processEvents()
            self.assertTrue(all(primary.document().findBlockByNumber(i).isVisible() for i in range(primary.blockCount())))
            primary.undo()
            self.assertEqual(primary.toPlainText(), '{\n "a": [\n  1\n ]\n}')
        finally:
            views.deleteLater()
