"""Reveal controls preserve secrets and existing confirmation callbacks."""
import unittest
from importlib.util import find_spec
if find_spec("toga"):
    from commonUtils.ui.native.password_input import PasswordInput


@unittest.skipUnless(find_spec("toga"), "Optional Toga backend is not installed")
class PasswordInputTests(unittest.TestCase):
    def test_reveal_preserves_value_and_clear_masks_again(self):
        field = PasswordInput()
        field.value = 'secret with spaces '
        field.eye.on_press()
        self.assertTrue(field.revealed)
        self.assertEqual(field.eye.accessible_name, 'Hide password')
        self.assertEqual(field.value, 'secret with spaces ')
        field.eye.on_press()
        self.assertFalse(field.revealed)
        field.eye.on_press()
        field.value = ''
        self.assertFalse(field.revealed)
        self.assertEqual(field.eye.accessible_name, 'Show password')
        field.value = 'another secret'
        field.eye.on_press()
        field.field.value = ''  # Clearing through the input itself also masks it.
        self.assertFalse(field.revealed)

    def test_disabled_control_and_reassigned_confirmation(self):
        confirmed = []
        field = PasswordInput()
        field.on_confirm = lambda widget: confirmed.append(widget.value)
        field.value = 'secret'
        field.field.on_confirm()
        self.assertEqual(confirmed, ['secret'])
        field.enabled = False
        self.assertFalse(field.field.enabled)
        self.assertFalse(field.eye.enabled)
        field.toggle_visibility()
        self.assertFalse(field.revealed)
