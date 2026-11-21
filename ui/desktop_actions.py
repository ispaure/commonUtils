"""Open and reveal local items through the platform's file applications."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from ..runtime.platform.capabilities import Capability, require_capability

from pathlib import Path
import subprocess
from urllib.parse import quote
from ..runtime.platform import OS, get_os
from . import pyside as qt


def open_default(path):
    require_capability(Capability.EXTERNAL_APPLICATIONS, 'open_default')
    if not qt.QDesktopServices.openUrl(qt.QUrl.fromLocalFile(str(Path(path).absolute()))):
        raise RuntimeError('Could not open the default application')


def reveal_label():
    return {OS.MAC: 'Reveal in Finder', OS.WIN: 'Reveal in Explorer'}.get(get_os(), 'Reveal in Linux File Explorer')


def reveal(path):
    require_capability(Capability.EXTERNAL_APPLICATIONS, 'reveal')
    path = Path(path).absolute()
    platform = get_os()
    if platform == OS.MAC:
        subprocess.run(['open', '-R', str(path)], check=True)
    elif platform == OS.WIN:
        subprocess.Popen(['explorer', '/select,', str(path)])
    else:
        # Desktop file managers implementing the standard interface select the file.
        try:
            result = subprocess.run(['dbus-send', '--session', '--dest=org.freedesktop.FileManager1',
                                 '--type=method_call', '--print-reply', '/org/freedesktop/FileManager1',
                                 'org.freedesktop.FileManager1.ShowItems',
                                 'array:string:' + quote(path.as_uri(), safe=':/%'), 'string:'], capture_output=True, check=False, timeout=5)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            result = None
        if result is None or result.returncode:
            open_default(path if path.is_dir() else path.parent)
