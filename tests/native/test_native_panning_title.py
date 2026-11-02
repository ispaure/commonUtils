"""Verify the native title bindings without requiring a mobile OS."""
from importlib.util import find_spec
import os
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from commonUtils.testing.stages import TestStage

os.environ.setdefault('TOGA_BACKEND', 'toga_dummy')
HAS_TOGA = find_spec('toga') is not None
if HAS_TOGA:
    from commonUtils.ui.native import panning_title

TEST_STAGE = TestStage.REGRESSION


@unittest.skipUnless(HAS_TOGA, 'Native title contracts require Toga')
class PanningTitleTests(unittest.TestCase):
    def test_android_binding_and_host_override_share_one_native_policy(self):
        bridge, label = Mock(), Mock()
        with patch.dict('sys.modules', {'java': NS(jclass=bridge)}):
            panning_title.configure_android_title(label)
            panning_title.set_android_title_motion_suppressed(True)
            panning_title.set_android_title_motion_suppressed(False)
        self.assertTrue(all(call.args == ('io.github.ispaure.commonutils.TitleMotion',)
                            for call in bridge.call_args_list))
        bridge.return_value.bind.assert_called_once_with(label)
        self.assertEqual([call.args for call in bridge.return_value.setSuppressed.call_args_list],
                         [(True,), (False,)])

    def test_android_replay_does_not_enable_a_suppressed_title(self):
        backend = type('AndroidLabel', (), {'__module__': 'toga_android.widgets.label'})
        native = Mock()
        label = NS(factory=NS(Label=backend), _impl=NS(native=native))
        native.isSelected.return_value = False
        panning_title.PanningTitleLabel.restart_pan(label)
        native.setSelected.assert_not_called()
        native.isSelected.return_value = True
        panning_title.PanningTitleLabel.restart_pan(label)
        self.assertEqual([call.args for call in native.setSelected.call_args_list], [(False,), (True,)])

    def test_toga_apple_backend_uses_the_same_native_label_as_navigation(self):
        class Label:
            __module__ = 'toga_iOS.widgets.label'

            def __init__(self, interface):
                self.interface = interface
                self.add_constraints = Mock()
                self.create()

        title = NS(factory=NS(Label=Label))
        factory = Mock()
        with patch.dict('sys.modules', {'rubicon.objc': NS(ObjCClass=factory)}):
            impl = panning_title.PanningTitleLabel._create(title)
        factory.assert_called_once_with('CommonUtilsPanningTitle')
        self.assertIs(impl.native, factory.return_value.new.return_value)
        self.assertEqual(impl.native.lineBreakMode, 5)
        impl.add_constraints.assert_called_once()
