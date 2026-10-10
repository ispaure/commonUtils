"""Painted icon copies survive garbage collection and update with the palette."""
import gc
import unittest
from commonUtils.ui import pyside as qt
from commonUtils.ui.icons import painted_icon, set_painted_icon
from commonUtils.ui.reader_chrome import ReaderIcon


class IconTests(unittest.TestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def test_native_copies_survive_owner_deletion_and_garbage_collection(self):
        for _ in range(40):
            owner = qt.QWidget()
            button = qt.QToolButton(owner)
            set_painted_icon(button, ReaderIcon, 'play')
            copy = qt.QIcon(button.icon())
            owner.deleteLater()
            self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
            del owner, button
            gc.collect()
            for state in (qt.QIcon.State.Off, qt.QIcon.State.On):
                for mode in (qt.QIcon.Mode.Normal, qt.QIcon.Mode.Disabled):
                    self.assertFalse(copy.pixmap(qt.QSize(32, 32), mode, state).isNull())

    def test_icon_binding_refreshes_on_theme_changes_and_reuses_rendered_icons(self):
        button = qt.QToolButton()
        self.addCleanup(button.deleteLater)
        set_painted_icon(button, ReaderIcon, 'play')
        before = button.icon().cacheKey()
        self.assertEqual(before, painted_icon(ReaderIcon, 'play').cacheKey())
        original = self.app.palette()
        palette = qt.QPalette(original)
        palette.setColor(qt.QPalette.ColorRole.ButtonText, qt.QColor('magenta'))
        try:
            self.app.setPalette(palette)
            self.assertNotEqual(button.icon().cacheKey(), before)
            self.assertEqual(button.icon().cacheKey(), painted_icon(ReaderIcon, 'play').cacheKey())
        finally:
            self.app.setPalette(original)
