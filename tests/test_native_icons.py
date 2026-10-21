"""Consumer artwork and retained controls remain independent of app policy."""
import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError
from importlib.util import find_spec
from commonUtils.ui.native.icons import IconSpec


class NativeIconTests(unittest.TestCase):
    def test_artwork_is_immutable_and_has_no_application_defaults(self):
        icon = IconSpec('square', '[]', (((1, 1), (2, 2)),))
        with self.assertRaises(FrozenInstanceError):
            icon.symbol = 'circle'
        self.assertEqual(icon.fills, ())
        self.assertFalse(icon.apple_vector)

    @unittest.skipUnless(find_spec('toga'), 'Native button test requires Toga')
    def test_renderer_preserves_callbacks_state_and_layout_without_platform_imports(self):
        code = '''
import sys
import toga
from commonUtils.ui.native.icons import IconSpec, IconRenderer
callback = lambda widget: None
button = toga.Button('Original', on_press=callback, enabled=False)
button.style.width = 93
renderer = IconRenderer({'custom': IconSpec('square', '[]')})
handler = button.on_press
renderer.apply(button, 'custom', 'Custom action', preserve_layout=True)
assert button.on_press is handler
assert not button.enabled
assert button.style.width == 93
assert button.text == '[]'
assert button.accessible_name == 'Custom action'
renderer.leading(button, [('custom', 'Meaning')])
assert button.leading_icons == (('custom', 'Meaning'),)
assert not any(name.startswith(('logisticsmobile', 'features.', 'toga_iOS', 'toga_android', 'PySide')) for name in sys.modules)
'''
        import os
        subprocess.run([sys.executable, '-c', code], env=dict(os.environ, TOGA_BACKEND='toga_dummy'), check=True)
