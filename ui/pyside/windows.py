"""Windows utilities; public API is commonUtils.ui.pyside."""

from . import _api


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
            dialog_cls = _api.QDialog()
        else:
            dialog_cls = _api.QMainWindow()

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
        _translate = _api.QCoreApplication.translate
        self.dlg.resize(self.width, self.height)
        self.dlg.setWindowTitle(_translate(self.name, self.name))

    def display_ui(self):
        self.re_translate_ui()
        _api.QMetaObject.connectSlotsByName(self.dlg)

        # Do right thing, depending on type
        if isinstance(self.dlg, _api.QDialog):
            # For QDialog, use exec()
            self.dlg.exec()

        elif isinstance(self.dlg, _api.QMainWindow):
            # For QMainWindow, use show() and ensure app.exec() is called
            self.dlg.show()

            if self.maximized:
                self.dlg.showMaximized()

        else:
            _api.logUtils.exit_msg('Wrong type for Window.dlg')

