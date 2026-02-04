from pathlib import Path
from typing import *

# Common utilities
from commonUtils import fileUtils


class AppImageFile(fileUtils.File):
    def __init__(self, path: Path):
        # Call the parent (File) initializer
        super().__init__(path)
