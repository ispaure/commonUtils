"""
UI utilities with automatic backend selection for supported generic functions.

Generic UI functions are exposed directly through this package. Native platform-specific functionality and
PySide-specific functionality are both lazily available through ``ui.native`` and ``ui.pyside``.

Lazy backend loading avoids importing optional dependencies unnecessarily and helps prevent circular imports between
UI backends and other commonUtils modules.
"""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

import importlib


# ----------------------------------------------------------------------------------------------------------------------
# SETTINGS

use_pyside = True  # Use PySide for supported generic UI functions when available.


# ----------------------------------------------------------------------------------------------------------------------
# LAZY MODULE ACCESS

def _get_backend(name: str):
    """
    Lazily import and return a UI backend.
    """
    module = globals().get(name)

    if module is None:
        module = importlib.import_module(f'{__name__}.{name}')
        globals()[name] = module

    return module


def __getattr__(name: str):
    """
    Lazily expose UI backends as ``ui.native`` and ``ui.pyside``.
    """
    if name in ('native', 'pyside'):
        return _get_backend(name)

    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# ----------------------------------------------------------------------------------------------------------------------
# GENERIC UI

def display_msg_box_ok(title: str, message: str) -> bool:
    if use_pyside:
        try:
            return _get_backend('pyside').display_msg_box_ok(title, message)
        except Exception as e:
            print(f'Could not display message using PySide: {e}')

    return _get_backend('native').display_msg_box_ok(title, message)


def display_msg_box_ok_cancel(title: str, message: str) -> bool:
    if use_pyside:
        try:
            return _get_backend('pyside').display_msg_box_ok_cancel(title, message)
        except Exception as e:
            print(f'Could not display message using PySide: {e}')

    return _get_backend('native').display_msg_box_ok_cancel(title, message)
