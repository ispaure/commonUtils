import sys
import os
import platform
from commonUtils.debugUtils import *
from commonUtils import debugUtils
from commonUtils import fileUtils

# if sys.platform != 'win32' and platform.processor() == 'arm':
from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtWidgets import *


tool_name = 'pySide6 Wrapper'
rog_ally = False


def set_font(q_thing):

    if rog_ally:
        modifier = 6
    else:
        modifier = 0

    if fileUtils.get_os() == 'Windows':
        font_size = 10 + modifier
    elif fileUtils.get_os() == 'macOS':
        font_size = 13 + modifier
    q_thing.setFont(QFont('Arial', font_size))


def get_scale_multiplier():
    return 1


class Palette:
    def __init__(self):
        self.palette = QPalette()

    def set_dark(self):
        self.palette.setColor(QPalette.Window, QColor(53, 53, 53))
        self.palette.setColor(QPalette.WindowText, Qt.white)
        self.palette.setColor(QPalette.Base, QColor(25, 25, 25))
        self.palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
        self.palette.setColor(QPalette.ToolTipBase, Qt.black)
        self.palette.setColor(QPalette.ToolTipText, Qt.white)
        self.palette.setColor(QPalette.Text, Qt.white)
        self.palette.setColor(QPalette.Button, QColor(53, 53, 53))
        self.palette.setColor(QPalette.ButtonText, Qt.white)
        self.palette.setColor(QPalette.BrightText, Qt.red)
        self.palette.setColor(QPalette.Link, QColor(42, 130, 218))
        self.palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        self.palette.setColor(QPalette.HighlightedText, Qt.black)


def button(text: str, target: QWidget, rect: QRect, fn=None, args=None):
    def clicked():
        if args is None:
            log(Severity.DEBUG, tool_name, 'Executing Button Function')
            fn()
        else:
            log(Severity.DEBUG, tool_name, 'Executing Button Function (with Arguments)')
            fn(args)

    push_button = QPushButton(target)
    push_button.setObjectName(text)
    push_button.setGeometry(rect)
    push_button.setText(text)
    set_font(push_button)
    push_button.clicked.connect(clicked)
    return push_button


class Label:
    def __init__(self, text: str, target: QWidget, rect: QRect):
        self.label = QLabel(target)
        self.label.setGeometry(rect)
        self.label.setObjectName(text)
        self.label.setText(text)
        set_font(self.label)


class LineEdit:
    def __init__(self, text: str, target: QWidget, rect: QRect, pw_field=False):
        self.line_edit = QLineEdit(target)
        self.line_edit.setGeometry(rect)
        self.line_edit.setObjectName('LineEdit')
        self.line_edit.setText(text)
        self.line_edit.setAlignment(Qt.AlignmentFlag.AlignRight)
        set_font(self.line_edit)

        if pw_field:
            self.line_edit.setEchoMode(QLineEdit.Password)

    def txt(self):
        return self.line_edit.text()

    def set_txt(self, txt):
        self.line_edit.setText(str(txt))


class Window:
    def __init__(self, name: str, main_window=False, maximized=False):
        self.name = name
        self.width = 720
        self.height = 500
        self.dlg = None
        self.maximized = maximized
        # self.layout = None
        self.create_ui(main_window)
        self.setup_ui()

    def create_ui(self, main_window):
        if not main_window:
            dialog_cls = QDialog()
        else:
            dialog_cls = QMainWindow()
        self.dlg = dialog_cls

    def setup_ui(self):
        self.dlg.setObjectName(self.name)
        self.dlg.resize(self.width, self.height)

        # if isinstance(self.dlg, QMainWindow):
        #     # Add layout to manage positioning (optional for base Window)
        #     central_widget = QWidget()
        #     self.layout = QVBoxLayout(central_widget)
        #     self.layout.addWidget(QLabel("Hello, world!", alignment=Qt.AlignCenter))
        #     self.dlg.setCentralWidget(central_widget)

    def re_translate_ui(self):
        _translate = QCoreApplication.translate
        self.dlg.resize(self.width, self.height)
        self.dlg.setWindowTitle(_translate(self.name, self.name))

    def display_ui(self):
        self.re_translate_ui()
        QMetaObject.connectSlotsByName(self.dlg)

        # Do right thing, depending on type
        if isinstance(self.dlg, QDialog):
            # For QDialog, use exec_()
            self.dlg.exec_()
        elif isinstance(self.dlg, QMainWindow):
            # For QMainWindow, use show() and ensure app.exec() is called
            self.dlg.show()
            if self.maximized:
                self.dlg.showMaximized()
        else:
            debugUtils.exit_msg('Wrong type for Window.dlg')


def button_open_win(text: str, target: QWidget, rect: QRect, window):
    def clicked(self):
        window().display_ui()

    push_button = QPushButton(target)
    push_button.setGeometry(rect)
    push_button.setText(text)
    set_font(push_button)
    push_button.clicked.connect(clicked)
    return push_button


def create_scroll_area(target, rect, rect_content):
    """
    Creates a scroll area (scroll bar appears only if not everything can be seen).
    :param target: Target UI Element to draw the scroll area in
    :type target: PySide2.QtWidgets.QObject
    :param rect: UiRect Object (Physical location and size of the scroll area on screen)
    :type rect: UiRect
    :param rect_content: UiSize Object (Size of the contents of the scroll area; Usually larger than size on screen)
    :type rect_content: UiSize
    :rtype: PySide2.QtWidgets.QWidget
    """
    scroll_area = QScrollArea(target)
    scroll_area.setGeometry(rect)
    scroll_area.setWidgetResizable(True)
    scroll_area.setObjectName('scroll_area')
    scroll_area_widget_contents = QWidget()
    scroll_area_widget_contents.setGeometry(rect)
    scroll_area_widget_contents.setMinimumSize(rect_content)
    scroll_area_widget_contents.setObjectName('scroll_area_widget')
    scroll_area.setWidget(scroll_area_widget_contents)

    if rog_ally:
        scroll_area.setStyleSheet("""
            QScrollBar:vertical {
                width: 30px; /* Set the desired width here */
            }
            QScrollBar:horizontal {
                height: 30px; /* Set the desired height here */
            }
        """)

    return scroll_area_widget_contents


def create_grid(target, rect: QRect):
    """
    Create a grid that can later be filled.
    :param target: Target UI Element to draw the grid in
    :type target: PySide2.QtWidgets.QObject
    :param rect: QRect Object
    :type rect: QRect
    :rtype PySide2.QtWidgets.QGridLayout
    """
    grid_layout_widget = QWidget(target)
    grid_layout_widget.setGeometry(rect)
    grid_layout_widget.setObjectName('grid_layout_widget')
    grid_layout = QGridLayout(grid_layout_widget)
    grid_layout.setContentsMargins(0, 0, 0, 0)
    grid_layout.setObjectName('grid_layout')
    return grid_layout


def create_scroll_area_grid(target, rect, rect_content):
    """
    Creates a scrollable area which contains a grid that can be filled later on.
    :param rect: UiRect Object (Physical location and size of the scroll area on screen)
    :type rect: UiRect
    :param rect_content: UiSize Object (Size of the contents of the scroll area; Usually larger than size on screen)
    :type rect_content: UiSize
    :param target: Target UI Element to draw the scroll area in
    :type target: PySide2.QtWidgets.QObject
    :return: PySide2.QtWidgets.QGridLayout
    """
    # Create scroll area widget contents
    scroll_area_widget_contents = create_scroll_area(target, rect, rect_content)
    # Make size for grid
    grid_ui_rect_cls = QRect(0, 0, 0, 0)
    grid_ui_rect_cls = QRect(0, 0, rect_content.width(), rect_content.height())
    # Create grid layout
    grid_layout = create_grid(scroll_area_widget_contents, grid_ui_rect_cls)
    return scroll_area_widget_contents, grid_layout


def create_size(size_x, size_y):
    """
    This function is used to create a PySide2.QtCore.QSize object that will scale properly in all scenarios
    :rtype: PySide2.QtCore.QSize
    """
    def size_x_scaled():
        return size_x * get_scale_multiplier()

    def size_y_scaled():
        return size_y * get_scale_multiplier()

    return QSize(size_x_scaled(), size_y_scaled())


def create_frame(target: QDialog, rect: QRect):
    frame = QFrame(target)
    frame.setGeometry(rect)
    frame.setObjectName('panel')
    frame.setFrameShape(QFrame.Panel)
    frame.setFrameShadow(QFrame.Plain)
    return frame


def create_checkbox(target: QWidget, rect: QRect, default_state: bool = False):
    """
    Create a checkbox which can be ticked or not by user.
    :param rect: UiRect Object
    :type rect: UiRect
    :param target: Target UI Element to draw the checkbox in
    :type target: PySide2.QtWidgets.QObject
    :rtype: PySide2.QtWidgets.QCheckBox
    :param default_state: Default state for the checkbox. Default is unchecked.
    :type default_state: bool
    :rtype: PySide2.QtWidgets.QCheckBox
    """
    checkbox = QCheckBox(target)
    checkbox.setGeometry(rect)
    checkbox.setObjectName('checkbox')
    if default_state:
        checkbox.setChecked(default_state)

    return checkbox


class MessageBox(QMessageBox):
    def __init__(self):
        super(MessageBox, self).__init__()


def create_msg_box_base(title, message, icon='default', width=300, height=400,
                        b_01_str=None, b_01_fn=None,
                        b_02_str=None, b_02_fn=None,
                        b_03_str=None, b_03_fn=None):
    """
    Creates message box of various types
    :param title: Title in the header of the message box
    :type title: str
    :param message: Message within the message box
    :type message: str
    :param icon: Icon in the message box to display (dependent of severity of message)
    :type icon: str, from a few predefined options (see API doc.)
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
        # Execute button pressed function.
        def exec_fn_if_not_none(b_fn):
            # If function isn't None, execute
            if b_fn is not None:
                b_fn()

        # Find out which button was pressed and run its fn (if not set to None)
        if info.text() == b_01_str:
            exec_fn_if_not_none(b_01_fn)
        if info.text() == b_02_str:
            exec_fn_if_not_none(b_02_fn)
        if info.text() == b_03_str:
            exec_fn_if_not_none(b_03_fn)

    # Create message box
    msg_box = MessageBox()
    msg_box.setWindowTitle(title)
    msg_box.setText(message)
    msg_box.setMinimumWidth(width)
    msg_box.setMinimumHeight(height)

    # Set Icon
    if icon.lower() == 'critical':
        msg_box.setIcon(msg_box.Icon.Critical)
    elif icon.lower() == 'warning':
        msg_box.setIcon(msg_box.Icon.Warning)
    elif icon.lower() == 'information':
        msg_box.setIcon(msg_box.Icon.Information)
    elif icon.lower() == 'question':
        msg_box.setIcon(msg_box.Icon.Question)

    # Connect button to functions
    msg_box.buttonClicked.connect(button_pressed)

    # Return created message box
    return msg_box


# ----------------------------------------------------------------------------------------------------------------------
# PRESETS

"""This section below includes presets which are based on the create_msg_box_base function."""


def display_msg_box_ok_cancel(title, message, fn_ok=None, fn_cancel=None, icon='information', width=300, height=400):
    """
    Displays a message box with OK and Cancel buttons.
    """
    msg_box = create_msg_box_base(title, message, icon, width, height, 'OK', fn_ok, 'Cancel', fn_cancel)
    msg_box.setStandardButtons(msg_box.StandardButton.Ok | msg_box.StandardButton.Cancel)
    msg_box.exec_()
    return True


def display_msg_box_ok(title, message, icon='warning', width=300, height=400):
    """
    Displays a message box with OK button.
    """
    msg_box = create_msg_box_base(title, message, icon, width, height, 'OK')
    msg_box.setStandardButtons(msg_box.StandardButton.Ok)
    msg_box.exec_()
    return True


def display_msg_box_ignore_abort(title, message, fn_ignore=None, fn_abort=None, icon='warning', width=300, height=400):
    """
    Displays a message box with Ignore and Abort buttons.
    """
    msg_box = create_msg_box_base(title, message, icon, width, height, 'Ignore', fn_ignore, 'Abort', fn_abort)
    msg_box.setStandardButtons(msg_box.Ignore | msg_box.Abort)
    msg_box.exec_()
    return True


def display_msg_box_yes_no(title, message, fn_yes=None, fn_no=None, icon='question', width=300, height=400):
    """
    Displays a message box with Yes and No buttons.
    """
    msg_box = create_msg_box_base(title, message, icon, width, height, '&Yes', fn_yes, '&No', fn_no)
    msg_box.setStandardButtons(msg_box.Yes | msg_box.No)
    msg_box.exec_()
    return True


def display_msg_box_ok_help(title, message, fn_help=None, icon='warning', width=300, height=400):
    """
    Displays a message box with Ok and Help buttons.
    """
    msg_box = create_msg_box_base(title, message, icon, width, height, 'Ok', None, 'Help', fn_help)
    msg_box.setStandardButtons(msg_box.Ok | msg_box.Help)
    msg_box.exec_()
    return True
