"""Compatibility alias for :mod:`commonUtils.ui.tasks.process_progress`."""
from importlib import import_module as _import_module
import sys as _sys

_sys.modules[__name__] = _import_module(".tasks.process_progress", __package__)
