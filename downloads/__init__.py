"""Compatibility package for streams.downloads; shares its module identity."""
import sys
from ..streams import downloads as _implementation
sys.modules[__name__] = _implementation
