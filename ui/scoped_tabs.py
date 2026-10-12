"""Compatibility alias for :mod:`commonUtils.ui.workspaces.scoped_tabs`."""
from importlib import import_module as _import_module
import sys as _sys

_sys.modules[__name__] = _import_module(".workspaces.scoped_tabs", __package__)
