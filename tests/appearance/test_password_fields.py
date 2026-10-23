"""Qt reveal controls preserve values and reset visibility on clear."""
from commonUtils.ui import pyside as qt
from commonUtils.tests.qt_test_case import QtTestCase


class PasswordFieldTests(QtTestCase):
    def test_password_eye_preserves_value_selection_and_masks_after_clear(self):
        from commonUtils.ui.pyside.passwords import password_field
        field = password_field(qt.QLineEdit())
        self.addCleanup(field.deleteLater)
        field.setText('synthetic secret')
        field.setSelection(2, 5)
        field.visibility_action.trigger()
        self.assertEqual(field.echoMode(), qt.QLineEdit.EchoMode.Normal)
        self.assertEqual(field.text(), 'synthetic secret')
        self.assertEqual(field.selectedText(), 'nthet')
        self.assertEqual(field.visibility_action.text(), 'Hide password')
        field.visibility_action.trigger()
        self.assertEqual(field.echoMode(), qt.QLineEdit.EchoMode.Password)
        field.visibility_action.trigger()
        field.clear()
        self.assertFalse(field.visibility_action.isChecked())
        self.assertEqual(field.echoMode(), qt.QLineEdit.EchoMode.Password)
        self.assertEqual(field.visibility_action.text(), 'Show password')
        self.assertIs(password_field(field), field)
        self.assertEqual(len(field.actions()), 1)

    def test_existing_password_wrapper_uses_reveal_control(self):
        from commonUtils.ui.pyside.widgets import LineEdit
        owner = qt.QWidget()
        self.addCleanup(owner.deleteLater)
        wrapper = LineEdit('synthetic secret', owner, qt.QRect(0, 0, 240, 48), pw_field=True)
        wrapper.line_edit.visibility_action.trigger()
        self.assertEqual(wrapper.line_edit.echoMode(), qt.QLineEdit.EchoMode.Normal)
        self.assertEqual(wrapper.txt(), 'synthetic secret')
