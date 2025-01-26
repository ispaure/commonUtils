from pathlib import Path
from commonUtils import fileUtils


def get_marc_dropbox_root():
    op_sys = fileUtils.get_os()
    match op_sys:
        case 'Windows':
            return Path(fileUtils.get_user_home_dir(), 'Yagi Dropbox', 'Marc-Andre Voyer')
        case 'macOS':
            return Path(fileUtils.get_user_home_dir(), 'Yagi Dropbox', 'Marc-Andre Voyer')
        case _:
            return None
