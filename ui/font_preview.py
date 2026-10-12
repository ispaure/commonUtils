"""Compatibility alias for :mod:`commonUtils.ui.settings.font_preview`."""
from importlib import import_module as _import_module
import sys as _sys

_sys.modules[__name__] = _import_module(".settings.font_preview", __package__)
