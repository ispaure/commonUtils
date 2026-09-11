"""
UI utilities with automatic backend selection for supported generic functions.

Generic UI functions are exposed directly through this package. Native platform-specific functionality is available
through ``ui.native``, while PySide-specific functionality is lazily available through ``ui.pyside``.
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

from . import native


# ----------------------------------------------------------------------------------------------------------------------
# SETTINGS

use_pyside = True  # Use PySide for supported generic UI functions when available.


# ----------------------------------------------------------------------------------------------------------------------
# LAZY MODULE ACCESS

def __getattr__(name: str):
    """
    Lazily expose the optional PySide backend as ``ui.pyside``.
    """
    if name == 'pyside':
        module = importlib.import_module(f'{__name__}.pyside')
        globals()['pyside'] = module
        return module

    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# ----------------------------------------------------------------------------------------------------------------------
# GENERIC UI

def display_msg_box_ok(title: str, message: str) -> bool:
    if use_pyside:
        try:
            return pyside.display_msg_box_ok(title, message)
        except Exception as e:
            print(f'Could not display message using PySide: {e}')

    return native.display_msg_box_ok(title, message)


def display_msg_box_ok_cancel(title: str, message: str) -> bool:
    if use_pyside:
        try:
            return pyside.display_msg_box_ok_cancel(title, message)
        except Exception as e:
            print(f'Could not display message using PySide: {e}')

    return native.display_msg_box_ok_cancel(title, message)
