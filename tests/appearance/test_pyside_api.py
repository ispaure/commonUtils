"""Qt exports and customization hooks work across implementation components."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import importlib
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import Mock, patch
from commonUtils.ui import pyside as qt


class PySideAPITests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def test_public_exports_share_one_module(self):
        from commonUtils.ui import pyside as pySideUtils
        from commonUtils.ui.pyside import Window, QApplication, OS, get_os
        self.assertIs(pySideUtils, qt)
        self.assertIs(importlib.import_module('commonUtils.ui.pyside'), qt)
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

    def test_resizable_scroll_area_keeps_native_defaults_and_independent_policies(self):
        owner = qt.QWidget()
        self.addCleanup(owner.deleteLater)
        native_frame = qt.QScrollArea(owner).frameShape()
        as_needed = qt.Qt.ScrollBarPolicy.ScrollBarAsNeeded
        horizontal_off = qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        vertical_on = qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOn

        default = qt.resizable_scroll_area(owner)
        self.assertIsInstance(default, qt.QScrollArea)
        self.assertIs(default.parentWidget(), owner)
        self.assertTrue(default.widgetResizable())
        self.assertEqual(default.frameShape(), native_frame)
        self.assertEqual(default.horizontalScrollBarPolicy(), as_needed)
        self.assertEqual(default.verticalScrollBarPolicy(), as_needed)

        custom = qt.resizable_scroll_area(
            owner, framed=False, horizontal_policy=horizontal_off, vertical_policy=vertical_on)
        self.assertTrue(custom.widgetResizable())
        self.assertEqual(custom.frameShape(), qt.QFrame.Shape.NoFrame)
        self.assertEqual(custom.horizontalScrollBarPolicy(), horizontal_off)
        self.assertEqual(custom.verticalScrollBarPolicy(), vertical_on)

    def test_fixed_scroll_area_keeps_content_contract_and_device_styles(self):
        owner = qt.QWidget()
        self.addCleanup(owner.deleteLater)
        bounds = qt.QRect(5, 10, 100, 120)
        minimum = qt.QSize(180, 200)
        with patch.object(qt, 'rog_ally', True):
            content = qt.create_scroll_area(owner, bounds, minimum)
            layout_area = qt.resizable_scroll_area(owner)
        area = owner.findChild(qt.QScrollArea, 'scroll_area')
        self.assertIs(area.widget(), content)
        self.assertEqual(area.geometry(), bounds)
        self.assertEqual(content.objectName(), 'scroll_area_widget')
        self.assertEqual(content.minimumSize(), minimum)
        self.assertIn('30px', area.styleSheet())
        self.assertEqual(layout_area.styleSheet(), '')

    def test_selection_details_replaces_actions_and_clears_empty_lists(self):
        from commonUtils.ui.pyside.selection_details import SelectionDetails

        clicked = Mock()

        def show_entry(entry):
            panel.add_detail_action(entry, lambda: clicked(entry), enabled=entry != 'disabled')

        panel = SelectionDetails('Entries', show_entry)
        panel.set_entries(('first', 'second', 'disabled'), label=str)
        self.assertEqual(panel.selection_list.currentRow(), 0)
        first_button = panel.details_layout.itemAt(0).widget()
        first_button.click()
        clicked.assert_called_once_with('first')

        panel.selection_list.setCurrentRow(1)
        second_button = panel.details_layout.itemAt(0).widget()
        self.assertIsNot(first_button, second_button)
        second_button.click()
        clicked.assert_called_with('second')

        panel.selection_list.setCurrentRow(2)
        panel.details_layout.itemAt(0).widget().click()
        self.assertEqual(clicked.call_count, 2)

        panel.set_entries((), label=str)
        self.assertEqual(panel.selection_list.currentRow(), -1)
        self.assertEqual(panel.details_layout.count(), 0)
        panel.close()

    def test_public_classes_keep_module_and_inheritance(self):
        self.assertEqual(qt.Window.__module__, 'commonUtils.ui.pyside')
        self.assertTrue(issubclass(qt.ProgressBarWindow, qt.Window))
        progress = qt.ProgressBarWindow('Progress')
        progress.update_progress(35)
        self.assertEqual(progress.progress_bar.value(), 35)
        progress.dlg.close()

    def test_cocoa_main_window_activation_waits_for_the_event_loop(self):
        window = qt.Window('Startup', main_window=True)
        with patch.object(qt.QApplication, 'platformName', return_value='cocoa'), \
                patch.object(qt.QTimer, 'singleShot') as scheduled:
            window.display_ui()
        self.assertTrue(window.dlg.isVisible())
        delay, context, activate = scheduled.call_args.args
        self.assertEqual(delay, 0)
        self.assertIs(context, window.dlg)
        with patch.object(window.dlg, 'isActiveWindow', return_value=False), \
                patch.object(window.dlg, 'raise_') as raised, \
                patch.object(window.dlg, 'activateWindow') as activated:
            activate()
            raised.assert_called_once()
            activated.assert_called_once()

    def test_startup_activation_respects_modal_windows_and_hidden_main_window(self):
        from commonUtils.ui.pyside.windows import _activate_main_window
        window = qt.QMainWindow()
        window.show()
        with patch.object(window, 'isActiveWindow', return_value=False), \
                patch.object(window, 'activateWindow') as activate:
            with patch.object(self.app, 'activeModalWidget', return_value=qt.QDialog()):
                _activate_main_window(window)
            window.hide()
            _activate_main_window(window)
            activate.assert_not_called()
