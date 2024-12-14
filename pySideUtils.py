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


class Button:
    def __init__(self, text: str, target: QWidget, rect: QRect, fn=None, args=None):
        self.push_button = None
        self.__init_push_button(text, target, rect, fn, args)

    def __init_push_button(self, text: str, target: QWidget, rect: QRect, fn=None, args=None):

        def clicked(self):
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

        self.push_button = push_button


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
