"""Compatibility alias for persistence.session."""
import sys
from .persistence import session as _implementation
sys.modules[__name__] = _implementation
