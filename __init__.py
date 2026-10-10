"""Utilities shared by Logistics and Blue Hole, organized by responsibility."""
from ._compat import install as _install, legacy_attribute as _legacy_attribute

_install(__name__)


def __getattr__(name):
    value = _legacy_attribute(__name__, name)
    globals()[name] = value
    return value
