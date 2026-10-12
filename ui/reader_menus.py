"""Compatibility alias for :mod:`commonUtils.ui.readers.reader_menus`."""
from importlib import import_module as _import_module
import sys as _sys

_sys.modules[__name__] = _import_module(".readers.reader_menus", __package__)
