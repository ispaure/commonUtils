from pathlib import Path

# Common utilities
from commonUtils import fileUtils
from commonUtils.osUtils import *


def get_marc_dropbox_root() -> Path:
    return Path(fileUtils.get_user_home_dir(), 'Yagi Dropbox', 'Marc-Andre Voyer')
