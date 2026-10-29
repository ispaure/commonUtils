"""Form presentation preserves source text and retained field values."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('TOGA_BACKEND', 'toga_dummy')
import unittest
from importlib.util import find_spec
HAS_TOGA = find_spec('toga') is not None
if HAS_TOGA:
    import toga
    from commonUtils.ui.native.forms import wrap_text, fit_text, FittedLabel, collapsible


@unittest.skipUnless(HAS_TOGA, 'Native form tests require Toga')
class NativeFormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = toga.App('Forms', 'org.example.forms')

    def test_wrap_preserves_paragraphs_and_splits_long_identifiers(self):
        self.assertEqual(wrap_text('one two\n\nabcdefghij', 4, len), 'one\ntwo\n\nabcd\nefgh\nij')

    def test_refit_recovers_original_text_and_updates_async_messages(self):
        label = FittedLabel('A long status message')
        fit_text(label, 40)
        self.assertIn('\n', label.text)
        fit_text(label, 1000)
        self.assertEqual(label.text, 'A long status message')
        fit_text(label, 40)
        label.text = 'Replacement status'
        self.assertEqual(label._settings_source_text, 'Replacement status')
        fit_text(label, 1000)
        self.assertEqual(label.text, 'Replacement status')

    def test_collapsed_field_keeps_identity_value_and_notifies_after_layout(self):
        field = toga.TextInput(value='Unsaved value')
        mounted = []
        box, button = collapsible('Advanced', [field], changed=lambda box: mounted.append(len(box.children)))
        button.on_press()
        body = box.children[1]
        self.assertIs(body.children[0], field)
        field.value = 'Changed value'
        button.on_press()
        self.assertIsNone(body.parent)
        button.on_press()
        self.assertIs(box.children[1], body)
        self.assertEqual(field.value, 'Changed value')
        self.assertEqual(mounted, [2, 1, 2])
