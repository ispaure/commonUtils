"""Compatibility package for filesystem.transfers; shares its module identity."""
import sys
from ..filesystem import transfers as _implementation
sys.modules[__name__] = _implementation
