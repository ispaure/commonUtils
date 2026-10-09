"""Breadcrumb geometry and bounded, optional radial navigation transitions."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import unittest
from unittest.mock import patch
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser.navigation import BreadcrumbBar, BreadcrumbSeparator
from commonUtils.ui.file_browser.storage_view import RadialMap


class BrowserPolishTests(unittest.TestCase):
    def test_repeated_slate_hover_paints_keep_option_geometry_fixed(self):
        from commonUtils.ui.file_browser.editing import FilenameDelegate
        from commonUtils.ui.theme import apply_theme
        app = qt.QApplication.instance() or qt.QApplication([])
        palette, css = app.palette(), app.styleSheet()
        view = qt.QTreeView()
        model = qt.QStandardItemModel()
        model.appendRow(qt.QStandardItem('Folder name'))
        view.setModel(model)
        delegate = FilenameDelegate(view)
        option = qt.QStyleOptionViewItem()
        option.initFrom(view)
        option.widget = view
        option.rect = qt.QRect(0, 0, 300, 40)
        option.state |= qt.QStyle.StateFlag.State_MouseOver
        try:
            for mode in ('light', 'dark'):
                apply_theme(app, mode=mode)
                for _ in range(30):
                    pixmap = qt.QPixmap(300, 40)
                    pixmap.fill(app.palette().color(qt.QPalette.ColorRole.Base))
                    painter = qt.QPainter(pixmap)
                    delegate.paint(painter, option, model.index(0, 0))
                    painter.end()
                    self.assertEqual(option.rect, qt.QRect(0, 0, 300, 40))
        finally:
            controller = getattr(app, '_commonutils_theme', None)
            if controller:
                controller.deleteLater(); del app._commonutils_theme
            app.setPalette(palette); app.setStyleSheet(css)
            view.deleteLater(); app.processEvents()

    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def test_breadcrumb_chevrons_have_fixed_width_and_centered_drawing(self):
        bar = BreadcrumbBar()
        self.addCleanup(bar.deleteLater)
        bar.set_paths([Path('/'), Path('/Users'), Path('/Users/example')])
        bar.resize(500,40)
        bar.show()
        self.app.processEvents()
        separators = bar.findChildren(BreadcrumbSeparator)
        self.assertEqual(len(separators), 2)
        self.assertTrue(all(item.width() == 14 and item.height() > 10 for item in separators))
        self.assertEqual([button.toolTip() for button in bar.buttons], ['/', '/Users', '/Users/example'])
        bar.grab()  # Exercise palette-aware backdrop and chevron paint paths.
        bar.close()

    def chart(self):
        chart = RadialMap()
        self.addCleanup(chart.deleteLater)
        chart.resize(500,500)
        chart.root = Path('/root')
        chart.nodes = {chart.root: [(chart.root/'child',100)]}
        chart.totals = {chart.root: 100}
        chart.set_items(chart.nodes[chart.root])
        chart.show()
        self.app.processEvents()
        return chart

    def test_zoom_in_and_out_and_hit_geometry(self):
        chart = self.chart()
        with patch('commonUtils.ui.file_browser.storage_view.get_setting', return_value=True):
            for direction, initial in ((1,.78),(-1,1.22)):
                chart.animate_navigation(direction)
                self.assertAlmostEqual(chart._zoom, initial)
                chart._animation.setCurrentTime(120)
                self.assertNotEqual(chart._zoom, initial)
                chart.grab()
                self.assertTrue(chart.sectors)
                shape = chart.sectors[0][2]
                # Hit testing uses transformed paths, matching what was painted.
                self.assertIsNotNone(chart.hit(qt.QPointF(chart.width()/2 + 60*chart._zoom, chart.height()/2)))
                self.assertTrue(shape.boundingRect().width() > 0)
                chart._animation.setCurrentTime(240)
                self.assertAlmostEqual(chart._zoom, 1.0)
        chart.close()

    def test_center_navigation_remains_responsive_during_zoom(self):
        from unittest.mock import Mock
        chart = self.chart()
        requested = Mock()
        chart.parent_requested.connect(requested)
        with patch('commonUtils.ui.file_browser.storage_view.get_setting', return_value=True):
            chart.animate_navigation(1)
            event = qt.QMouseEvent(qt.QEvent.Type.MouseButtonDblClick, qt.QPointF(250,250),
                                  qt.QPointF(250,250), qt.Qt.MouseButton.LeftButton,
                                  qt.Qt.MouseButton.LeftButton, qt.Qt.KeyboardModifier.NoModifier)
            chart.mouseDoubleClickEvent(event)
        requested.assert_called_once_with()
        chart.close()

    def test_disabled_animation_and_hidden_chart_do_not_tick(self):
        chart = self.chart()
        with patch('commonUtils.ui.file_browser.storage_view.get_setting', return_value=False):
            chart.animate_navigation(1)
            self.assertEqual(chart._animation.state(), qt.QAbstractAnimation.State.Stopped)
            self.assertEqual(chart._zoom, 1.0)
        with patch('commonUtils.ui.file_browser.storage_view.get_setting', return_value=True):
            chart.animate_navigation(1)
            chart.hide()
            self.assertEqual(chart._animation.state(), qt.QAbstractAnimation.State.Stopped)
            self.assertEqual(chart._zoom, 1.0)


if __name__ == '__main__':
    unittest.main()
