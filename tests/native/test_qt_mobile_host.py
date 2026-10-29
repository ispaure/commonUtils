"""Host admission contracts; simulator evidence belongs to the consuming app."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from commonUtils.runtime.platform import OS
from commonUtils.runtime.platform import capabilities as policy

class QtMobileHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_explicit_host_admits_only_qt(self):
        with patch.object(policy, '_qt_host', None), patch.object(policy, 'get_os', return_value=OS.IOS):
            self.assertEqual(policy.capability_status(policy.Capability.QT_UI).state, policy.CapabilityState.UNAVAILABLE)
            policy.register_qt_ui_host(self.app)
            self.assertEqual(policy.capability_status(policy.Capability.QT_UI).state, policy.CapabilityState.IMPLEMENTED)
            for capability in (policy.Capability.DESKTOP_UI, policy.Capability.SHELL,
                               policy.Capability.FILE_DIALOGS, policy.Capability.DEFAULT_STORAGE,
                               policy.Capability.EXTERNAL_APPLICATIONS):
                with self.assertRaises(policy.UnsupportedCapabilityError):
                    policy.require_capability(capability)

    def test_requires_live_application_and_supported_version(self):
        with self.assertRaises(ValueError):
            policy.register_qt_ui_host(object())
        with patch('PySide6.QtCore.qVersion', return_value='6.11.0'), self.assertRaises(ValueError):
            policy.register_qt_ui_host(self.app)
