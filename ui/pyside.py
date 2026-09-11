"""
PySide6 UI utilities and reusable Qt-based interface components.

This module provides the PySide-specific UI implementation for ``commonUtils.ui``, including message boxes, windows,
widgets, layouts, progress indicators, styling helpers, and other Qt-related utilities.

Generic UI operations that do not require direct access to PySide should normally be called through ``commonUtils.ui``.
Use this module directly through ``ui.pyside`` when working with Qt-specific classes or functionality.
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

from typing import *
import os
import ctypes

# Common utilities
from .. import logUtils, fileUtils, debugUtils, steamUtils
from ..osUtils import *

# PySide6 (Qt) modules
from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtWidgets import *


tool_name = 'PySide6 Wrapper'
rog_ally = False


class ProgressBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Layout for the progress bar
        layout = QVBoxLayout()

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Start Button
        self.button = QPushButton("Start Progress")
        self.button.clicked.connect(self.start_progress)
        layout.addWidget(self.button)

        # Set layout
        self.setLayout(layout)

        # Timer for updating progress
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_progress)
        self.progress_value = 0

    def start_progress(self):
        self.progress_value = 0
        self.progress_bar.setValue(self.progress_value)
        self.timer.start(100)  # Updates every 100ms

    def update_progress(self):
        if self.progress_value < 100:
            self.progress_value += 5
            self.progress_bar.setValue(self.progress_value)
        else:
            self.timer.stop()


def set_font(q_thing):
    if rog_ally:
        modifier = 6
    else:
        modifier = 0

    match get_os():
        case OS.WIN:
            font_size = 10 + modifier
        case OS.MAC:
            font_size = 13 + modifier
        case OS.LINUX:
            font_size = 10 + modifier
        case _:
            debugUtils.log(debugUtils.Severity.ERROR, 'Set Font', 'Unsupported OS!')
            return

    q_thing.setFont(QFont('Arial', font_size))


def get_scale_multiplier():
    return 1


class Palette:
    def __init__(self):
        self.palette = QPalette()

    def set_dark(self):
        self.palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
        self.palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        self.palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
        self.palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
        self.palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.black)
        self.palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
        self.palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
        self.palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        self.palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        self.palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        self.palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        self.palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        self.palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)

    def set_navy(self):
        navy_window = QColor(18, 30, 49)          # main background
        navy_button = QColor(28, 44, 68)          # buttons
        navy_base = QColor(12, 20, 36)            # input fields
        navy_alt = QColor(22, 36, 58)             # alternate rows
        navy_highlight = QColor(64, 140, 255)     # selection highlight
        navy_link = QColor(90, 170, 255)          # links

        self.palette.setColor(QPalette.ColorRole.Window, navy_window)
        self.palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)

        self.palette.setColor(QPalette.ColorRole.Base, navy_base)
        self.palette.setColor(QPalette.ColorRole.AlternateBase, navy_alt)

        self.palette.setColor(QPalette.ColorRole.ToolTipBase, navy_base)
        self.palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)

        self.palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)

        self.palette.setColor(QPalette.ColorRole.Button, navy_button)
        self.palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)

        self.palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 85, 85))

        self.palette.setColor(QPalette.ColorRole.Link, navy_link)

        self.palette.setColor(QPalette.ColorRole.Highlight, navy_highlight)
        self.palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)


def initialize_q_app():
    # Create QApplication, which is the PySide6 UI Application. One per project!
    q_app = QApplication([])
    q_app.setStyle('Fusion')

    # If on Windows, set to dark mode always with a palette (if not, it doesn't handle it properly)
    match get_os():
        case OS.WIN:
            os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '1'
            # palette_cls = Palette()
            # palette_cls.set_dark()
            # q_app.setPalette(palette_cls.palette)

        case OS.LINUX:
            if steamUtils.is_linux_steam_big_picture():
                palette_cls = Palette()
                palette_cls.set_navy()
                q_app.setPalette(palette_cls.palette)

        case _:
            pass

    return q_app


def button(text: str, target: QWidget, rect: QRect, fn=None, args=None):
    def clicked():
        if args is None:
            debugUtils.log(debugUtils.Severity.DEBUG, tool_name, 'Executing Button Function')
            fn()
        else:
            debugUtils.log(debugUtils.Severity.DEBUG, tool_name, 'Executing Button Function (with Arguments)')
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
            self.line_edit.setEchoMode(QLineEdit.EchoMode.Password)

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
        #     self.layout.addWidget(QLabel("Hello, world!", alignment=Qt.AlignmentFlag.AlignCenter))
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
            # For QDialog, use exec()
            self.dlg.exec()

        elif isinstance(self.dlg, QMainWindow):
            # For QMainWindow, use show() and ensure app.exec() is called
            self.dlg.show()

            if self.maximized:
                self.dlg.showMaximized()

        else:
            logUtils.exit_msg('Wrong type for Window.dlg')


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
    :type target: PySide6.QtWidgets.QObject
    :param rect: QRect Object
    :type rect: QRect
    :param rect_content: QSize Object
    :type rect_content: QSize
    :rtype: PySide6.QtWidgets.QWidget
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
    :type target: PySide6.QtWidgets.QObject
    :param rect: QRect Object
    :type rect: QRect
    :rtype: PySide6.QtWidgets.QGridLayout
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

    :param rect: QRect Object
    :type rect: QRect
    :param rect_content: QSize Object
    :type rect_content: QSize
    :param target: Target UI Element to draw the scroll area in
    :type target: PySide6.QtWidgets.QObject
    :return: PySide6.QtWidgets.QGridLayout
    """
    # Create scroll area widget contents
    scroll_area_widget_contents = create_scroll_area(target, rect, rect_content)

    # Make size for grid
    grid_ui_rect_cls = QRect(0, 0, rect_content.width(), rect_content.height())

    # Create grid layout
    grid_layout = create_grid(scroll_area_widget_contents, grid_ui_rect_cls)
    return scroll_area_widget_contents, grid_layout


def create_size(size_x, size_y):
    """
    This function is used to create a PySide6.QtCore.QSize object that will scale properly in all scenarios.

    :rtype: PySide6.QtCore.QSize
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
    frame.setFrameShape(QFrame.Shape.Panel)
    frame.setFrameShadow(QFrame.Shadow.Plain)
    return frame


def create_checkbox(target: QWidget, rect: QRect, default_state: bool = False):
    """
    Create a checkbox which can be ticked or not by user.

    :param rect: QRect Object
    :type rect: QRect
    :param target: Target UI Element to draw the checkbox in
    :type target: PySide6.QtWidgets.QObject
    :param default_state: Default state for the checkbox. Default is unchecked.
    :type default_state: bool
    :rtype: PySide6.QtWidgets.QCheckBox
    """
    checkbox = QCheckBox(target)
    checkbox.setGeometry(rect)
    checkbox.setObjectName('checkbox')

    if default_state:
        checkbox.setChecked(default_state)

    return checkbox


class MessageBox(QMessageBox):
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
    msg_box = MessageBox()
    msg_box.setWindowTitle(title)
    msg_box.setText(message)
    msg_box.setMinimumWidth(width)
    msg_box.setMinimumHeight(height)

    # Set Icon
    if icon.lower() == 'critical':
        msg_box.setIcon(QMessageBox.Icon.Critical)

    elif icon.lower() == 'warning':
        msg_box.setIcon(QMessageBox.Icon.Warning)

    elif icon.lower() == 'information':
        msg_box.setIcon(QMessageBox.Icon.Information)

    elif icon.lower() == 'question':
        msg_box.setIcon(QMessageBox.Icon.Question)

    # Connect button to functions
    msg_box.buttonClicked.connect(button_pressed)

    return msg_box


# ----------------------------------------------------------------------------------------------------------------------
# PRESETS

"""This section below includes presets which are based on the create_msg_box_base function."""


def display_msg_box_ok_cancel(title, message, fn_ok=None, fn_cancel=None, icon='information', width=300, height=400):
    """
    Displays a message box with OK and Cancel buttons.
    """
    msg_box = create_msg_box_base(title, message, icon, width, height, 'OK', fn_ok, 'Cancel', fn_cancel)
    msg_box.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
    result = msg_box.exec()
    return result == QMessageBox.StandardButton.Ok


def display_msg_box_ok(title, message, icon='warning', width=300, height=400):
    """
    Displays a message box with OK button.
    """
    msg_box = create_msg_box_base(title, message, icon, width, height, 'OK')
    msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg_box.exec()
    return True


def display_msg_box_ignore_abort(title, message, fn_ignore=None, fn_abort=None, icon='warning', width=300, height=400):
    """
    Displays a message box with Ignore and Abort buttons.
    """
    msg_box = create_msg_box_base(title, message, icon, width, height, 'Ignore', fn_ignore, 'Abort', fn_abort)
    msg_box.setStandardButtons(QMessageBox.StandardButton.Ignore | QMessageBox.StandardButton.Abort)
    msg_box.exec()
    return True


def display_msg_box_yes_no(title, message, fn_yes=None, fn_no=None, icon='question', width=300, height=400):
    """
    Displays a message box with Yes and No buttons.
    """
    msg_box = create_msg_box_base(title, message, icon, width, height, '&Yes', fn_yes, '&No', fn_no)
    msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    result = msg_box.exec()
    return result == QMessageBox.StandardButton.Yes


def display_msg_box_ok_help(title, message, fn_help=None, icon='warning', width=300, height=400):
    """
    Displays a message box with OK and Help buttons.
    """
    msg_box = create_msg_box_base(title, message, icon, width, height, 'OK', None, 'Help', fn_help)
    msg_box.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Help)
    msg_box.exec()
    return True


# ----------------------------------------------------------------------------------------------------------------------
# PROGRESS BAR WINDOW

class ProgressBarWindow(Window):
    def __init__(self, title: str):
        super().__init__(title, main_window=False)

        # Set dimensions
        self.width = 300
        self.height = 50
        self.dlg.resize(int(self.width), int(self.height))
        self.dlg.setWindowTitle(title)
        self.dlg.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)

        # Create layout
        layout = QVBoxLayout()

        # Create progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Attach layout to dialog
        self.dlg.setLayout(layout)

    def update_progress(self, value):
        """Update the progress bar."""
        self.progress_bar.setValue(value)
        QApplication.processEvents()


def display_progress_bar(title: str):
    progress_window = ProgressBarWindow(title)
    progress_window.dlg.show()
    return progress_window


def hide_console_window():
    """Hide the console window on Windows."""
    match get_os():
        case OS.WIN:
            ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

        case _:
            debugUtils.log(debugUtils.Severity.WARNING, 'Main', 'Could not hide console window!')
