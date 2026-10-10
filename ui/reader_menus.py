"""Shared desktop reader actions; format-specific navigation stays with callers."""
import json
from pathlib import Path
from ..persistence import atomic_write_json
from threading import RLock

from . import pyside as qt
from ..storage import cache_directory

_history_lock = RLock()


class RecentFiles:
    """Bounded local-file history; readers choose which formats to show."""
    def __init__(self, *, path=None):
        self.path = Path(path) if path else cache_directory(create=False) / 'Readers' / 'recent.json'

    def paths(self, suffixes=()):
        try:
            if self.path.stat().st_size > 65536:
                return []
            values = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(values, list):
                return []
            result = []
            for value in values[:40]:
                if not isinstance(value, str):
                    continue
                path = Path(value)
                if path.is_absolute() and path.is_file() and (not suffixes or path.suffix.lower() in suffixes):
                    result.append(path)
            return result
        except (OSError, ValueError):
            return []

    def add(self, path):
        path = Path(path).resolve()
        with _history_lock:
            values = [str(path)] + [str(item) for item in self.paths() if item != path]
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            atomic_write_json(self.path, values[:40], allow_nan=True)



class ReaderMenus(qt.QObject):
    """Consistent File/Edit/View/Navigate menus with platform standard shortcuts."""
    def __init__(self, owner, bar, *, open_file, edit_metadata, close, fullscreen,
                 open_path=None, find=None, open_label='Open…', suffixes=(), history=None):
        super().__init__(owner)
        self.shortcut_widget = owner
        while self.shortcut_widget is not None and not isinstance(self.shortcut_widget, qt.QWidget):
            self.shortcut_widget = self.shortcut_widget.parent()
        self.bar = bar
        self.file = bar.addMenu('&File')
        self.edit = bar.addMenu('&Edit')
        self.view = bar.addMenu('&View')
        self.navigate = bar.addMenu('&Navigate')
        self.open_action = self.action(self.file, open_label, open_file, qt.QKeySequence.StandardKey.Open)
        self.history = history or RecentFiles()
        self.recent = self.file.addMenu('Open recent')
        self._open_path = open_path
        self._suffixes = suffixes
        self.recent.aboutToShow.connect(self._refresh_recent)
        self.file.addSeparator()
        self.close_action = self.action(self.file, 'Close', close, qt.QKeySequence.StandardKey.Close)
        self.metadata_action = self.action(self.edit, 'Edit metadata…', edit_metadata, 'Ctrl+I')
        self.find_action = self.action(self.edit, 'Find…', find, qt.QKeySequence.StandardKey.Find) if find else None
        self.fullscreen_action = self.action(self.view, 'Full screen', fullscreen, 'F11', checkable=True)

    def action(self, menu, label, callback, shortcut=None, *, checkable=False):
        action = menu.addAction(label)
        action.setCheckable(checkable)
        action.setAutoRepeat(False)
        if shortcut is not None:
            action.setShortcut(qt.QKeySequence(shortcut))
            action.setShortcutContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            if self.shortcut_widget is not None:
                self.shortcut_widget.addAction(action)
        action.triggered.connect(lambda checked=False: callback())
        return action

    def _refresh_recent(self):
        self.recent.clear()
        paths = self.history.paths(self._suffixes)
        if not paths or self._open_path is None:
            self.recent.addAction('No recent files').setEnabled(False)
            return
        for path in paths[:12]:
            action = self.action(self.recent, path.name.replace('&', '&&'), lambda path=path: self._open_path(path))
            action.setToolTip(str(path))

    def remember(self, path):
        try:
            self.history.add(path)
        except OSError:
            pass  # Reading a book must not depend on writable history storage.
