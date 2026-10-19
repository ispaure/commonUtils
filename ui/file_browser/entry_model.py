"""Qt projection of the portable browse tree, plus a directory-provider adapter."""
from datetime import datetime
from pathlib import Path
from .. import pyside as qt
from ...runtime.browsing import BrowseEntry, BrowseColumn, BrowseRole, BrowseTree, provider_entries
from ...filesystem import format_size, format_datetime
from .model import BrowserTree


class EntryModel(qt.QAbstractItemModel):
    children_requested = qt.Signal(object)
    snapshot_changed = qt.Signal()

    def __init__(self, root, columns=None, parent=None, *, max_entries=10000):
        super().__init__(parent)
        self.tree = BrowseTree(root, max_entries=max_entries)
        self.columns = tuple(columns or (BrowseColumn('name', 'Name'),))
        self._numbers = {root.identity: 1}
        self._identities = {1: root.identity}
        self._next_number = 2
        self.pending = set()
        self.filter_text = ''
        self.filter_parent = None

    def _number(self, identity):
        if identity not in self._numbers:
            self._numbers[identity] = self._next_number
            self._identities[self._next_number] = identity
            self._next_number += 1
        return self._numbers[identity]

    def browse_identity(self, index):
        if not index.isValid():
            return None
        identity = self._identities.get(index.internalId())
        return identity if identity in self.tree.entries else None

    def _children(self, identity):
        if getattr(self, 'flat_root', None) is not None and identity != self.flat_root:
            return ()
        if identity not in self.tree.entries:
            return ()
        children = self.tree.children.get(identity)
        if children is None:
            children = tuple(key for key, parent in self.tree.parents.items() if parent == identity)
        if self.filter_text and identity == self.filter_parent:
            children = tuple(key for key in children if self.filter_text in self.tree.entries[key].label.casefold())
        return children

    def browse_index(self, identity, column=0):
        if identity not in self.tree.entries:
            return qt.QModelIndex()
        if identity == self.tree.root:
            return self.createIndex(0, column, self._number(identity))
        parent = self.tree.parents[identity]
        children = self._children(parent)
        if identity not in children:
            return qt.QModelIndex()
        return self.createIndex(children.index(identity), column, self._number(identity))

    def browse_parent(self, identity):
        return self.tree.parents.get(identity)

    def browse_key(self, identity):
        return identity

    def browse_within(self, identity, scope):
        return self.tree.within(identity, scope)

    def browse_network(self, identity):
        return False  # Source-specific latency policy belongs to its adapter.

    def browse_root_index(self, identity):
        return self.browse_index(identity)

    def index(self, row, column, parent=qt.QModelIndex()):
        if row < 0 or column < 0 or column >= len(self.columns) or parent.column() > 0:
            return qt.QModelIndex()
        if not parent.isValid():
            return self.browse_index(self.tree.root, column) if row == 0 else qt.QModelIndex()
        children = self._children(self.browse_identity(parent))
        return self.browse_index(children[row], column) if row < len(children) else qt.QModelIndex()

    def parent(self, index):
        identity = self.browse_identity(index)
        return self.browse_index(self.browse_parent(identity)) if identity is not None else qt.QModelIndex()

    def rowCount(self, parent=qt.QModelIndex()):
        if parent.column() > 0:
            return 0
        return len(self._children(self.browse_identity(parent))) if parent.isValid() else 1

    def columnCount(self, parent=qt.QModelIndex()):
        return len(self.columns)

    def hasChildren(self, parent=qt.QModelIndex()):
        if not parent.isValid():
            return True
        identity = self.browse_identity(parent)
        return bool(identity is not None and parent.column() == 0 and self.tree.entries[identity].container)

    def canFetchMore(self, parent):
        identity = self.browse_identity(parent)
        return bool(identity is not None and self.tree.entries[identity].container
                    and identity not in self.tree.children and identity not in self.pending)

    def fetchMore(self, parent):
        identity = self.browse_identity(parent)
        if self.canFetchMore(parent):
            self.pending.add(identity)
            self.children_requested.emit(identity)

    def set_children(self, identity, entries):
        updated = self.tree.updated_children(identity, entries)
        parent = self.browse_index(identity)
        count = len(self._children(identity))
        if count:
            self.beginRemoveRows(parent, 0, count - 1)
            self.tree.children[identity] = ()
            self.endRemoveRows()
        count = len(updated.children[identity])
        if self.filter_text and identity == self.filter_parent:
            count = sum(self.filter_text in updated.entries[key].label.casefold()
                        for key in updated.children[identity])
        if count:
            self.beginInsertRows(parent, 0, count - 1)
        self.tree = updated
        self.pending.discard(identity)
        for removed in self._numbers.keys() - self.tree.entries.keys():
            self._identities.pop(self._numbers.pop(removed), None)
        self.pending.intersection_update(self.tree.entries)
        if count:
            self.endInsertRows()
        self.snapshot_changed.emit()

    def set_filter(self, text, identity):
        text = text.casefold()
        if text == self.filter_text and (not text or identity == self.filter_parent):
            self.filter_parent = identity
            return
        self.beginResetModel()
        self.filter_text, self.filter_parent = text, identity
        self.endResetModel()

    def data(self, index, role=qt.Qt.ItemDataRole.DisplayRole):
        identity = self.browse_identity(index)
        if identity is None:
            return None
        entry = self.tree.entries[identity]
        if role == BrowseRole.Identity:
            return identity
        if role == BrowseRole.Container:
            return entry.container
        if role == BrowseRole.Thumbnail:
            return entry.thumbnail
        if role == BrowseRole.Badge:
            return entry.badge
        if role == BrowseRole.Suffix:
            return entry.suffix
        if role == BrowseRole.Revision:
            return entry.revision
        if role == qt.Qt.ItemDataRole.UserRole:
            return entry.payload
        column = self.columns[index.column()]
        value = entry.label if column.key == 'name' else entry.properties.get(column.key)
        if role == BrowseRole.SortValue:
            return value
        if role == qt.Qt.ItemDataRole.DisplayRole:
            return format_size(value) if column.kind == 'bytes' and value is not None else ('' if value is None else str(value))
        if role == qt.Qt.ItemDataRole.DecorationRole and index.column() == 0:
            return qt.QApplication.style().standardIcon(qt.QStyle.StandardPixmap.SP_DirIcon if entry.container else qt.QStyle.StandardPixmap.SP_FileIcon)
        if role == qt.Qt.ItemDataRole.ToolTipRole:
            return entry.label
        return None

    def headerData(self, section, orientation, role=qt.Qt.ItemDataRole.DisplayRole):
        if orientation == qt.Qt.Orientation.Horizontal and role == qt.Qt.ItemDataRole.DisplayRole and section < len(self.columns):
            return self.columns[section].label
        return None

    def flags(self, index):
        return (qt.Qt.ItemFlag.ItemIsEnabled | qt.Qt.ItemFlag.ItemIsSelectable) if index.isValid() else qt.Qt.ItemFlag.NoItemFlags


class ProviderEntryModel(EntryModel):
    """Convert provider paths into identities without opening them on disk."""
    def __init__(self, provider, parent=None, *, thumbnail=None):
        self.provider = provider
        self.thumbnail = thumbnail
        super().__init__(BrowseEntry(provider.root, provider.root.name or str(provider.root), True),
                         (BrowseColumn('name', 'Name'), BrowseColumn('modified', 'Date Modified'),
                          BrowseColumn('size', 'Size', 'bytes')), parent)

    def data(self, index, role=qt.Qt.ItemDataRole.DisplayRole):
        value = super().data(index, role)
        if (role == qt.Qt.ItemDataRole.DisplayRole and index.isValid()
                and self.columns[index.column()].key == 'modified'):
            try:
                modified = datetime.fromisoformat(value).astimezone() if value else None
            except (ValueError, OverflowError):
                modified = None
            return format_datetime(modified)
        return value

    def ensure_directory(self, directory):
        relative = self.provider.relative(directory)
        current = self.tree.root
        for part in Path(relative).parts:
            target = current / part
            self.tree.ensure(BrowseEntry(target, part, True), current)
            current = target
        return current

    def browse_key(self, identity):
        return Path(identity)

    def entries(self, rows):
        return provider_entries(self.provider, rows, thumbnail=self.thumbnail)


class EntryRow:
    """Small compatibility facade for existing provider-picker row consumers."""
    def __init__(self, model, identity):
        self.model, self.identity = model, identity

    def data(self, column, role):
        return self.model.data(self.model.browse_index(self.identity, column), role)

    def text(self, column):
        return str(self.data(column, qt.Qt.ItemDataRole.DisplayRole) or '')


class ProviderTree(BrowserTree):
    itemSelectionChanged = qt.Signal()

    def setModel(self, model):
        super().setModel(model)
        self.selectionModel().selectionChanged.connect(self.itemSelectionChanged)

    def topLevelItemCount(self):
        return self.model().rowCount(super(BrowserTree, self).rootIndex())

    def topLevelItem(self, row):
        source = self.model().mapToSource(self.model().index(row, 0, super(BrowserTree, self).rootIndex()))
        return EntryRow(self.model().sourceModel(), source.data(BrowseRole.Identity))

    def selectedItems(self):
        return [EntryRow(self.model().sourceModel(), index.data(BrowseRole.Identity))
                for index in self.selectionModel().selectedRows()]
