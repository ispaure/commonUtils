"""Widgets utilities; public API is commonUtils.ui.pyside."""

from . import _api


def button(text: str, target: _api.QWidget, rect: _api.QRect, fn=None, args=None):
    def clicked():
        if args is None:
            _api.debugUtils.log(_api.debugUtils.Severity.DEBUG, _api.tool_name, 'Executing Button Function')
            fn()
        else:
            _api.debugUtils.log(_api.debugUtils.Severity.DEBUG, _api.tool_name, 'Executing Button Function (with Arguments)')
            fn(args)

    push_button = _api.QPushButton(target)
    push_button.setObjectName(text)
    push_button.setGeometry(rect)
    push_button.setText(text)
    _api.set_font(push_button)
    push_button.clicked.connect(clicked)
    return push_button


class Label:
    def __init__(self, text: str, target: _api.QWidget, rect: _api.QRect):
        self.label = _api.QLabel(target)
        self.label.setGeometry(rect)
        self.label.setObjectName(text)
        self.label.setText(text)
        _api.set_font(self.label)


class LineEdit:
    def __init__(self, text: str, target: _api.QWidget, rect: _api.QRect, pw_field=False):
        self.line_edit = _api.QLineEdit(target)
        self.line_edit.setGeometry(rect)
        self.line_edit.setObjectName('LineEdit')
        self.line_edit.setText(text)
        self.line_edit.setAlignment(_api.Qt.AlignmentFlag.AlignRight)
        _api.set_font(self.line_edit)

        if pw_field:
            self.line_edit.setEchoMode(_api.QLineEdit.EchoMode.Password)

    def txt(self):
        return self.line_edit.text()

    def set_txt(self, txt):
        self.line_edit.setText(str(txt))


def button_open_win(text: str, target: _api.QWidget, rect: _api.QRect, window):
    def clicked(self):
        window().display_ui()

    push_button = _api.QPushButton(target)
    push_button.setGeometry(rect)
    push_button.setText(text)
    _api.set_font(push_button)
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
    scroll_area = _api.QScrollArea(target)
    scroll_area.setGeometry(rect)
    scroll_area.setWidgetResizable(True)
    scroll_area.setObjectName('scroll_area')

    scroll_area_widget_contents = _api.QWidget()
    scroll_area_widget_contents.setGeometry(rect)
    scroll_area_widget_contents.setMinimumSize(rect_content)
    scroll_area_widget_contents.setObjectName('scroll_area_widget')
    scroll_area.setWidget(scroll_area_widget_contents)

    if _api.rog_ally:
        scroll_area.setStyleSheet("""
            QScrollBar:vertical {
                width: 30px; /* Set the desired width here */
            }
            QScrollBar:horizontal {
                height: 30px; /* Set the desired height here */
            }
        """)

    return scroll_area_widget_contents


def create_grid(target, rect: _api.QRect):
    """
    Create a grid that can later be filled.

    :param target: Target UI Element to draw the grid in
    :type target: PySide6.QtWidgets.QObject
    :param rect: QRect Object
    :type rect: QRect
    :rtype: PySide6.QtWidgets.QGridLayout
    """
    grid_layout_widget = _api.QWidget(target)
    grid_layout_widget.setGeometry(rect)
    grid_layout_widget.setObjectName('grid_layout_widget')

    grid_layout = _api.QGridLayout(grid_layout_widget)
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
    scroll_area_widget_contents = _api.create_scroll_area(target, rect, rect_content)

    # Make size for grid
    grid_ui_rect_cls = _api.QRect(0, 0, rect_content.width(), rect_content.height())

    # Create grid layout
    grid_layout = _api.create_grid(scroll_area_widget_contents, grid_ui_rect_cls)
    return scroll_area_widget_contents, grid_layout


def create_size(size_x, size_y):
    """
    This function is used to create a PySide6.QtCore.QSize object that will scale properly in all scenarios.

    :rtype: PySide6.QtCore.QSize
    """
    def size_x_scaled():
        return size_x * _api.get_scale_multiplier()

    def size_y_scaled():
        return size_y * _api.get_scale_multiplier()

    return _api.QSize(size_x_scaled(), size_y_scaled())


def create_frame(target: _api.QDialog, rect: _api.QRect):
    frame = _api.QFrame(target)
    frame.setGeometry(rect)
    frame.setObjectName('panel')
    frame.setFrameShape(_api.QFrame.Shape.Panel)
    frame.setFrameShadow(_api.QFrame.Shadow.Plain)
    return frame


def create_checkbox(target: _api.QWidget, rect: _api.QRect, default_state: bool = False):
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
    checkbox = _api.QCheckBox(target)
    checkbox.setGeometry(rect)
    checkbox.setObjectName('checkbox')

    if default_state:
        checkbox.setChecked(default_state)

    return checkbox

