"""Compatibility alias for :mod:`commonUtils.ui.settings.ini_editor`."""
from importlib import import_module as _import_module
import sys as _sys

_sys.modules[__name__] = _import_module(".settings.ini_editor", __package__)
