"""Compatibility alias for :mod:`commonUtils.ui.readers.reader_chrome`."""
from importlib import import_module as _import_module
import sys as _sys

_sys.modules[__name__] = _import_module(".readers.reader_chrome", __package__)
