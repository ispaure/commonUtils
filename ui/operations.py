"""Background callbacks for Qt owners, without file-browser dependencies."""

from . import pyside as qt
from ..debugUtils import noninteractive_logging


class Operation(qt.QThread):
    completed = qt.Signal(object, str)

    def __init__(self, callback, parent):
        super().__init__(parent)
        self.callback = callback

    def run(self):
        try:
            with noninteractive_logging():
                result = self.callback()
            self.completed.emit(result, '')
        except Exception as error:
            self.completed.emit(None, str(error))

