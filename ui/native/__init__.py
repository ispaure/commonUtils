"""Optional native adapters and lazy desktop dialogs; imports load no toolkit."""


def display_msg_box_ok(title: str, message: str) -> bool:
    from .dialogs import display_msg_box_ok as display
    return display(title, message)


def display_msg_box_ok_cancel(title: str, message: str) -> bool:
    from .dialogs import display_msg_box_ok_cancel as display
    return display(title, message)
