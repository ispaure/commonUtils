"""The organized Qt package keeps the historical facade and customization hooks."""
import importlib
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from unittest.mock import Mock, patch
from commonUtils.ui import pyside as qt


class PySideCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def test_historical_paths_share_one_module(self):
        from commonUtils import pySideUtils
        from commonUtils.pySideUtils import Window, QApplication, OS, get_os
        self.assertIs(pySideUtils, qt)
        self.assertIs(importlib.import_module('commonUtils.pySideUtils'), qt)
        self.assertIs(Window, qt.Window)
        self.assertIs(QApplication, qt.QApplication)
        self.assertIs(OS, qt.OS)
        self.assertIs(get_os, qt.get_os)
        self.assertTrue(hasattr(qt, '__author__'))

    def test_public_customizations_cross_component_boundaries(self):
        widget = qt.QWidget()
        with patch.object(qt, 'set_font') as font:
            qt.Label('Label', widget, qt.QRect(0, 0, 100, 30))
        font.assert_called_once()
        with patch.object(qt, 'get_scale_multiplier', return_value=2):
            self.assertEqual(qt.create_size(10, 20), qt.QSize(20, 40))
        with patch.object(qt, 'rog_ally', True):
            area = qt.create_scroll_area(widget, qt.QRect(0, 0, 100, 100), qt.QSize(200, 200))
            self.assertIn('30px', area.parentWidget().parentWidget().styleSheet())
        factory = Mock(return_value=Mock())
        factory.return_value.exec.return_value = qt.QMessageBox.StandardButton.Yes
        with patch.object(qt, 'create_msg_box_base', factory):
            self.assertTrue(qt.display_msg_box_yes_no('Title', 'Message'))
        factory.assert_called_once()
        widget.close()

    def test_public_classes_keep_module_and_inheritance(self):
        self.assertEqual(qt.Window.__module__, 'commonUtils.ui.pyside')
        self.assertTrue(issubclass(qt.ProgressBarWindow, qt.Window))
        progress = qt.ProgressBarWindow('Progress')
        progress.update_progress(35)
        self.assertEqual(progress.progress_bar.value(), 35)
        progress.dlg.close()
