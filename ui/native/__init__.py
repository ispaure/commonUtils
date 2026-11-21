"""Optional native adapters and lazy desktop dialogs; imports load no toolkit."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------


def display_msg_box_ok(title: str, message: str) -> bool:
    from .dialogs import display_msg_box_ok as display
    return display(title, message)


def display_msg_box_ok_cancel(title: str, message: str) -> bool:
    from .dialogs import display_msg_box_ok_cancel as display
    return display(title, message)
