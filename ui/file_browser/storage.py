"""Interactive storage treemap and largest-first listing inside the file browser."""
from .. import pyside as qt
from .discovery import ScanDialog
from ...directory_index import storage_totals
from ...filesystem import format_size
from dataclasses import dataclass


@dataclass
class StorageScan:
    snapshot: object
    totals: dict


def treemap_rectangles(items, rect):
    """Balanced binary treemap: area is proportional to logical bytes."""
    items = [(path, size) for path, size in items if size > 0]
    if not items:
        return []
    if len(items) == 1:
        return [(items[0][0], items[0][1], rect)]
    total = sum(size for _, size in items)
    running, split = 0, 1
    for index, (_, size) in enumerate(items[:-1], 1):
        running += size
        split = index
        if running >= total / 2:
            break
    ratio = running / total
    if rect.width() >= rect.height():
        width = rect.width() * ratio
        first = qt.QRectF(rect.x(), rect.y(), width, rect.height())
        second = qt.QRectF(rect.x() + width, rect.y(), rect.width() - width, rect.height())
    else:
        height = rect.height() * ratio
        first = qt.QRectF(rect.x(), rect.y(), rect.width(), height)
        second = qt.QRectF(rect.x(), rect.y() + height, rect.width(), rect.height() - height)
    return treemap_rectangles(items[:split], first) + treemap_rectangles(items[split:], second)


class Treemap(qt.QWidget):
    selected = qt.Signal(object)
    activated = qt.Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.rectangles = []
        self.setMinimumSize(250, 180)
        self.setMouseTracking(True)
        self.setAccessibleName('Storage distribution; matching entries are also available in the list')

    def set_items(self, items):
        self.items = list(items)
        self.update()

    def paintEvent(self, event):
        painter = qt.QPainter(self)
        painter.fillRect(self.rect(), self.palette().brush(qt.QPalette.ColorRole.Base))
        self.rectangles = treemap_rectangles(self.items, qt.QRectF(self.rect()))
        for index, (path, size, rect) in enumerate(self.rectangles):
            painter.fillRect(rect.adjusted(1, 1, -1, -1), qt.QColor.fromHsv((index * 47) % 360, 130, 125))
            painter.setPen(qt.QColor('white'))
            if rect.width() > 65 and rect.height() > 35:
                painter.save()
                painter.setClipRect(rect)
                painter.drawText(rect.adjusted(6, 4, -6, -4), qt.Qt.AlignmentFlag.AlignLeft |
                                 qt.Qt.AlignmentFlag.AlignTop | qt.Qt.TextFlag.TextWordWrap,
                                 f'{path.name}\n{format_size(size)}')
                painter.restore()
        if not self.rectangles:
            painter.setPen(self.palette().color(qt.QPalette.ColorRole.Text))
            painter.drawText(self.rect(), qt.Qt.AlignmentFlag.AlignCenter, 'No file bytes to display')

    def hit(self, point):
        return next(((path, size) for path, size, rect in self.rectangles if rect.contains(point)), None)

    def mouseMoveEvent(self, event):
        item = self.hit(event.position())
        self.setToolTip(f'{item[0]}\n{format_size(item[1])}' if item else '')
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        item = self.hit(event.position())
        if item and event.button() == qt.Qt.MouseButton.LeftButton:
            self.selected.emit(item[0])
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        item = self.hit(event.position())
        if item and event.button() == qt.Qt.MouseButton.LeftButton:
            self.activated.emit(item[0])
        super().mouseDoubleClickEvent(event)


class StorageDialog(ScanDialog):
    def __init__(self, browser):
        super().__init__(browser, 'Storage distribution')
        self.current = self.root
        self.selected_path = self.root
        self.totals = {}
        controls = qt.QHBoxLayout()
        self.up_button = qt.QPushButton('Up')
        self.up_button.clicked.connect(lambda: self.drill(self.current.parent))
        self.locate_button = qt.QPushButton('Show in browser')
        self.locate_button.clicked.connect(lambda: self.locate(self.selected_path))
        self.refresh_button = qt.QPushButton('Analyze / Resume')
        self.refresh_button.clicked.connect(lambda: self.scan(True))
        self.rebuild_button = qt.QPushButton('Rebuild index')
        self.rebuild_button.clicked.connect(lambda: self.scan(True, refresh=True))
        for widget in (self.up_button, self.locate_button, self.refresh_button, self.rebuild_button):
            controls.addWidget(widget)
        self.layout.insertLayout(1, controls)
        self.map = Treemap()
        self.map.selected.connect(self.select)
        self.map.activated.connect(self.drill)
        self.results = qt.QTreeWidget()
        self.results.setHeaderLabels(['File or folder (largest first)', 'Size', 'Share'])
        self.results.header().setSectionResizeMode(0, qt.QHeaderView.ResizeMode.Stretch)
        self.results.header().setSectionResizeMode(1, qt.QHeaderView.ResizeMode.ResizeToContents)
        self.results.header().setSectionResizeMode(2, qt.QHeaderView.ResizeMode.ResizeToContents)
        self.results.setRootIsDecorated(False)
        self.results.setUniformRowHeights(True)
        self.results.itemActivated.connect(lambda row, column: self.drill(row.data(0, qt.Qt.ItemDataRole.UserRole)))
        self.results.currentItemChanged.connect(lambda row, old: self.select(row.data(0, qt.Qt.ItemDataRole.UserRole)) if row else None)
        splitter = qt.QSplitter(qt.Qt.Orientation.Vertical)
        splitter.addWidget(self.map)
        splitter.addWidget(self.results)
        self.layout.insertWidget(2, splitter, 1)
        self.summary.setText('Analyze this folder, then double-click a folder to drill down. Symbolic links are excluded.')
        self.up_button.setEnabled(False)

    def show_snapshot(self):
        self.drill(self.current if self.current in self.totals else self.root)

    def collect(self, root, recursive, refresh, report, cancelled):
        snapshot = super().collect(root, recursive, refresh, report, cancelled)
        report(0, 0, 'Calculating storage totals…')
        return StorageScan(snapshot, storage_totals(snapshot, cancelled=cancelled))

    def _completed(self, result, error):
        if isinstance(result, StorageScan):
            self.totals = result.totals
            result = result.snapshot
        super()._completed(result, error)

    def drill(self, path):
        if not self.snapshot:
            return
        entry = self.snapshot.entry(path) if path != self.root else None
        if path not in self.totals or (path != self.root and not (entry and entry.directory)):
            self.select(path)
            return
        self.current = path
        self.selected_path = path
        self.location.setText(str(path))
        children = sorted(((entry.path, self.totals[entry.path]) for entry in self.snapshot.children(path)),
                          key=lambda item: (-item[1], item[0].name.casefold()))
        self.map.set_items(children)
        self.results.clear()
        total = self.totals[path]
        for child, size in children:
            row = qt.QTreeWidgetItem([child.name, format_size(size), f'{100 * size / total:.1f}%' if total else '0%'])
            row.setData(0, qt.Qt.ItemDataRole.UserRole, child)
            row.setToolTip(0, str(child))
            self.results.addTopLevelItem(row)
        self.up_button.setEnabled(path != self.root)
        self.summary.setText(f'{format_size(total)} · {len(children)} entries · '
                             f'{len(self.snapshot.errors)} unreadable entries. '
                             'Logical file sizes; links excluded. Double-click folders to drill down.')
        self.summary.setToolTip('\n'.join(f'{path}: {error}' for path, error in self.snapshot.errors))

    def select(self, path):
        self.selected_path = path
        self.summary.setText(f'{path} · {format_size(self.totals.get(path, 0))}')
