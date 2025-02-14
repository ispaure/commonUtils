from pathlib import Path

# Common utilities
from commonUtils import fileUtils
from commonUtils.osUtils import *


def get_marc_dropbox_root():
    op_sys = get_os()
    match op_sys:
        case OS.WIN:
            return Path(fileUtils.get_user_home_dir(), 'Yagi Dropbox', 'Marc-Andre Voyer')
        case OS.MAC:
            return Path(fileUtils.get_user_home_dir(), 'Yagi Dropbox', 'Marc-Andre Voyer')
        case _:
            return None
