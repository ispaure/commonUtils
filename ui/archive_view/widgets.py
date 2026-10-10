"""Archive view items and aspect-preserving image display."""
from .. import pyside as qt
from ...filesystem import format_size


def size_text(size):
    return '—' if size is None else format_size(size, binary_units=True)


class ImagePreview(qt.QLabel):
    def __init__(self):
        super().__init__()
        self.original = None
        self.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(qt.QSizePolicy.Policy.Ignored, qt.QSizePolicy.Policy.Ignored)

    def set_preview(self, pixmap):
        self.original = pixmap
        self._scale()

    def _scale(self):
        if self.original is not None:
            self.setPixmap(self.original.scaled(self.size(), qt.Qt.AspectRatioMode.KeepAspectRatio,
                                               qt.Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._scale()

    def clear(self):
        self.original = None
        super().clear()


class ArchiveItem(qt.QTreeWidgetItem):
    def __lt__(self, other):
        column = self.treeWidget().sortColumn()
        left = self.data(0, qt.Qt.ItemDataRole.UserRole)
        right = other.data(0, qt.Qt.ItemDataRole.UserRole)
        if left and right and left[1] != right[1]:
            return left[1]
        if column in (1, 2, 3):
            role = int(qt.Qt.ItemDataRole.UserRole) + 1
            return (self.data(column, role) or 0) < (other.data(column, role) or 0)
        return self.text(column).casefold() < other.text(column).casefold()


