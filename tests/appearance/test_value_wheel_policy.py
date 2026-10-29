"""Wheel gestures scroll forms without dirtying their value controls."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path

from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtWidgets import QSpinBox

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.pyside.wheel_policy import install_value_wheel_policy
from commonUtils.ui.settings.ini_editor import INISettingsEditor
from commonUtils.ui.settings.layered_settings import LayeredSettingsEditor
from commonUtils.configuration.layered import LayeredSettings


class ValueWheelTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.policy = install_value_wheel_policy(self.app)
        self.addCleanup(self.remove_policy)

    def remove_policy(self):
        self.app.removeEventFilter(self.policy)
        del self.app._commonutils_value_wheel_policy
        self.policy.deleteLater()

    def wheel(self, widget, *, pixel=False):
        local = qt.QPointF(widget.rect().center())
        event = qt.QWheelEvent(
            local, qt.QPointF(widget.mapToGlobal(local.toPoint())),
            qt.QPoint(0, -40) if pixel else qt.QPoint(),
            qt.QPoint() if pixel else qt.QPoint(0, -120),
            qt.Qt.MouseButton.NoButton, qt.Qt.KeyboardModifier.NoModifier,
            qt.Qt.ScrollPhase.ScrollUpdate if pixel else qt.Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        self.app.sendEvent(widget, event)
        self.app.processEvents()

    def form(self, widget):
        scroll = qt.QScrollArea()
        scroll.setWidgetResizable(True)
        body = qt.QWidget()
        layout = qt.QVBoxLayout(body)
        layout.addWidget(widget)
        layout.addSpacing(1800)
        scroll.setWidget(body)
        scroll.resize(400, 240)
        scroll.show()
        self.app.processEvents()
        return scroll

    def test_all_value_types_ignore_wheel_even_when_focused(self):
        for factory, getter in (
            (QSpinBox, lambda w: w.value()),
            (qt.QDoubleSpinBox, lambda w: w.value()),
            (qt.QDateEdit, lambda w: w.date()),
            (qt.QTimeEdit, lambda w: w.time()),
            (qt.QDateTimeEdit, lambda w: w.dateTime()),
            (qt.QComboBox, lambda w: w.currentIndex()),
            (qt.QFontComboBox, lambda w: w.currentIndex()),
            (qt.QSlider, lambda w: w.value()),
            (qt.QDial, lambda w: w.value()),
        ):
            with self.subTest(control=factory.__name__):
                widget = factory()
                if isinstance(widget, qt.QComboBox) and not widget.count():
                    widget.addItems(['one', 'two', 'three'])
                    widget.setCurrentIndex(1)
                elif isinstance(widget, (qt.QSpinBox, qt.QDoubleSpinBox, qt.QAbstractSlider)):
                    widget.setValue(50)
                scroll = self.form(widget)
                before = getter(widget)
                for focused in (False, True):
                    widget.setFocus() if focused else widget.clearFocus()
                    for pixel in (False, True):
                        self.wheel(widget, pixel=pixel)
                        self.assertEqual(getter(widget), before)
                scroll.deleteLater()
                self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)

    def test_wheel_over_control_and_embedded_editor_scrolls_parent(self):
        for factory in (qt.QSpinBox, qt.QDoubleSpinBox, qt.QComboBox):
            with self.subTest(control=factory.__name__):
                widget = factory()
                if isinstance(widget, qt.QComboBox):
                    widget.addItems(['one', 'two', 'three'])
                    widget.setEditable(True)
                    signal = widget.currentIndexChanged
                else:
                    widget.setValue(50)
                    signal = widget.valueChanged
                scroll = self.form(widget)
                spy = QSignalSpy(signal)
                widget.setFocus()
                for target in (widget, widget.lineEdit()):
                    for pixel in (False, True):
                        scroll.verticalScrollBar().setValue(0)
                        self.wheel(target, pixel=pixel)
                        self.assertGreater(scroll.verticalScrollBar().value(), 0)
                self.assertEqual(spy.count(), 0)
                # Deliberate keyboard and text edits still work.
                QTest.keyClick(widget, qt.Qt.Key.Key_Down)
                self.assertGreater(spy.count(), 0)
                if isinstance(widget, qt.QAbstractSpinBox):
                    widget.lineEdit().selectAll()
                    QTest.keyClicks(widget.lineEdit(), '23')
                    QTest.keyClick(widget.lineEdit(), qt.Qt.Key.Key_Return)
                    self.assertEqual(widget.value(), 23)
                    options = qt.QStyleOptionSpinBox()
                    widget.initStyleOption(options)
                    button = widget.style().subControlRect(
                        qt.QStyle.ComplexControl.CC_SpinBox, options,
                        qt.QStyle.SubControl.SC_SpinBoxUp, widget)
                    QTest.mouseClick(widget, qt.Qt.MouseButton.LeftButton, pos=button.center())
                    self.assertEqual(widget.value(), 24)
                scroll.deleteLater()
                self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)

    def test_open_dropdown_and_scrollbar_still_scroll(self):
        combo = qt.QComboBox()
        combo.setStyleSheet('QComboBox { combobox-popup: 0; }')
        combo.setMaxVisibleItems(8)
        combo.addItems([str(n) for n in range(100)])
        scroll = self.form(combo)
        self.wheel(scroll.verticalScrollBar())
        self.assertGreater(scroll.verticalScrollBar().value(), 0)
        scroll.verticalScrollBar().setValue(0)
        combo.showPopup()
        self.app.processEvents()
        bar = combo.view().verticalScrollBar()
        bar.setValue(0)
        self.wheel(combo.view().viewport())
        self.assertGreater(combo.view().verticalScrollBar().value(), 0)
        combo.hidePopup()

    def test_settings_editors_install_policy_and_remain_clean(self):
        self.remove_policy()
        with self.temporary_directory() as directory:
            path = Path(directory) / 'settings.ini'
            path.write_text('[Options]\nsize_int = 12\nchoice_mode = one\nchoice_choices_list-str = ["one", "two"]\n')
            original = path.read_bytes()
            ini = INISettingsEditor(path, typed_keys=True)
            self.policy = install_value_wheel_policy(self.app)
            self.assertIs(self.policy, install_value_wheel_policy(self.app))
            self.wheel(ini.fields['Options', 'choice_mode'])
            self.assertFalse(ini.text.document().isModified())
            self.remove_policy()
            store = LayeredSettings(path, Path(directory) / 'personal.ini')
            layered = LayeredSettingsEditor(store)
            self.policy = install_value_wheel_policy(self.app)
            self.wheel(layered.fields['Options', 'size_int'])
            self.wheel(layered.fields['Options', 'choice_mode'])
            self.assertEqual(layered.pending, {})
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse((Path(directory) / 'personal.ini').exists())
