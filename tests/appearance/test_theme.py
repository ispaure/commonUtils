"""Opt-in theme, accessible palettes and active workspace tab rendering."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import importlib
from dataclasses import replace
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from unittest.mock import patch
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.appearance.theme import apply_theme, SLATE_LIGHT, SLATE_DARK, configured_colors
from commonUtils.ui.workspaces.workspace import Workspace


def contrast(first, second):
    def luminance(hex_color):
        values=[int(hex_color[n:n+2],16)/255 for n in (1,3,5)]
        values=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
        return sum(v*w for v,w in zip(values,(.2126,.7152,.0722)))
    a,b=sorted((luminance(first),luminance(second)))
    return (b+.05)/(a+.05)


class ThemeTests(QtTestCase):
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
        import commonUtils.ui.appearance.theme as theme
        importlib.reload(theme)
        self.assertEqual(self.app.styleSheet(),self.old_css)
        for colors in (SLATE_LIGHT,SLATE_DARK):
            self.assertGreaterEqual(contrast(colors.text,colors.surface),4.5)
            self.assertGreaterEqual(contrast(colors.muted,colors.surface),4.5)
            self.assertEqual(colors.selected_text, '#ffffff')
            self.assertGreaterEqual(contrast(colors.selected_text,colors.selection_background or colors.accent),4.5)
        for colors in (configured_colors(False), configured_colors(True)):
            self.assertGreaterEqual(contrast(colors.text, colors.surface), 4.5)
            self.assertGreaterEqual(contrast(colors.selected_text, colors.selection_background), 4.5)

    def test_switching_reuses_controller_and_does_not_grow_stylesheet(self):
        controller=apply_theme(self.app,mode='light');light=self.app.styleSheet()
        self.assertEqual(self.app.palette().color(qt.QPalette.ColorRole.Highlight).name(),configured_colors(False).accent)
        self.assertIs(controller,apply_theme(self.app,mode='dark'))
        self.assertEqual(self.app.palette().color(qt.QPalette.ColorRole.Base).name(),configured_colors(True).surface)
        controller.set_mode('light');self.assertEqual(self.app.styleSheet(),light)
        controller.set_mode('system')
        with self.assertRaises(ValueError): controller.set_mode('unknown')

    def test_mode_switch_keeps_style_engine_and_repeated_apply_does_no_work(self):
        controller = apply_theme(self.app, mode='light')
        style = self.app.style()
        with patch.object(self.app, 'setStyle', wraps=self.app.setStyle) as set_style:
            controller.set_mode('dark')
            set_style.assert_not_called()
        self.assertIs(self.app.style(), style)
        with patch.object(self.app, 'setPalette') as set_palette, \
                patch.object(self.app, 'setStyleSheet') as set_sheet:
            controller._apply()
            set_palette.assert_not_called()
            set_sheet.assert_not_called()

    def test_system_notifications_coalesce_and_theme_application_is_not_reentrant(self):
        controller = apply_theme(self.app, mode='system')
        with patch.object(controller, '_apply_colors', wraps=controller._apply_colors) as apply:
            for _ in range(20):
                controller._system_changed(qt.Qt.ColorScheme.Dark)
            self.app.processEvents()
            self.assertEqual(apply.call_count, 1)
        original = self.app.setPalette

        def nested_palette(value):
            original(value)
            controller._apply()

        with patch.object(self.app, 'setPalette', side_effect=nested_palette) as set_palette:
            controller.set_mode('dark')
            self.assertLessEqual(set_palette.call_count, 1)

    def test_accent_and_tint_repaint_existing_controls_without_replacing_stylesheet(self):
        host = qt.QWidget()
        self.addCleanup(host.deleteLater)
        layout = qt.QVBoxLayout(host)
        field = qt.QLineEdit()
        button = qt.QPushButton()
        button.setCheckable(True)
        button.setChecked(True)
        progress = qt.QProgressBar()
        progress.setValue(100)
        progress.setTextVisible(False)
        for widget in (field, button, progress):
            widget.setFixedSize(150, 35)
            layout.addWidget(widget)
        host.show()
        controller = apply_theme(self.app, mode='light')
        try:
            for mode in ('light', 'dark'):
                controller.set_mode(mode)
                for accent, surface in (('#007755', '#aaccdd'), ('#ffff00', '#334455')):
                    colors = replace(configured_colors(mode == 'dark'), accent=accent,
                                     selection_background=accent, surface=surface)
                    with patch('commonUtils.ui.appearance.theme.configured_colors', return_value=colors), \
                            patch.object(self.app, 'setStyleSheet', wraps=self.app.setStyleSheet) as set_sheet:
                        controller._apply()
                        self.app.processEvents()
                        set_sheet.assert_not_called()
                        # Inspect pixels: palette values alone cannot detect QSS
                        # render rules retaining brushes from the previous accent.
                        for widget, expected in ((field, surface), (button, accent), (progress, accent)):
                            actual = widget.grab().toImage().pixelColor(70, 15).name()
                            self.assertEqual(actual, expected, f'{type(widget).__name__} in {mode}')
        finally:
            host.close()

    def test_compact_form_fields_have_room_for_text_in_both_modes(self):
        controller = apply_theme(self.app, mode='light')
        host = qt.QWidget()
        layout = qt.QVBoxLayout(host)
        controls = [qt.QLineEdit('Metadata'), qt.QComboBox(), qt.QSpinBox()]
        controls[1].setEditable(True)
        controls[1].addItem('Publisher')
        for control in controls:
            control.setFixedHeight(22)
            layout.addWidget(control)
        host.show()
        try:
            for mode in ('light', 'dark'):
                controller.set_mode(mode)
                self.app.processEvents()
                for control in controls:
                    line = control if isinstance(control, qt.QLineEdit) else control.findChild(qt.QLineEdit)
                    option = qt.QStyleOptionFrame()
                    option.initFrom(line)
                    option.rect = line.rect()
                    text_rect = line.style().subElementRect(qt.QStyle.SubElement.SE_LineEditContents, option, line)
                    self.assertGreaterEqual(text_rect.height(), line.fontMetrics().height(),
                                            f'{type(control).__name__} in {mode} mode')
                    self.assertEqual(control.height(), 22)
        finally:
            host.close(); host.deleteLater(); self.app.processEvents()

    def test_workspace_selected_tabs_keep_accent_in_both_modes(self):
        controller=apply_theme(self.app,mode='light')
        workspace=Workspace(lambda argument:qt.QWidget());workspace.resize(650,300)
        first=workspace.add_view();workspace.add_view();workspace.show()
        for mode, colors in [('light',configured_colors(False)),('dark',configured_colors(True))]:
            controller.set_mode(mode)
            for _ in range(5):self.app.processEvents()
            bars=[bar for bar in workspace.findChildren(qt.QTabBar) if bar.count()==2]
            self.assertTrue(bars)
            self.assertIs(workspace.active_dock, workspace._tab_dock(bars[0], bars[0].currentIndex()))
            bars[0].setCurrentIndex(0)
            self.app.processEvents()
            self.assertIs(workspace.active_view, first)
            bars[0].setCurrentIndex(1)
            self.app.processEvents()
            self.assertIs(workspace.active_view, workspace.docks[1].widget())
            self.assertIn('palette(highlight)',bars[0].styleSheet())
            self.assertEqual(bars[0].palette().color(qt.QPalette.ColorRole.Highlight).name(),colors.selection_background or colors.accent)
            self.assertTrue(workspace.docks[0].tab_header.title.font().bold())
        workspace.close();self.app.processEvents()
