"""Messages utilities; public API is commonUtils.ui.pyside."""

from . import _api


class MessageBox(_api.QMessageBox):
    def __init__(self):
        super().__init__()


def create_msg_box_base(title, message, icon='default', width=300, height=400,
                        b_01_str=None, b_01_fn=None,
                        b_02_str=None, b_02_fn=None,
                        b_03_str=None, b_03_fn=None):
    """
    Creates message box of various types.

    :param title: Title in the header of the message box
    :type title: str
    :param message: Message within the message box
    :type message: str
    :param icon: Icon in the message box to display
    :type icon: str
    :param width: Width of the window
    :type width: int
    :param height: Height of the window
    :type height: int
    :param b_01_str: Text to display on first button
    :type b_01_str: str
    :param b_01_fn: Function to execute on first button press
    :type b_01_fn: func
    :param b_02_str: Text to display on second button
    :type b_02_str: str
    :param b_02_fn: Function to execute on second button press
    :type b_02_fn: func
    :param b_03_str: Text to display on third button
    :type b_03_str: str
    :param b_03_fn: Function to execute on third button press
    :type b_03_fn: func
    """

    def button_pressed(info):
        def exec_fn_if_not_none(b_fn):
            if b_fn is not None:
                b_fn()

        if info.text() == b_01_str:
            exec_fn_if_not_none(b_01_fn)

        if info.text() == b_02_str:
            exec_fn_if_not_none(b_02_fn)

        if info.text() == b_03_str:
            exec_fn_if_not_none(b_03_fn)

    # Create message box
    msg_box = _api.MessageBox()
    msg_box.setWindowTitle(title)
    msg_box.setText(message)
    msg_box.setMinimumWidth(width)
    msg_box.setMinimumHeight(height)

    # Set Icon
    if icon.lower() == 'critical':
        msg_box.setIcon(_api.QMessageBox.Icon.Critical)

    elif icon.lower() == 'warning':
        msg_box.setIcon(_api.QMessageBox.Icon.Warning)

    elif icon.lower() == 'information':
        msg_box.setIcon(_api.QMessageBox.Icon.Information)

    elif icon.lower() == 'question':
        msg_box.setIcon(_api.QMessageBox.Icon.Question)

    # Connect button to functions
    msg_box.buttonClicked.connect(button_pressed)

    return msg_box


def display_msg_box_ok_cancel(title, message, fn_ok=None, fn_cancel=None, icon='information', width=300, height=400):
    """
    Displays a message box with OK and Cancel buttons.
    """
    msg_box = _api.create_msg_box_base(title, message, icon, width, height, 'OK', fn_ok, 'Cancel', fn_cancel)
    msg_box.setStandardButtons(_api.QMessageBox.StandardButton.Ok | _api.QMessageBox.StandardButton.Cancel)
    result = msg_box.exec()
    return result == _api.QMessageBox.StandardButton.Ok


def display_msg_box_ok(title, message, icon='warning', width=300, height=400):
    """
    Displays a message box with OK button.
    """
    msg_box = _api.create_msg_box_base(title, message, icon, width, height, 'OK')
    msg_box.setStandardButtons(_api.QMessageBox.StandardButton.Ok)
    msg_box.exec()
    return True


def display_msg_box_ignore_abort(title, message, fn_ignore=None, fn_abort=None, icon='warning', width=300, height=400):
    """
    Displays a message box with Ignore and Abort buttons.
    """
    msg_box = _api.create_msg_box_base(title, message, icon, width, height, 'Ignore', fn_ignore, 'Abort', fn_abort)
    msg_box.setStandardButtons(_api.QMessageBox.StandardButton.Ignore | _api.QMessageBox.StandardButton.Abort)
    msg_box.exec()
    return True


def display_msg_box_yes_no(title, message, fn_yes=None, fn_no=None, icon='question', width=300, height=400):
    """
    Displays a message box with Yes and No buttons.
    """
    msg_box = _api.create_msg_box_base(title, message, icon, width, height, '&Yes', fn_yes, '&No', fn_no)
    msg_box.setStandardButtons(_api.QMessageBox.StandardButton.Yes | _api.QMessageBox.StandardButton.No)
    result = msg_box.exec()
    return result == _api.QMessageBox.StandardButton.Yes


def display_msg_box_ok_help(title, message, fn_help=None, icon='warning', width=300, height=400):
    """
    Displays a message box with OK and Help buttons.
    """
    msg_box = _api.create_msg_box_base(title, message, icon, width, height, 'OK', None, 'Help', fn_help)
    msg_box.setStandardButtons(_api.QMessageBox.StandardButton.Ok | _api.QMessageBox.StandardButton.Help)
    msg_box.exec()
    return True

