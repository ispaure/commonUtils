"""Compatibility package for filesystem.removal; shares its module identity."""
import sys
from ..filesystem import removal as _implementation
sys.modules[__name__] = _implementation
