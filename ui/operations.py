"""Compatibility alias for :mod:`commonUtils.ui.tasks.operations`."""
from importlib import import_module as _import_module
import sys as _sys

_sys.modules[__name__] = _import_module(".tasks.operations", __package__)
