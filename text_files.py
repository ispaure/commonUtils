"""Compatibility alias for persistence.text."""
import sys
from .persistence import text as _implementation
sys.modules[__name__] = _implementation
