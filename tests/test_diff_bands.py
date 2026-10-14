"""Diff metadata follows Qt paragraphs, including embedded separators."""
from types import SimpleNamespace

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor.diff_bands import DiffEdit, DiffHighlighter


def line(text, old='', new='', kind=''):
    return SimpleNamespace(text=text, old=old, new=new, kind=kind)


def view(lines):
    text = '\n'.join(row.text for row in lines)
    return SimpleNamespace(text=text, raw_text=text, lines=lines, raw_lines=lines)


class DiffBandsTests(QtTestCase):
    def test_embedded_separators_keep_later_line_numbers_and_bands_aligned(self):
        editor = DiffEdit()
        editor.highlighter = DiffHighlighter(editor)
        editor.resize(480, 240)
        editor.show()
        for separator in ('\r', '\n', '\r\n', '\u2029'):
            for raw in (False, True):
                with self.subTest(separator=repr(separator), raw=raw):
                    editor.set_diff(view([line('-old' + separator + 'continued', '1', kind='remove'),
                                          line('+new', new='1', kind='add')]), raw=raw)
                    self.assertEqual(editor.blockCount(), 3)
                    self.assertEqual(editor.diff_rows, [('1', '', 'remove'), ('', '', 'remove'),
                                                        ('', '1', 'add')])
                    editor.highlight_cursor()
                    self.assertEqual(len(editor.extraSelections()), 3)
                    editor.gutter.grab()

    def test_crlf_patch_lines_and_unicode_line_separator_keep_single_rows(self):
        editor = DiffEdit()
        editor.set_diff(view([line('-old\r', '1', kind='remove'),
                              line('+new\u2028continued\r', new='1', kind='add'), line('')]))
        self.assertEqual(editor.blockCount(), 3)
        self.assertEqual(len(editor.diff_rows), 3)
        self.assertEqual(editor.diff_rows[1], ('', '1', 'add'))

    def test_multiline_fallback_and_trailing_paragraph_have_metadata_for_every_block(self):
        editor = DiffEdit()
        editor.set_diff(view([line('first\nsecond\r')]))
        self.assertEqual(editor.blockCount(), 3)
        self.assertEqual(len(editor.diff_rows), 3)
        editor.set_diff(view([]))
        editor.highlight_cursor()
        self.assertEqual(editor.diff_rows, [])

    def test_document_changes_with_stale_metadata_render_unannotated_blocks(self):
        editor = DiffEdit()
        editor.set_diff(view([line('+first', new='1', kind='add')]))
        editor.resize(480, 240)
        editor.show()
        editor.appendPlainText('extra\nblocks')
        editor._bands_key = None
        editor.highlight_cursor()
        self.assertEqual(len(editor.extraSelections()), 1)
        editor.gutter.grab()
        self.assertEqual(editor._diff_row(editor.document().lastBlock()), ('', '', ''))

    def test_palette_and_font_changes_with_extra_blocks_do_not_raise_in_qt_callbacks(self):
        import io
        from contextlib import redirect_stderr
        editor = DiffEdit()
        editor.set_diff(view([line('+first', new='1', kind='add')]))
        editor.appendPlainText('extra\nblocks')
        editor.resize(480, 240)
        editor.show()
        errors = io.StringIO()
        with redirect_stderr(errors):
            for color in ('#222222', '#ffffff', '#222222'):
                palette = qt.QPalette(editor.palette())
                palette.setColor(qt.QPalette.ColorRole.Base, qt.QColor(color))
                editor.setPalette(palette)
                font = qt.QFont(editor.font())
                font.setPointSize(12)
                editor.setFont(font)
                qt.QApplication.instance().processEvents()
                editor.gutter.grab()
        self.assertNotIn('Error calling Python override', errors.getvalue())
        self.assertNotIn('IndexError', errors.getvalue())
