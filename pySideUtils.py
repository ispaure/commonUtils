"""Historical import path for the shared PySide utilities."""
import sys
from .ui import pyside
sys.modules[__name__] = pyside
