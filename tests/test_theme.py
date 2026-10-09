"""Opt-in theme, accessible palettes and active workspace tab rendering."""
import importlib
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from commonUtils.ui import pyside as qt
from commonUtils.ui.theme import apply_theme, SLATE_LIGHT, SLATE_DARK
from commonUtils.ui.workspace import Workspace


def contrast(first, second):
    def luminance(hex_color):
        values=[int(hex_color[n:n+2],16)/255 for n in (1,3,5)]
        values=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
        return sum(v*w for v,w in zip(values,(.2126,.7152,.0722)))
    a,b=sorted((luminance(first),luminance(second)))
    return (b+.05)/(a+.05)


class ThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=qt.QApplication.instance() or qt.QApplication([])

    def setUp(self):
        self.old_palette=self.app.palette();self.old_css=self.app.styleSheet()

    def tearDown(self):
        controller=getattr(self.app,'_commonutils_theme',None)
        if controller:
            controller.deleteLater();del self.app._commonutils_theme
        self.app.setPalette(self.old_palette);self.app.setStyleSheet(self.old_css)
        self.app.sendPostedEvents(None,qt.QEvent.Type.DeferredDelete)

    def test_import_is_opt_in_and_palette_pairs_are_readable(self):
        import commonUtils.ui.theme as theme
        importlib.reload(theme)
        self.assertEqual(self.app.styleSheet(),self.old_css)
        for colors in (SLATE_LIGHT,SLATE_DARK):
            self.assertGreaterEqual(contrast(colors.text,colors.surface),4.5)
            self.assertGreaterEqual(contrast(colors.muted,colors.surface),4.5)
            self.assertGreaterEqual(contrast(colors.selected_text,colors.accent),4.5)

    def test_switching_reuses_controller_and_does_not_grow_stylesheet(self):
        controller=apply_theme(self.app,mode='light');light=self.app.styleSheet()
        self.assertEqual(self.app.palette().color(qt.QPalette.ColorRole.Highlight).name(),SLATE_LIGHT.accent)
        self.assertIs(controller,apply_theme(self.app,mode='dark'))
        self.assertEqual(self.app.palette().color(qt.QPalette.ColorRole.Base).name(),SLATE_DARK.surface)
        controller.set_mode('light');self.assertEqual(self.app.styleSheet(),light)
        controller.set_mode('system')
        with self.assertRaises(ValueError): controller.set_mode('unknown')

    def test_workspace_selected_tabs_keep_accent_in_both_modes(self):
        controller=apply_theme(self.app,mode='light')
        workspace=Workspace(lambda argument:qt.QWidget());workspace.resize(650,300)
        first=workspace.add_view();workspace.add_view();workspace.show()
        for mode, colors in [('light',SLATE_LIGHT),('dark',SLATE_DARK)]:
            controller.set_mode(mode)
            for _ in range(5):self.app.processEvents()
            bars=[bar for bar in workspace.findChildren(qt.QTabBar) if bar.count()==2]
            self.assertTrue(bars)
            self.assertIn('palette(highlight)',bars[0].styleSheet())
            self.assertEqual(bars[0].palette().color(qt.QPalette.ColorRole.Highlight).name(),colors.accent)
            self.assertTrue(workspace.docks[0].tab_header.title.font().bold())
        workspace.close();self.app.processEvents()
