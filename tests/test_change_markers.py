from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor import CodeEdit
from commonUtils.ui.code_editor.markers import line_changes


class MarkerTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def test_add_modify_delete_and_eof(self):
        for before, after, kind, start, end in [
            ('a\n', 'a\nb\n', 'add', 1, 2),
            ('a\n', 'b\n', 'modify', 0, 1),
            ('a\nb\n', 'a\n', 'delete', 1, 1),
            ('a', '', 'delete', 0, 0),
            ('a\n', 'a', 'modify', 0, 1),
        ]:
            change, = line_changes(before, after)
            self.assertEqual((change.kind, change.start, change.end), (kind, start, end))

    def test_render_markers_separate_from_folding_and_numbers(self):
        editor = CodeEdit()
        self.addCleanup(editor.deleteLater)
        editor.resize(480, 240)
        before = 'def example():\n    old = 1\n    return old\n# deleted\n'
        after = 'def example():\n    new = 2\n    return old\n'
        editor.setPlainText(after)
        editor.folding.configure('python')
        editor.set_line_changes(line_changes(before, after), 'Git index')
        editor.show()
        self.app.processEvents()
        image = editor.gutter.grab().toImage()
        self.assertEqual(image.pixelColor(3, editor.fontMetrics().height() + 6).name(), '#408bd6')
        self.assertEqual(editor.gutter.toolTip(), 'Git index')
        editor.gutter_click(qt.QPoint(3, 8))
        self.assertFalse(editor.folding.collapsed)
