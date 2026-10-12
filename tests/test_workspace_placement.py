"""Assert actual pane coordinates, not merely accepted docking operations."""
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.workspaces.workspace import Workspace
from commonUtils.ui.workspaces.workspace_policy import WorkspacePolicy


class PlacementTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def settle(self):
        for _ in range(12):
            self.app.processEvents()

    def workspace(self, names, rtl=False):
        w = Workspace(lambda name: qt.QLabel(name), dock_group='placement', policy=WorkspacePolicy())
        if rtl:
            w.setLayoutDirection(qt.Qt.LayoutDirection.RightToLeft)
        w.resize(1200, 650)
        w.show()
        for name in names:
            w.add_view(name)
        self.settle()
        return w

    def order(self, workspace, expected):
        self.settle()
        def rectangle(dock):
            members = [dock, *workspace.tabifiedDockWidgets(dock)]
            return next(item.geometry() for item in members if workspace.rect().intersects(item.geometry()))
        actual = sorted(expected, key=lambda dock: rectangle(dock).center().x())
        self.assertEqual([d.widget().text() for d in actual], [d.widget().text() for d in expected])
        for left, right in zip(expected, expected[1:]):
            self.assertNotIn(right, workspace.tabifiedDockWidgets(left))
            self.assertLess(rectangle(left).right(), rectangle(right).left())
            self.assertGreater(rectangle(left).bottom(), rectangle(right).top())
            self.assertGreater(rectangle(right).bottom(), rectangle(left).top())

    def test_repeated_left_right_moves_keep_exact_neighbor_order(self):
        for rtl in (False, True):
            w = self.workspace('ABCD', rtl)
            a, b, c, d = w.docks
            for moving, anchor in ((b,a),(c,b),(d,c)):
                self.assertTrue(w.adopt(moving, placement='right', anchor=anchor))
                self.settle()
            expected = [a,b,c,d]
            self.order(w, expected)
            for moving in (a,b,c,d,a,d):
                for anchor in (a,b,c,d):
                    if moving is anchor:
                        continue
                    for side in ('left','right'):
                        expected.remove(moving)
                        position = expected.index(anchor) + (side == 'right')
                        expected.insert(position, moving)
                        self.assertTrue(w.adopt(moving, placement=side, anchor=anchor))
                        self.order(w, expected)
            w.close()

    def test_split_preserves_target_tab_companions_and_other_columns(self):
        w = self.workspace('ABCDE')
        a,b,c,d,e = w.docks
        w.adopt(c, placement='right', anchor=a)
        w.adopt(d, placement='right', anchor=c)
        self.settle()
        self.assertEqual(set(w.tabifiedDockWidgets(a)), {b,e})
        bar = next(bar for bar in w.findChildren(qt.QTabBar)
                   if bar.parent() is w and bar.isVisible() and bar.count() == 3)
        bar.moveTab(0,2)
        self.settle()
        original_order = [w._tab_dock(bar,i) for i in range(3)]
        for moving,anchor,side,expected in (
            (d,a,'left',[d,a,c]), (c,a,'right',[d,a,c]),
            (d,c,'right',[a,c,d]), (c,a,'left',[c,a,d]),
        ):
            w.adopt(moving,placement=side,anchor=anchor)
            self.order(w,expected)
            self.assertEqual(set(w.tabifiedDockWidgets(a)), {b,e})
            bar = next(bar for bar in w.findChildren(qt.QTabBar)
                       if bar.parent() is w and bar.isVisible() and bar.count() == 3)
            self.assertEqual([w._tab_dock(bar,i) for i in range(3)],original_order)

    def test_cross_window_center_drop_uses_pointer_anchor(self):
        w = self.workspace('ABCD')
        a,b,c,d = w.docks
        w.adopt(c,placement='right',anchor=a)
        w.adopt(d,placement='tabs',anchor=c)
        self.settle()
        source = self.workspace('X')
        incoming = source.active_dock
        self.assertTrue(w.adopt(incoming,placement='tabs',anchor=a))
        self.settle()
        self.assertIn(incoming,w.tabifiedDockWidgets(a))
        self.assertNotIn(incoming,w.tabifiedDockWidgets(c))
        self.assertEqual(set(w.tabifiedDockWidgets(c)), {d})
        self.assertEqual(source.docks,[])

    def test_side_drop_preserves_an_existing_vertical_partition(self):
        w = self.workspace('ABCD')
        a,b,c,d = w.docks
        for moving, anchor in ((b,a),(c,b),(d,c)):
            w.adopt(moving, placement='right', anchor=anchor)
            self.settle()
        w.splitDockWidget(c,d,qt.Qt.Orientation.Vertical)
        self.settle()
        w.adopt(b,placement='left',anchor=c)
        self.settle()
        self.assertLess(a.geometry().right(),b.geometry().left())
        self.assertLess(b.geometry().right(),c.geometry().left())
        self.assertLess(b.geometry().bottom(),d.geometry().top())
        self.assertLess(c.geometry().bottom(),d.geometry().top())
        self.assertGreater(a.height(),d.height())

    def test_splitting_one_column_keeps_neighbor_width(self):
        w = self.workspace('ABC')
        a,b,c = w.docks
        w.adopt(c,placement='right',anchor=a)
        self.settle()
        w.resizeDocks([a,c],[600,600],qt.Qt.Orientation.Horizontal)
        self.settle()
        width = c.width()
        w.adopt(b,placement='left',anchor=a)
        self.settle()
        self.order(w,[b,a,c])
        self.assertAlmostEqual(c.width(),width,delta=12)
