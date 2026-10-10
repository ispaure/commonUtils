"""Focused cursor commands shared by plain, source and formatted text editors."""
from . import pyside as qt


def text_units(text):
    """Qt cursor positions count UTF-16 code units, including supplementary text."""
    return len(text.encode('utf-16-le')) // 2


def wrap_selection(editor, opening, closing=None, *, keep_selected=True, reset_format=False):
    """Wrap in one undo step; caller chooses selection and formatting policy."""
    if editor.isReadOnly():
        return False
    closing = opening if closing is None else closing
    cursor = editor.textCursor()
    start = cursor.selectionStart()
    text = cursor.selectedText().replace('\u2029', '\n')
    cursor.beginEditBlock()
    if reset_format:
        cursor.insertText(opening + text + closing, qt.QTextCharFormat())
    else:
        cursor.insertText(opening + text + closing)
    first = start + text_units(opening)
    if keep_selected:
        cursor.setPosition(first)
        cursor.setPosition(first + text_units(text), qt.QTextCursor.MoveMode.KeepAnchor)
    else:
        cursor.setPosition(first + text_units(text))
    cursor.endEditBlock()
    editor.setTextCursor(cursor)
    return True
