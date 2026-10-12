"""Compatibility alias for :mod:`commonUtils.ui.settings.settings_sections`."""
from importlib import import_module as _import_module
import sys as _sys

_sys.modules[__name__] = _import_module(".settings.settings_sections", __package__)
