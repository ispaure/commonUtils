from typing import *
from pathlib import Path

# Common utilities
from commonUtils import fileUtils
from commonUtils.debugUtils import *


class XMLFile(fileUtils.TXTFile):
    def __init__(self, path: Path):
        super().__init__(path)
