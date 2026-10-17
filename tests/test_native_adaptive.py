"""Allocated logical width, independent of device branding or pixel density."""
from types import SimpleNamespace
import unittest

from commonUtils.ui.native.adaptive import SidebarPolicy, allocated_width


class AdaptiveWidthTests(unittest.TestCase):
    def test_fits_depends_on_pane_budget(self):
        policy = SidebarPolicy()
        for width, expanded in ((390, False), (600, False), (719, False), (720, True),
                                (820, True), (1024, True), (500, False)):
            self.assertEqual(policy.fits(width), expanded)
        self.assertFalse(SidebarPolicy(detail_minimum=600).fits(820))

    def test_measures_parent_allocation_and_caps_at_host_window(self):
        ios = type('Impl', (), {'__module__': 'toga_iOS.widgets.box'})()
        ios.native = SimpleNamespace(bounds=SimpleNamespace(size=SimpleNamespace(width=510)))
        widget = SimpleNamespace(parent=SimpleNamespace(_impl=ios))
        self.assertEqual(allocated_width(widget, 1024), 510)
        self.assertEqual(allocated_width(widget, 390), 390)
        android = type('Impl', (), {'__module__': 'toga_android.widgets.box'})()
        android.native = SimpleNamespace(getWidth=lambda: 1560,
            getContext=lambda: SimpleNamespace(getResources=lambda: SimpleNamespace(
                getDisplayMetrics=lambda: SimpleNamespace(density=3))))
        widget.parent._impl = android
        self.assertEqual(allocated_width(widget, 1200), 520)
        android.native.getWidth = lambda: 0
        self.assertEqual(allocated_width(widget, 600), 600)
        widget.parent = None
        self.assertEqual(allocated_width(widget, 390), 390)
