"""Platform folder shortcuts, scoped to file views rather than text controls."""
import sys
from .. import pyside as qt


def command(key, modifiers, platform):
    keys, mods = qt.Qt.Key, qt.Qt.KeyboardModifier
    if modifiers == mods.NoModifier:
        if key == keys.Key_F2:
            return 'rename'
        if key in (keys.Key_Return, keys.Key_Enter):
            return 'rename' if platform == 'darwin' else 'open'
        if key == keys.Key_Backspace and platform == 'win32':
            return 'up'
    # Qt maps its Control modifier to Command on macOS.
    if platform == 'darwin' and modifiers == mods.ControlModifier:
        return {keys.Key_Up: 'up', keys.Key_Down: 'open', keys.Key_O: 'open'}.get(key)
    if modifiers == mods.AltModifier:
        return {keys.Key_Up: 'up', keys.Key_Left: 'back', keys.Key_Right: 'forward'}.get(key)
    return None


class BrowserKeyboard(qt.QObject):
    def __init__(self, browser):
        super().__init__(browser)
        self.browser = browser
        self.platform = sys.platform
        qt.QApplication.instance().installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() not in (qt.QEvent.Type.ShortcutOverride, qt.QEvent.Type.KeyPress):
            return False
        browser = self.browser
        if (browser.stopping or not isinstance(watched, qt.QWidget)
                or isinstance(watched, (qt.QLineEdit, qt.QTextEdit, qt.QPlainTextEdit))):
            return False
        panes = (browser.views.currentWidget(), browser.index_search.results)
        if not any(watched is pane or pane.isAncestorOf(watched) for pane in panes):
            return False
        action = command(event.key(), event.modifiers(), self.platform)
        if action is None:
            return False
        event.accept()
        if event.type() == qt.QEvent.Type.KeyPress:
            if action == 'rename':
                browser.file_actions.rename_selected()
            elif action == 'open':
                selected = browser.selected_objects()
                if len(selected) == 1:
                    browser._activate_item(selected[0])
            else:
                getattr(browser.navigation, action).click()
        return True
