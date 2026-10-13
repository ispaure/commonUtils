from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor import CodeEdit


class ColumnGuideTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def test_guide_follows_text_columns_horizontal_scroll_and_font(self):
        editor = CodeEdit()
        editor.resize(600, 220)
        editor.setPlainText(' ' * 250)
        editor.set_column_guide(80)
        editor.show()
        self.app.processEvents()
        cursor = editor.textCursor()
        cursor.setPosition(80)
        self.assertAlmostEqual(editor.column_guide_x(), editor.cursorRect(cursor).x(), delta=1)
        original = editor.column_guide_x()
        editor.horizontalScrollBar().setValue(50)
        self.assertAlmostEqual(editor.column_guide_x(), original - 50, delta=1)
        font = editor.font()
        font.setPointSizeF(font.pointSizeF() + 4)
        editor.setFont(font)
        self.assertGreater(editor.column_guide_x(), original - 50)
        self.assertEqual(editor.toPlainText(), ' ' * 250)

    def test_guide_renders_and_can_be_disabled_and_shared(self):
        editor = CodeEdit()
        editor.resize(800, 220)
        editor.set_column_guide(40)
        editor.show()
        self.app.processEvents()
        image = editor.viewport().grab().toImage()
        x = int(editor.column_guide_x())
        second = CodeEdit()
        second.share_document_from(editor)
        self.assertEqual(second.column_guide, 40)
        editor.set_column_guide(0)
        cleared = editor.viewport().grab().toImage()
        changed = sum(image.pixelColor(x, y) != cleared.pixelColor(x, y)
                      for y in range(40, image.height()))
        self.assertGreater(changed, 20)
