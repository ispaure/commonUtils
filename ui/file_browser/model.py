"""Qt filesystem watching with File/Directory objects as the public data model."""

from collections import OrderedDict
from pathlib import Path
from .. import pyside as qt
from ...dirUtils import Directory
from ...fileTypes.registry import file_types, object_from_path
from ...filesystem import format_size
from ...file_operations import validate_name


class BrowserFileSystemModel(qt.QFileSystemModel):
    edit_failed = qt.Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.folder_totals = {}
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
                    stats = self.folder_totals.get(item.path)
                    if item.path.is_symlink():
                        return '—'
                    return format_size(stats.size) if stats is not None else '…'
                return format_size(item.size) if item.size is not None else '—'
            if index.column() == 3 and item.modified_time is not None:
                return item.modified_time.strftime('%Y-%m-%d %H:%M')
        if index.isValid() and index.column() == 1 and role == qt.Qt.ItemDataRole.ToolTipRole:
            if isinstance(self.item(index), Directory):
                return 'Recursive file size; symbolic links are excluded.'
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
        previous = self.folder_totals
        self.folder_totals = totals or {}
        for path in previous.keys() | self.folder_totals.keys():
            index = self.index(str(path), 1)
            if index.isValid():
                self.dataChanged.emit(index, index, [qt.Qt.ItemDataRole.DisplayRole])

    def invalidate(self, path):
        self._items.pop(Path(path), None)
