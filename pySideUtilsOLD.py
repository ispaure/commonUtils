"""
Legacy PySide Utils for creating GUI (needs a few outside packages, I know they are in Maya but IDK for the others).
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

import sys
import platform

if sys.platform != 'win32' and platform.processor() == 'arm':

    # Alternative worked before fuck up
    from PySide6.QtCore import *
    from PySide6.QtGui import *
    from PySide6.QtWidgets import *

    # from PySide2.QtCore import *
    # from PySide2.QtGui import *
    # from PySide2.QtWidgets import *

    # # Alternative trying April 2024
    # from PyQt6.QtCore import *
    # from PyQt6.QtGui import *
    # from PyQt6.QtWidgets import *
else:
    from PySide2.QtCore import *
    from PySide2.QtGui import *
    from PySide2.QtWidgets import *


show_verbose = True


# ----------------------------------------------------------------------------------------------------------------------
# LABELS & BUTTONS & SCROLL AREA & GRID & PANEL
# To add to custom UI Windows


def get_scale_multiplier():
    return 1


class UiRect:
    def __init__(self, point_x, point_y, size_x, size_y):
        """
        :param point_x: Offset from origin (horizontal)
        :type point_x: Int
        :param point_y: Offset from origin (vertical)
        :type point_y: Int
        :param size_x: Size (horizontal)
        :type size_x: Int
        :param size_y: Size (vertical)
        :type size_y: Int
        """
        self.QRect = self.create_scaled_qrect(point_x, point_y, size_x, size_y)

    def create_scaled_qrect(self, point_x, point_y, size_x, size_y):
        """
        This function is used to create a PySide2.QtCore.QRect object that will scale properly in all scenarios
        :rtype: PySide2.QtCore.QRect
        """

        def point_x_scaled():
            return point_x * get_scale_multiplier()

        def point_y_scaled():
            return point_y * get_scale_multiplier()

        def size_x_scaled():
            return size_x * get_scale_multiplier()

        def size_y_scaled():
            return size_y * get_scale_multiplier()

        return QRect(point_x_scaled(), point_y_scaled(), size_x_scaled(), size_y_scaled())


class UiSize:
    def __init__(self, size_x, size_y):
        """
        :param size_x: Size (horizontal)
        :type size_x: Int
        :param size_y: Size (vertical)
        :type size_y: Int
        """
        self.QSize = self.create_scaled_qsize(size_x, size_y)

    def create_scaled_qsize(self, size_x, size_y):
        """
        This function is used to create a PySide2.QtCore.QSize object that will scale properly in all scenarios
        :rtype: PySide2.QtCore.QSize
        """

        def size_x_scaled():
            return size_x * get_scale_multiplier()

        def size_y_scaled():
            return size_y * get_scale_multiplier()

        return QSize(size_x_scaled(), size_y_scaled())


def create_label(text, ui_rect_cls, target, align_center=False, box_frame=False):
    """
    Create a label (piece of non-interactive text) that can be used within a UI.
    :param text: Text to display on label
    :type text: str
    :param ui_rect_cls: UiRect Object
    :type ui_rect_cls: UiRect
    :param target: Target UI Element to draw the label in
    :type target: PySide2.QtWidgets.QObject
    :param align_center: Whether to align the text in centre of the bounds of the UiRect Object. Default is False
    :type align_center: bool
    :param box_frame: Whether to use a box frame or not for the label. Default is False
    :type box_frame: bool
    :rtype: PySide2.QtWidgets.QLabel
    """
    label = QLabel(target)
    label.setGeometry(ui_rect_cls.QRect)
    label.setObjectName('label')
    label.setText(text)

    # Set Font and Size
    if sys.platform == 'win32':
        font_size = 10
    else:
        font_size = 13
    label.setFont(QFont('Arial', font_size))

    if align_center:
        label.setAlignment(Qt.AlignCenter)
    if box_frame:
        label.setFrameShape(QFrame.Box)
    return label


def create_button(text, ui_rect_cls, target, exec_fn=None, arg_dict=None, tooltip=None):
    """
    Create a button that can trigger a function (with arguments) when clicked
    :param text: Text to display on button
    :type text: str
    :param ui_rect_cls: UiRect Object
    :type ui_rect_cls: UiRect
    :param target: Target UI Element to draw the button in
    :type target: PySide2.QtWidgets.QObject
    :param exec_fn: Function to execute when button is pressed
    :type exec_fn: Func
    :param arg_dict: Dictionary of arguments to pass on to the function when executing it
    :type arg_dict: dict
    :param tooltip: Tooltip to display on hover of the button
    :type tooltip: str
    :rtype: PySide2.QtWidgets.QPushButton
    """
    def clicked():
        if exec_fn is not None:
            if arg_dict is not None:
                exec_fn(arg_dict)
            else:
                exec_fn()
    push_button = QPushButton(target)
    push_button.setGeometry(ui_rect_cls.QRect)
    push_button.setObjectName('button')
    push_button.setText(text)
    push_button.clicked.connect(clicked)
    if tooltip is not None:
        push_button.setToolTip(tooltip)

    # Set Font and Size
    if sys.platform == 'win32':
        font_size = 10
    else:
        font_size = 13
    push_button.setFont(QFont('Arial', font_size))

    return push_button


def create_panel(ui_rect_cls, target):
    """
    Creates a panel which can hold multiple objects to be displayed
    :param ui_rect_cls: UiRect Object
    :type ui_rect_cls: UiRect
    :param target: Target UI Element to draw the panel in
    :type target: PySide2.QtWidgets.QObject
    :rtype: PySide2.QtWidgets.QFrame
    """
    line = QFrame(target)
    line.setGeometry(ui_rect_cls.QRect)
    line.setObjectName('panel')
    line.setFrameShape(QFrame.Panel)
    line.setFrameShadow(QFrame.Plain)
    return line


def create_textedit(text, ui_rect_cls, target, pw_field=False):
    """
    Create a text box which can be filled by user.
    :param text: Text that is there by default in the field (set to '' for nothing)
    :type text: str
    :param ui_rect_cls: UiRect Object
    :type ui_rect_cls: UiRect
    :param target: Target UI Element to draw the textedit in
    :type target: PySide2.QtWidgets.QObject
    :param pw_field: If is a password field or not (put *** instead of text)
    :type pw_field: bool
    :rtype: PySide2.QtWidgets.QTextEdit
    """
    textedit = QLineEdit(target)
    textedit.setGeometry(ui_rect_cls.QRect)
    textedit.setObjectName('textedit')
    textedit.setText(text)

    # Set Font and Size
    if sys.platform == 'win32':
        font_size = 10
    else:
        font_size = 13
    textedit.setFont(QFont('Arial', font_size))

    # Set PW field
    if pw_field:
        textedit.setEchoMode(QLineEdit.Password)

    return textedit


def create_scroll_area(ui_rect_cls, ui_size_min, target):
    """
    Creates a scroll area (scroll bar appears only if not everything can be seen).
    :param ui_rect_cls: UiRect Object (Physical location and size of the scroll area on screen)
    :type ui_rect_cls: UiRect
    :param ui_size_min: UiSize Object (Size of the contents of the scroll area; Usually larger than size on screen)
    :type ui_size_min: UiSize
    :param target: Target UI Element to draw the scroll area in
    :type target: PySide2.QtWidgets.QObject
    :rtype: PySide2.QtWidgets.QWidget
    """
    scroll_area = QScrollArea(target)
    scroll_area.setGeometry(ui_rect_cls.QRect)
    scroll_area.setWidgetResizable(True)
    scroll_area.setObjectName('scroll_area')
    scroll_area_widget_contents = QWidget()
    scroll_area_widget_contents.setGeometry(ui_rect_cls.QRect)
    scroll_area_widget_contents.setMinimumSize(ui_size_min.QSize)
    scroll_area_widget_contents.setObjectName('scroll_area_widget')
    scroll_area.setWidget(scroll_area_widget_contents)
    return scroll_area_widget_contents


def create_grid(ui_rect_cls, target):
    """
    Create a grid that can later be filled.
    :param ui_rect_cls: uiRect Object
    :type ui_rect_cls: UiRect
    :param target: Target UI Element to draw the grid in
    :type target: PySide2.QtWidgets.QObject
    :rtype PySide2.QtWidgets.QGridLayout
    """
    grid_layout_widget = QWidget(target)
    grid_layout_widget.setGeometry(ui_rect_cls.QRect)
    grid_layout_widget.setObjectName('grid_layout_widget')
    grid_layout = QGridLayout(grid_layout_widget)
    grid_layout.setContentsMargins(0, 0, 0, 0)
    grid_layout.setObjectName('grid_layout')
    return grid_layout


def create_scroll_area_grid(ui_rect_cls, ui_size_cls_content, target):
    """
    Creates a scrollable area which contains a grid that can be filled later on.
    :param ui_rect_cls: UiRect Object (Physical location and size of the scroll area on screen)
    :type ui_rect_cls: UiRect
    :param ui_size_cls_content: UiSize Object (Size of the contents of the scroll area; Usually larger than size on screen)
    :type ui_size_cls_content: UiSize
    :param target: Target UI Element to draw the scroll area in
    :type target: PySide2.QtWidgets.QObject
    :return: PySide2.QtWidgets.QGridLayout
    """
    # Create scroll area widget contents
    scroll_area_widget_contents = create_scroll_area(ui_rect_cls, ui_size_cls_content, target)
    # Make size for grid
    grid_ui_rect_cls = UiRect(0, 0, 0, 0)
    grid_ui_rect_cls.QRect = QRect(0, 0, ui_size_cls_content.QSize.width(), ui_size_cls_content.QSize.height())
    # Create grid layout
    grid_layout = create_grid(grid_ui_rect_cls, scroll_area_widget_contents)
    return scroll_area_widget_contents, grid_layout
