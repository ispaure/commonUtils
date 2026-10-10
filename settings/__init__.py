"""Compatibility package for configuration.settings; shares its module identity."""
import sys
from ..configuration import settings as _implementation
sys.modules[__name__] = _implementation
