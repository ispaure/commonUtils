"""Compatibility alias for :mod:`commonUtils.ui.appearance.theme`."""
from importlib import import_module as _import_module
import sys as _sys

_sys.modules[__name__] = _import_module(".appearance.theme", __package__)
