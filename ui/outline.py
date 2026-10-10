"""Navigation-only outlines with opaque targets, independent of filesystem actions."""
from dataclasses import dataclass
from . import pyside as qt


@dataclass(frozen=True)
class OutlineEntry:
    id: object
    label: str
    target: object
    depth: int = 0


class OutlineList(qt.QListWidget):
    def set_entries(self, entries):
        self.clear()
        self.entries = tuple(entries)
        self.items_by_id = {}
        for entry in self.entries:
            item = qt.QListWidgetItem('    ' * max(0, entry.depth) + entry.label)
            item.setToolTip(entry.label)
            item.setData(qt.Qt.ItemDataRole.UserRole, entry.target)
            self.addItem(item)
            self.items_by_id[entry.id] = item


class OutlineTree(qt.QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.items_by_id = {}

    def set_entries(self, entries):
        self.clear()
        self.items_by_id = {}
        parents = []
        for entry in entries:
            item = qt.QTreeWidgetItem([entry.label])
            item.setToolTip(0, entry.label)
            item.setData(0, qt.Qt.ItemDataRole.UserRole, entry.target)
            depth = min(max(0, entry.depth), len(parents))
            if depth:
                parents[depth - 1].addChild(item)
            else:
                self.addTopLevelItem(item)
            parents[depth:] = [item]
            self.items_by_id[entry.id] = item
        self.expandAll()
