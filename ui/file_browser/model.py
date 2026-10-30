"""Qt filesystem watching with File/Directory objects as the public data model."""

from collections import OrderedDict
from pathlib import Path
import stat
import sys
from .. import pyside as qt
from ...filesystem.directories import Directory
from ...formats.registry import file_types, object_from_path
from ...filesystem import format_size, format_datetime
from ...filesystem.transfers import validate_name
from ...runtime.browsing import BrowseRole


def hidden_path(path, *, info=None):
    """Recognize dot names and native hidden metadata for a local entry."""
    path = Path(path)
    if path.name.startswith('.'):
        return True
    info = info if info is not None else qt.QFileInfo(str(path))
    if info.isHidden():
        return True
    if sys.platform == 'darwin':
        try:
            return bool(path.lstat().st_flags & stat.UF_HIDDEN)
        except OSError:
            pass
    return False


def hidden_brush():
    return qt.QApplication.palette().brush(qt.QPalette.ColorRole.PlaceholderText)


class BrowserFileSystemModel(qt.QFileSystemModel):
    def multiData(self, index, roles):
        # Qt 6.12 delegates request roles in batches. Native implementations
        # bypass Python data() overrides, including our names and folder sizes.
        for position in range(roles.size()):
            role = roles[position]
            role.setData(self.data(index, role.role()))

    edit_failed = qt.Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.directory_boundary = None
        self.folder_totals = {}
        self.network_location = False
        self.size_parents = set()
        self._items = OrderedDict()
        self._item_checks = {}
        self._item_check_timer = qt.QTimer(self)
        self._item_check_timer.setSingleShot(True)
        self._item_check_timer.timeout.connect(self._item_checks.clear)

    def _managed_directory(self, index):
        return bool(index.isValid() and getattr(self, 'directory_boundary', None)
                    and self.directory_boundary(Path(self.filePath(index))))

    def rowCount(self, parent=qt.QModelIndex()):
        return 0 if self._managed_directory(parent) else super().rowCount(parent)

    def canFetchMore(self, parent):
        return False if self._managed_directory(parent) else super().canFetchMore(parent)

    def fetchMore(self, parent):
        if not self._managed_directory(parent):
            super().fetchMore(parent)

    def item(self, index):
        # Sort/paint can request thousands of roles within one GUI event. Check
        # each path once per turn, retaining stat precision and immediate direct
        # path lookups instead of relying on QFileSystemModel's stale fileInfo.
        path = Path(self.filePath(index))
        cached = self._items.get(path)
        if cached is not None and self._item_checks.get(path) == file_types.revision:
            self._items.move_to_end(path)
            return cached[1]
        result = self.object_for_path(path)
        self._item_checks[path] = file_types.revision
        if not self._item_check_timer.isActive():
            self._item_check_timer.start(0)
        return result

    def object_for_path(self, path):
        path = Path(path)
        try:
            stat = path.stat()
            fingerprint = (stat.st_mtime_ns, stat.st_size, file_types.revision)
        except OSError:
            fingerprint = (None, None, file_types.revision)
        return self._cached_object(path, fingerprint)

    def _cached_object(self, path, fingerprint):
        cached = self._items.get(path)
        if cached is None or cached[0] != fingerprint:
            cached = (fingerprint, object_from_path(path))
            self._items[path] = cached
        self._items.move_to_end(path)
        while len(self._items) > 512:
            self._items.popitem(last=False)
        return cached[1]

    def browse_identity(self, index):
        return Path(self.filePath(index)) if index.isValid() else None

    def browse_key(self, identity):
        return Path(identity)

    def browse_index(self, identity):
        return self.index(str(identity)) if identity is not None else qt.QModelIndex()

    def browse_parent(self, identity):
        return Path(identity).parent

    def browse_within(self, identity, scope):
        return identity == scope or scope in Path(identity).parents

    def browse_network(self, identity):
        from ...filesystem.network import is_network_location
        return is_network_location(identity)

    def browse_root_index(self, identity):
        hidden_root = getattr(self, '_browse_hidden_root', None)
        if hidden_root is not None and not self.browse_within(identity, hidden_root):
            self.setFilter(self._browse_hidden_filter)
            self._browse_hidden_root = None
        index = self.browse_index(identity)
        if not index.isValid():
            if getattr(self, '_browse_hidden_root', None) is None:
                self._browse_hidden_filter = self.filter()
                self._browse_hidden_root = identity
            self.setFilter(self._browse_hidden_filter | qt.QDir.Filter.Hidden)
            index = self.setRootPath(str(identity))
        return index

    def refresh_index(self, index):
        return self.index(self.filePath(index), index.column())

    def data(self, index, role=qt.Qt.ItemDataRole.DisplayRole):
        if (index.isValid() and role == qt.Qt.ItemDataRole.ForegroundRole
                and hidden_path(self.filePath(index), info=self.fileInfo(index))):
            return hidden_brush()
        if index.isValid() and role in BrowseRole._value2member_map_:
            if role == BrowseRole.Identity:
                return self.browse_identity(index)
            if role == BrowseRole.Container:
                return self.isDir(index)
            if role == BrowseRole.SortValue:
                if index.column() == 1:
                    if self.isDir(index):
                        stats = self.folder_totals.get(Path(self.filePath(index)))
                        return stats.size if stats is not None and not self.fileInfo(index).isSymLink() else None
                    return self.size(index)
                if index.column() == 3:
                    return self.lastModified(index)
                return self.fileName(index)
            item = self.item(index)
            if role == BrowseRole.Badge:
                return item.browser_thumbnail_badge
            if role == BrowseRole.Thumbnail:
                return (lambda size, cancelled: item.browser_thumbnail(size)) if item.browser_has_thumbnail else None
            if role == BrowseRole.Suffix:
                return '' if isinstance(item, Directory) else item.path.suffix
            if role == BrowseRole.Revision:
                return None
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
            from ...filesystem.local_access import check_local_path
            check_local_path(source, recursive=True)
            check_local_path(target, recursive=True)
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
    def multiData(self, index, roles):
        # Preserve data() overrides in subclasses such as CoverModel as well.
        for position in range(roles.size()):
            role = roles[position]
            role.setData(self.data(index, role.role()))

    """The list sorts displayed byte totals without changing other view models."""
    def __init__(self, filesystem, parent=None):
        super().__init__(parent)
        self.filesystem = filesystem
        self.setSourceModel(filesystem)
        self.setDynamicSortFilter(True)

    def mapFromSource(self, index):
        if index.isValid() and index.model() is self.filesystem:
            # Disk watching can reorder rows while indexes retain file pointers.
            refresh = getattr(self.filesystem, 'refresh_index', None)
            if refresh:
                index = refresh(index)
        return super().mapFromSource(index)

    def _bytes(self, index):
        return self.filesystem.data(index, BrowseRole.SortValue)

    def lessThan(self, left, right):
        from ..entry_views import value_less, label_less
        if left.column() == 0:
            a, b = left.data(BrowseRole.Container), right.data(BrowseRole.Container)
            if a != b:
                return bool(a)
        a, b = left.data(BrowseRole.SortValue), right.data(BrowseRole.SortValue)
        if left.column() != 0:
            decision = value_less(a, b, descending=self.sortOrder() == qt.Qt.SortOrder.DescendingOrder)
            if decision is not None:
                return decision
        return label_less(str(left.siblingAtColumn(0).data()), str(right.siblingAtColumn(0).data()))


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
