"""Progress utilities; public API is commonUtils.ui.pyside."""

from . import _api


class ProgressBar(_api.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Layout for the progress bar
        layout = _api.QVBoxLayout()

        # Progress Bar
        self.progress_bar = _api.QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Start Button
        self.button = _api.QPushButton("Start Progress")
        self.button.clicked.connect(self.start_progress)
        layout.addWidget(self.button)

        # Set layout
        self.setLayout(layout)

        # Timer for updating progress
        self.timer = _api.QTimer()
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


class ProgressBarWindow(_api.Window):
    def __init__(self, title: str):
        super().__init__(title, main_window=False)

        # Set dimensions
        self.width = 300
        self.height = 50
        self.dlg.resize(int(self.width), int(self.height))
        self.dlg.setWindowTitle(title)
        self.dlg.setWindowFlags(_api.Qt.WindowType.Window | _api.Qt.WindowType.CustomizeWindowHint | _api.Qt.WindowType.WindowTitleHint)

        # Create layout
        layout = _api.QVBoxLayout()

        # Create progress bar
        self.progress_bar = _api.QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Attach layout to dialog
        self.dlg.setLayout(layout)

    def update_progress(self, value):
        """Update the progress bar."""
        self.progress_bar.setValue(value)
        _api.QApplication.processEvents()


def display_progress_bar(title: str):
    progress_window = _api.ProgressBarWindow(title)
    progress_window.dlg.show()
    return progress_window

