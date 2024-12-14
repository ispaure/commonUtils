import sys
import os
import platform
from commonUtils import logUtils

# if sys.platform != 'win32' and platform.processor() == 'arm':
from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtWidgets import *


def set_font(q_thing):
    if sys.platform == 'win32':
        font_size = 10
    else:
        font_size = 13
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


def create_button(text: str, target: QWidget, rect: QRect, fn=None, args=None):
    def clicked():
        if args is None:
            logUtils.log_msg('Executing Button Function')
            fn()
        else:
            logUtils.log_msg('Executing Button Function (with Arguments)')
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
    def __init__(self, name: str):
        self.name = name
        self.width = 720
        self.height = 500
        self.dlg = None
        self.create_ui()

    def create_ui(self):
        dialog_cls = QDialog()
        self.dlg = dialog_cls
        self.setup_ui()

    def setup_ui(self):
        self.dlg.setObjectName(self.name)
        self.dlg.resize(self.width, self.height)

    def re_translate_ui(self):
        _translate = QCoreApplication.translate
        self.dlg.resize(self.width, self.height)
        self.dlg.setWindowTitle(_translate(self.name, self.name))

    def display_ui(self):
        self.re_translate_ui()
        QMetaObject.connectSlotsByName(self.dlg)
        self.dlg.exec_()


class ButtonOpenWindow:
    def __init__(self, text: str, target: QWidget, rect: QRect, window):
        self.push_button = QPushButton(target)
        self.push_button.setGeometry(rect)
        self.push_button.setText(text)
        set_font(self.push_button)
        self.window = window
        self.push_button.clicked.connect(self.clicked)

    def clicked(self):
        self.window().display_ui()


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
