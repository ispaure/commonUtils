"""Compatibility alias for the canonical directory indexing package."""
import sys
from . import directory as _implementation
sys.modules[__name__] = _implementation
