"""Application utilities; public API is commonUtils.ui.pyside."""

from . import _api


def set_font(q_thing):
    if _api.rog_ally:
        modifier = 6
    else:
        modifier = 0

    match _api.get_os():
        case _api.OS.WIN:
            font_size = 10 + modifier
        case _api.OS.MAC:
            font_size = 13 + modifier
        case _api.OS.LINUX:
            font_size = 10 + modifier
        case _:
            _api.debugUtils.log(_api.debugUtils.Severity.ERROR, 'Set Font', 'Unsupported OS!')
            return

    q_thing.setFont(_api.QFont('Arial', font_size))


def get_scale_multiplier():
    return 1


class Palette:
    def __init__(self):
        self.palette = _api.QPalette()

    def set_dark(self):
        self.palette.setColor(_api.QPalette.ColorRole.Window, _api.QColor(53, 53, 53))
        self.palette.setColor(_api.QPalette.ColorRole.WindowText, _api.Qt.GlobalColor.white)
        self.palette.setColor(_api.QPalette.ColorRole.Base, _api.QColor(25, 25, 25))
        self.palette.setColor(_api.QPalette.ColorRole.AlternateBase, _api.QColor(53, 53, 53))
        self.palette.setColor(_api.QPalette.ColorRole.ToolTipBase, _api.Qt.GlobalColor.black)
        self.palette.setColor(_api.QPalette.ColorRole.ToolTipText, _api.Qt.GlobalColor.white)
        self.palette.setColor(_api.QPalette.ColorRole.Text, _api.Qt.GlobalColor.white)
        self.palette.setColor(_api.QPalette.ColorRole.Button, _api.QColor(53, 53, 53))
        self.palette.setColor(_api.QPalette.ColorRole.ButtonText, _api.Qt.GlobalColor.white)
        self.palette.setColor(_api.QPalette.ColorRole.BrightText, _api.Qt.GlobalColor.red)
        self.palette.setColor(_api.QPalette.ColorRole.Link, _api.QColor(42, 130, 218))
        self.palette.setColor(_api.QPalette.ColorRole.Highlight, _api.QColor(42, 130, 218))
        self.palette.setColor(_api.QPalette.ColorRole.HighlightedText, _api.Qt.GlobalColor.black)

    def set_navy(self):
        navy_window = _api.QColor(18, 30, 49)          # main background
        navy_button = _api.QColor(28, 44, 68)          # buttons
        navy_base = _api.QColor(12, 20, 36)            # input fields
        navy_alt = _api.QColor(22, 36, 58)             # alternate rows
        navy_highlight = _api.QColor(64, 140, 255)     # selection highlight
        navy_link = _api.QColor(90, 170, 255)          # links

        self.palette.setColor(_api.QPalette.ColorRole.Window, navy_window)
        self.palette.setColor(_api.QPalette.ColorRole.WindowText, _api.Qt.GlobalColor.white)

        self.palette.setColor(_api.QPalette.ColorRole.Base, navy_base)
        self.palette.setColor(_api.QPalette.ColorRole.AlternateBase, navy_alt)

        self.palette.setColor(_api.QPalette.ColorRole.ToolTipBase, navy_base)
        self.palette.setColor(_api.QPalette.ColorRole.ToolTipText, _api.Qt.GlobalColor.white)

        self.palette.setColor(_api.QPalette.ColorRole.Text, _api.Qt.GlobalColor.white)

        self.palette.setColor(_api.QPalette.ColorRole.Button, navy_button)
        self.palette.setColor(_api.QPalette.ColorRole.ButtonText, _api.Qt.GlobalColor.white)

        self.palette.setColor(_api.QPalette.ColorRole.BrightText, _api.QColor(255, 85, 85))

        self.palette.setColor(_api.QPalette.ColorRole.Link, navy_link)

        self.palette.setColor(_api.QPalette.ColorRole.Highlight, navy_highlight)
        self.palette.setColor(_api.QPalette.ColorRole.HighlightedText, _api.Qt.GlobalColor.black)


def initialize_q_app():
    # Create QApplication, which is the PySide6 UI Application. One per project!
    q_app = _api.QApplication([])
    q_app.setStyle('Fusion')

    # If on Windows, set to dark mode always with a palette (if not, it doesn't handle it properly)
    match _api.get_os():
        case _api.OS.WIN:
            _api.os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '1'
            # palette_cls = Palette()
            # palette_cls.set_dark()
            # q_app.setPalette(palette_cls.palette)

        case _api.OS.LINUX:
            if _api.steamUtils.is_linux_steam_big_picture():
                palette_cls = _api.Palette()
                palette_cls.set_navy()
                q_app.setPalette(palette_cls.palette)

        case _:
            pass

    return q_app


def hide_console_window():
    """Hide the console window on Windows."""
    match _api.get_os():
        case _api.OS.WIN:
            _api.ctypes.windll.user32.ShowWindow(_api.ctypes.windll.kernel32.GetConsoleWindow(), 0)

        case _:
            _api.debugUtils.log(_api.debugUtils.Severity.WARNING, 'Main', 'Could not hide console window!')

