"""Compatibility package for archives.zip_access; shares its module identity."""
import sys
from ..archives import zip_access as _implementation
sys.modules[__name__] = _implementation
