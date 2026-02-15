""" Allows to choose method for displaying UI (for supported functions) """

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

from . import sysUI

use_pyside = True  # Uses pyside for UI, Else make dialog popup using os terminal


def display_msg_box_ok(title: str, message: str) -> bool:
    if use_pyside:
        try:
            from . import pySideUtils  # local import breaks the cycle, so only do here when needed
            return pySideUtils.display_msg_box_ok(title, message)
        except Exception:
            print('Could not load pySideUtils / display message!')
    else:
        return sysUI.display_msg_box_ok(title, message)


def display_msg_box_ok_cancel(title: str, message: str) -> bool:
    if use_pyside:
        try:
            from . import pySideUtils  # local import breaks the cycle, so only do here when needed
            return pySideUtils.display_msg_box_ok_cancel(title, message)
        except Exception:
            print('Could not load pySideUtils / display message!')
    else:
        return sysUI.display_msg_box_ok_cancel(title, message)
