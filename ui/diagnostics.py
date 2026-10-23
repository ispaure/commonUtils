"""Optional desktop diagnostic presentation, explicitly installed by each host."""
from ..runtime.platform.capabilities import Capability, CapabilityState, capability_status


def present_diagnostic(title, message):
    if capability_status(Capability.DESKTOP_UI).state is CapabilityState.IMPLEMENTED:
        from . import display_msg_box_ok
        display_msg_box_ok(title, message)
