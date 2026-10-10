"""Radial redraw cost, geometric hit testing and cursor-following hover details."""
import math
from pathlib import Path
from unittest.mock import patch
import unittest
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser.storage_view import RadialMap


class RadialRenderingTests(unittest.TestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.chart = RadialMap()
        self.chart.resize(400, 400)
        self.chart.show()
        self.addCleanup(self.chart.deleteLater)
        self.root = Path('/fixture')
        self.first, self.second = self.root/'first', self.root/'second'
        self.nested = self.first/'nested'
        self.chart.root = self.root
        self.chart.nodes = {self.root: [(self.first, 50), (self.second, 50)],
                            self.first: [(self.nested, 50)]}
        self.chart.totals = {self.root: 100, self.first: 50}
        self.chart.set_items(self.chart.nodes[self.root])

    def point(self, angle, depth):
        ring = (min(self.chart.width(), self.chart.height()) / 2 - 12) / 5
        radius = ring * (depth + .5) * self.chart._zoom
        angle = math.radians(angle)
        return qt.QPointF(self.chart.width()/2 + radius*math.cos(angle),
                         self.chart.height()/2 - radius*math.sin(angle))

    def test_repaint_selection_and_zoom_reuse_scene_resize_rebuilds(self):
        with patch.object(self.chart, '_build_scene', wraps=self.chart._build_scene) as build:
            self.chart.grab()
            self.chart.selected_path = self.first
            for frame in range(10):
                self.chart._zoom_start = .78
                self.chart._zoom_frame(frame/10)
                self.chart.grab()
                self.assertEqual(self.chart.hit(self.point(90, 1)), (self.first, 50))
            self.assertEqual(build.call_count, 1)
            self.chart.resize(420, 420); self.chart.grab()
            self.assertEqual(build.call_count, 2)
            self.chart.totals[self.root] = 200
            self.chart.set_items(self.chart.nodes[self.root]); self.chart.grab()
            self.assertEqual(build.call_count, 3)

    def test_hit_testing_handles_nested_rings_zoom_and_partial_index_gaps(self):
        self.chart.grab()
        self.assertEqual(self.chart.hit(self.point(90, 2)), (self.nested, 50))
        self.assertEqual(self.chart.hit(self.point(270, 1)), (self.second, 50))
        self.assertIsNone(self.chart.hit(self.point(270, 2)))
        self.assertIsNone(self.chart.hit(qt.QPointF(200, 200)))
        self.chart._zoom = .78
        self.assertEqual(self.chart.hit(self.point(90, 2)), (self.nested, 50))
        self.chart.totals[self.root] = 200
        self.chart.set_items(self.chart.nodes[self.root])
        self.assertIsNone(self.chart.hit(self.point(270, 1)))

    def test_hover_moves_inside_same_folder_and_disappears_when_leaving(self):
        positions = []
        for angle in (70, 80):
            point = self.point(angle, 1)
            global_point = self.chart.mapToGlobal(point.toPoint())
            event = qt.QMouseEvent(qt.QEvent.Type.MouseMove, point, qt.QPointF(global_point),
                qt.Qt.MouseButton.NoButton, qt.Qt.MouseButton.NoButton, qt.Qt.KeyboardModifier.NoModifier)
            self.app.sendEvent(self.chart, event)
            self.assertTrue(self.chart.hover.label.isVisible())
            self.assertIn(str(self.first), self.chart.hover.label.text())
            positions.append(self.chart.hover.label.pos())
        self.assertNotEqual(*positions)
        self.app.sendEvent(self.chart, qt.QEvent(qt.QEvent.Type.Leave))
        self.assertFalse(self.chart.hover.label.isVisible())

    def test_tooltip_flips_near_screen_edge_and_keeps_following_pointer(self):
        bounds = self.chart.screen().availableGeometry()
        points = [qt.QPoint(bounds.right() - offset, bounds.center().y()) for offset in (20, 30)]
        positions = []
        for point in points:
            self.chart.hover.show('Folder details', point)
            rect = self.chart.hover.label.frameGeometry()
            self.assertTrue(bounds.contains(rect))
            self.assertLess(rect.right(), point.x())
            positions.append(rect.topLeft())
        self.assertEqual(positions[0].x() - positions[1].x(), 10)

    def test_loading_has_no_hover_hit_or_popup(self):
        self.chart.loading = True
        self.assertIsNone(self.chart.hit(self.point(90, 1)))
