"""Pure preferences must not probe Qt's font database before GUI startup."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from commonUtils.ui import pyside as qt
from commonUtils.ui.appearance.font_families import supported_font_family
from commonUtils.ui.appearance.styling import validate_style


class HeadlessFontSettingsTests(unittest.TestCase):
    def test_windows_metadata_checks_wait_for_gui_startup(self):
        with patch('commonUtils.ui.appearance.font_families.sys', SimpleNamespace(platform='win32')), \
                patch.object(qt.QGuiApplication, 'instance', return_value=None), \
                patch.object(qt.QFontDatabase, 'isSmoothlyScalable', side_effect=AssertionError('No GUI')), \
                patch.object(qt.QFontDatabase, 'isFixedPitch', side_effect=AssertionError('No GUI')):
            self.assertTrue(supported_font_family('Arial'))
            self.assertFalse(supported_font_family('Terminal'))
            validate_style('reading_font_family_str', 'Arial')
            validate_style('code_font_family_str', 'Courier New')
            with self.assertRaises(ValueError):
                validate_style('ui_font_family_str', 'Fixedsys')


if __name__ == '__main__':
    unittest.main()
