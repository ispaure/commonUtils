from pathlib import Path
import os
# Common utilities
from commonUtils import fileUtils
from commonUtils.osUtils import *


def get_marc_dropbox_root() -> Path:
    if get_os() == OS.WIN:
        if os.path.isdir('B:\\Yagi Dropbox'):
            return Path('B:\\Yagi Dropbox\\Marc-Andre Voyer')
    return Path(fileUtils.get_user_home_dir(), 'Yagi Dropbox', 'Marc-Andre Voyer')
