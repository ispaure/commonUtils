"""Optional desktop diagnostic presentation, explicitly installed by each host."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from ..runtime.platform.capabilities import Capability, CapabilityState, capability_status


def present_diagnostic(title, message):
    if capability_status(Capability.DESKTOP_UI).state is CapabilityState.IMPLEMENTED:
        from . import display_msg_box_ok
        display_msg_box_ok(title, message)
