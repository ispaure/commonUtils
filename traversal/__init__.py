"""Compatibility package for filesystem.traversal; shares its module identity."""
import sys
from ..filesystem import traversal as _implementation
sys.modules[__name__] = _implementation
