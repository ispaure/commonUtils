"""Backward-compatible Qt facade, organized into focused implementation modules.

Qt, typing and OS exports remain available for existing consumers. Mutable settings
and calls between components resolve through this facade to preserve customization.
"""
from ._imports import *
from ._imports import (__author__, __copyright__, __license__, __maintainer__, __email__, __status__)
import sys as _sys

_api = _sys.modules[__name__]
tool_name = 'PySide6 Wrapper'
rog_ally = False

from .application import set_font, get_scale_multiplier, Palette, initialize_q_app, hide_console_window
from .windows import Window
from .widgets import button, Label, LineEdit, button_open_win, create_scroll_area, create_grid, create_scroll_area_grid, create_size, create_frame, create_checkbox
from .messages import MessageBox, create_msg_box_base, display_msg_box_ok_cancel, display_msg_box_ok, display_msg_box_ignore_abort, display_msg_box_yes_no, display_msg_box_ok_help
from .progress import ProgressBar, ProgressBarWindow, display_progress_bar

# Keep historical class/function identities for introspection and pickling.
for _name in ['Label', 'LineEdit', 'MessageBox', 'Palette', 'ProgressBar', 'ProgressBarWindow', 'Window', 'button', 'button_open_win', 'create_checkbox', 'create_frame', 'create_grid', 'create_msg_box_base', 'create_scroll_area', 'create_scroll_area_grid', 'create_size', 'display_msg_box_ignore_abort', 'display_msg_box_ok', 'display_msg_box_ok_cancel', 'display_msg_box_ok_help', 'display_msg_box_yes_no', 'display_progress_bar', 'get_scale_multiplier', 'hide_console_window', 'initialize_q_app', 'set_font']:
    globals()[_name].__module__ = __name__
