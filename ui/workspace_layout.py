"""Compatibility alias for :mod:`commonUtils.ui.workspaces.workspace_layout`."""
from importlib import import_module as _import_module
import sys as _sys

_sys.modules[__name__] = _import_module(".workspaces.workspace_layout", __package__)
