"""Desktop reveal commands and their platform fallback."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

from pathlib import Path
import unittest
from unittest.mock import patch


class DesktopActionTests(unittest.TestCase):
    def test_platform_reveal_commands_and_linux_fallback(self):
        from commonUtils.runtime.platform import OS
        from commonUtils.ui import desktop_actions
        path = Path('/tmp/test name.cbz').absolute()
        with patch.object(desktop_actions, 'get_os', return_value=OS.MAC), patch.object(desktop_actions.subprocess, 'run') as run:
            desktop_actions.reveal(path)
            run.assert_called_once_with(['open', '-R', str(path)], check=True)
        with patch.object(desktop_actions, 'get_os', return_value=OS.WIN), patch.object(desktop_actions.subprocess, 'Popen') as start:
            desktop_actions.reveal(path)
            self.assertEqual(start.call_args.args[0][0], 'explorer')
        with patch.object(desktop_actions, 'get_os', return_value=OS.LINUX), patch.object(desktop_actions.subprocess, 'run', side_effect=FileNotFoundError), patch.object(desktop_actions, 'open_default') as opened:
            desktop_actions.reveal(path)
            opened.assert_called_once_with(path.parent)
