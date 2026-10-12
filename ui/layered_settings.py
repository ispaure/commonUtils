"""Compatibility alias for :mod:`commonUtils.ui.settings.layered_settings`."""
from importlib import import_module as _import_module
import sys as _sys

_sys.modules[__name__] = _import_module(".settings.layered_settings", __package__)
