"""Qt filesystem watching with File/Directory objects as the public data model."""

from collections import OrderedDict
from pathlib import Path
from .. import pyside as qt
from ...dirUtils import Directory
from ...fileTypes.registry import file_types, object_from_path
from ...filesystem import format_size, format_datetime
from ...file_operations import validate_name


class BrowserFileSystemModel(qt.QFileSystemModel):
    edit_failed = qt.Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.folder_totals = {}
        self.network_location = False
        self.size_parents = set()
        self._items = OrderedDict()

    def item(self, index):
        return self.object_for_path(self.filePath(index))

    def object_for_path(self, path):
        path = Path(path)
        try:
            stat = path.stat()
            fingerprint = (stat.st_mtime_ns, stat.st_size, file_types.revision)
        except OSError:
            fingerprint = (None, None, file_types.revision)
        cached = self._items.get(path)
        if cached is None or cached[0] != fingerprint:
            cached = (fingerprint, object_from_path(path))
            self._items[path] = cached
        self._items.move_to_end(path)
        while len(self._items) > 512:
            self._items.popitem(last=False)
        return cached[1]

    def data(self, index, role=qt.Qt.ItemDataRole.DisplayRole):
        if index.isValid() and role == qt.Qt.ItemDataRole.DisplayRole:
            item = self.item(index)
            if index.column() == 0:
                return item.name if isinstance(item, Directory) else item.file_name
            if index.column() == 1:
                if isinstance(item, Directory):
                    if self.network_location: return '—'
                    stats = self.folder_totals.get(item.path)
                    if item.path.is_symlink():
                        return '—'
                    return (('≥ ' if not stats.complete else '') + format_size(stats.size)) if stats is not None else '…'
                return format_size(item.size) if item.size is not None else '—'
            if index.column() == 3 and item.modified_time is not None:
                return format_datetime(item.modified_time)
        if index.isValid() and index.column() == 1 and role == qt.Qt.ItemDataRole.ToolTipRole:
            if isinstance(self.item(index), Directory):
                if self.network_location: return 'Folder sizes disabled for network drives'
                stats = self.folder_totals.get(Path(self.filePath(index)))
                state = ('Incomplete / calculating' if not stats.complete else 'Cached; checking for changes'
                         if stats.stale else 'Up to date') if stats is not None else 'Calculating'
                return f'{state}. Recursive logical file size; symbolic links are excluded.'
        return super().data(index, role)

    def setData(self, index, value, role=qt.Qt.ItemDataRole.EditRole):
        if role != qt.Qt.ItemDataRole.EditRole or index.column() != 0:
            return super().setData(index, value, role)
        try:
            if self.isReadOnly():
                return False
            validate_name(value)
            source = Path(self.filePath(index))
            target = source.with_name(value)
            if source == target:
                return True
            # Directory entries distinguish a real collision from a case-only rename
            # on a case-insensitive volume. Qt's rename also refuses racing collisions.
            if (target.exists() or target.is_symlink()) and value in {entry.name for entry in source.parent.iterdir()}:
                raise FileExistsError(f'A file or folder named "{value}" already exists.')
            if not super().setData(index, value, role):
                raise OSError('Could not rename this item. Check its name and write permissions.')
            return True
        except Exception as error:
            self.edit_failed.emit(str(error))
            return False

    def set_folder_totals(self, totals):
        if self.folder_totals == (totals or {}):
            return
        self.folder_totals = totals or {}
        # Updating every indexed path would make QFileSystemModel load distant
        # folders on the GUI thread. Only invalidate currently displayed parents.
        for path in self.size_parents or {self.rootPath()}:
            parent = self.index(str(path))
            rows = self.rowCount(parent)
            if parent.isValid() and rows:
                self.dataChanged.emit(self.index(0, 1, parent), self.index(rows - 1, 1, parent),
                                      [qt.Qt.ItemDataRole.DisplayRole, qt.Qt.ItemDataRole.ToolTipRole])

    def invalidate(self, path):
        self._items.pop(Path(path), None)


class ByteSortModel(qt.QSortFilterProxyModel):
    """The list sorts displayed byte totals without changing other view models."""
    def __init__(self, filesystem, parent=None):
        super().__init__(parent)
        self.filesystem = filesystem
        self.setSourceModel(filesystem)
        self.setDynamicSortFilter(True)

    def mapFromSource(self, index):
        if index.isValid() and index.model() is self.filesystem:
            # QFileSystemModel indexes can retain a file pointer with an old row
            # while asynchronous loading reorders siblings. Refresh by path before
            # passing the row-based index to the sorting proxy.
            index = self.filesystem.index(self.filesystem.filePath(index), index.column())
        return super().mapFromSource(index)

    def _bytes(self, index):
        path = Path(self.filesystem.filePath(index))
        if self.filesystem.isDir(index):
            stats = self.filesystem.folder_totals.get(path)
            return stats.size if stats is not None and not path.is_symlink() else None
        return self.filesystem.size(index)

    def lessThan(self, left, right):
        if left.column() == 1:
            a, b = self._bytes(left), self._bytes(right)
            if (a is None) != (b is None):
                return (a is not None) if self.sortOrder() == qt.Qt.SortOrder.AscendingOrder else (a is None)
            if a != b:
                return a < b
        elif left.column() == 3:
            a, b = self.filesystem.lastModified(left), self.filesystem.lastModified(right)
            if a != b:
                return a < b
        else:
            a, b = self.filesystem.isDir(left), self.filesystem.isDir(right)
            if a != b:
                return a
        # QCollator's C-locale backend ignores numeric mode on headless Linux.
        from ...traversal import natural_path_key
        return natural_path_key(self.filesystem.fileName(left)) < natural_path_key(self.filesystem.fileName(right))


class _BrowserSelection(qt.QItemSelectionModel):
    """Accept filesystem indexes from existing browser integrations."""
    def setCurrentIndex(self, index, command):
        if index.model() is self.model().sourceModel():
            index = self.model().mapFromSource(index)
        super().setCurrentIndex(index, command)

    def select(self, selection, command):
        if isinstance(selection, qt.QModelIndex) and selection.model() is self.model().sourceModel():
            selection = self.model().mapFromSource(selection)
        elif isinstance(selection, qt.QItemSelection) and selection and selection[0].model() is self.model().sourceModel():
            selection = self.model().mapSelectionFromSource(selection)
        super().select(selection, command)


class BrowserTree(qt.QTreeView):
    def source_to_view(self, index):
        return self.model().mapFromSource(index) if index.model() is self.model().sourceModel() else index

    def setRootIndex(self, index):
        super().setRootIndex(self.source_to_view(index))

    def rootIndex(self):
        return self.model().mapToSource(super().rootIndex())

    def expand(self, index):
        super().expand(self.source_to_view(index))

    def collapse(self, index):
        super().collapse(self.source_to_view(index))

    def setCurrentIndex(self, index):
        super().setCurrentIndex(self.source_to_view(index))

    def scrollTo(self, index, hint=qt.QAbstractItemView.ScrollHint.EnsureVisible):
        super().scrollTo(self.source_to_view(index), hint)

    def visualRect(self, index):
        return super().visualRect(self.source_to_view(index))

    def edit(self, index, *args):
        return super().edit(self.source_to_view(index), *args)
