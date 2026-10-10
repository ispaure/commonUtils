"""Compatibility package for filesystem.network; shares its module identity."""
import sys
from ..filesystem import network as _implementation
sys.modules[__name__] = _implementation
