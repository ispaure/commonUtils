"""Reusable archive contents view; navigation and presentation only.

The owner supplies validated entries and decoded previews and handles requests
for extraction, removal and preview. This widget has no password policy, worker,
filesystem mutations, executable discovery or Logistics imports.
"""
from pathlib import PurePosixPath
from .. import pyside as qt
from .widgets import ImagePreview, ArchiveItem, size_text


class ArchiveContents(qt.QWidget):
    preview_requested = qt.Signal(str)
    extract_requested = qt.Signal(object)
    remove_requested = qt.Signal(object)
    selection_changed = qt.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.path = None
        self.members = ()
        self.folder = ''
        self.busy = False
        self.editable = False
        self._member_lookup = {}
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.splitter = qt.QSplitter()
        self.folders = qt.QTreeWidget()
        self.folders.setHeaderLabel('Folders')
        self.folders.setMinimumWidth(140)
        self.folders.setAccessibleName('Archive folders')
        self.folders.itemSelectionChanged.connect(self._folder_selected)
        self.splitter.addWidget(self.folders)
        contents = qt.QWidget()
        content_layout = qt.QVBoxLayout(contents)
        content_layout.setContentsMargins(0, 0, 0, 0)
        row = qt.QHBoxLayout()
        self.up = qt.QToolButton()
        self.up.setIcon(self.style().standardIcon(qt.QStyle.StandardPixmap.SP_ArrowUp))
        self.up.setToolTip('Parent folder (Alt+Up)')
        self.up.setAccessibleName('Parent folder')
        self.up.clicked.connect(self.up_folder)
        row.addWidget(self.up)
        self.breadcrumb = qt.QLabel('Archive contents')
        self.breadcrumb.setTextFormat(qt.Qt.TextFormat.PlainText)
        row.addWidget(self.breadcrumb, 1)
        self.search = qt.QLineEdit()
        self.search.setPlaceholderText('Search all entries…')
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(180)
        self.search.setAccessibleName('Search archive entries')
        self.search.textChanged.connect(self._render)
        row.addWidget(self.search)
        content_layout.addLayout(row)
        self.files = qt.QTreeWidget()
        self.files.setHeaderLabels(['Name', 'Size', 'Packed', 'Saved', 'Modified', 'Protection'])
        self.files.setRootIsDecorated(False)
        self.files.setAlternatingRowColors(True)
        self.files.setSelectionMode(qt.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.files.setSortingEnabled(True)
        self.files.setAccessibleName('Archive entries')
        self.files.header().setSectionResizeMode(0, qt.QHeaderView.ResizeMode.Stretch)
        self.files.header().setSectionResizeMode(4, qt.QHeaderView.ResizeMode.ResizeToContents)
        self.files.itemDoubleClicked.connect(self._activate)
        self.files.itemSelectionChanged.connect(self._selection)
        self.files.setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)
        self.files.customContextMenuRequested.connect(self._context_menu)
        content_layout.addWidget(self.files, 1)
        self.empty = qt.QLabel('<h1>Your archive workbench</h1>'
                              '<p>Explore, pack, protect and unpack your files.</p><br>'
                              '<p><b>ZIP for sharing · AES for privacy · TAR for Linux</b></p>'
                              '<p>Open an archive above, or drop files here to start a new one.</p>')
        self.empty.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        self.empty.setMargin(24)
        content_layout.addWidget(self.empty, 1)
        self.splitter.addWidget(contents)
        preview_panel = self.preview_panel = qt.QWidget()
        preview_layout = qt.QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        self.details = qt.QLabel('ENTRY DETAILS')
        self.details.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.details.setWordWrap(True)
        preview_layout.addWidget(self.details)
        self.preview_button = qt.QPushButton('Preview file')
        self.preview_button.clicked.connect(self._request_preview)
        preview_layout.addWidget(self.preview_button)
        self.preview_text = qt.QPlainTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlaceholderText('Select a file for details. Preview text and images without extracting them.')
        self.preview_text.setAccessibleName('Archive text preview')
        preview_layout.addWidget(self.preview_text, 1)
        self.preview_image = ImagePreview()
        self.preview_image.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        self.preview_image.setAccessibleName('Archive image preview')
        self.image_scroll = qt.QScrollArea()
        self.image_scroll.setWidgetResizable(True)
        self.image_scroll.setWidget(self.preview_image)
        self.image_scroll.hide()
        preview_layout.addWidget(self.image_scroll, 1)
        self.splitter.addWidget(preview_panel)
        self.splitter.setSizes([180, 680, 250])
        layout.addWidget(self.splitter, 1)
        self._render()

    def set_entries(self, path, members):
        self.path = path
        self.members = tuple(members)
        self.folder = ''
        self._member_lookup = {entry.name.rstrip('/'): entry for entry in self.members}
        with qt.QSignalBlocker(self.search):
            self.search.clear()
        self._build_folders()
        self._render()

    def set_state(self, *, busy=False, editable=False, closing=False):
        self.busy = busy
        self.editable = editable
        self.setEnabled(not busy and not closing)
        self._selection_state()

    def _selection_state(self):
        selection = self.files.selectedItems()
        self.preview_button.setEnabled(not self.busy and len(selection) == 1
            and not selection[0].data(0, qt.Qt.ItemDataRole.UserRole)[1])

    def selected_paths(self):
        return [item.data(0, qt.Qt.ItemDataRole.UserRole)[0] for item in self.files.selectedItems()]

    def _request_preview(self):
        selection = self.files.selectedItems()
        if len(selection) == 1:
            name, directory = selection[0].data(0, qt.Qt.ItemDataRole.UserRole)
            if not directory:
                self.preview_requested.emit(name)

    def show_preview(self, result):
        if isinstance(result, bytes):
            pixmap = qt.QPixmap()
            if not pixmap.loadFromData(result, 'PNG'):
                self.show_preview('The image could not be displayed.')
                return
            self.preview_image.set_preview(pixmap)
            self.preview_text.hide()
            self.image_scroll.show()
        else:
            self.preview_text.setPlainText(result)
            self.preview_text.show()
            self.image_scroll.hide()

    def _build_folders(self):
        self.folders.blockSignals(True)
        self.folders.clear()
        root = qt.QTreeWidgetItem(self.folders, ['All contents'])
        root.setData(0, qt.Qt.ItemDataRole.UserRole, '')
        nodes = {'': root}
        folder_names = set()
        for entry in self.members:
            parts = PurePosixPath(entry.name).parts
            for i in range(1, len(parts) + (1 if entry.directory else 0)):
                folder_names.add('/'.join(parts[:i]) + '/')
        for folder in sorted(folder_names):
            parent = folder.rstrip('/').rsplit('/', 1)[0] + '/' if '/' in folder.rstrip('/') else ''
            node = qt.QTreeWidgetItem(nodes[parent], [PurePosixPath(folder).name])
            node.setData(0, qt.Qt.ItemDataRole.UserRole, folder)
            node.setIcon(0, self.style().standardIcon(qt.QStyle.StandardPixmap.SP_DirIcon))
            nodes[folder] = node
        root.setExpanded(True)
        self.folders.setCurrentItem(root)
        self._folder_nodes = nodes
        self.folders.blockSignals(False)


    def _folder_selected(self):
        item = self.folders.currentItem()
        if item:
            self.folder = item.data(0, qt.Qt.ItemDataRole.UserRole)
            self.search.clear()
            self._render()


    def _render(self):
        query = self.search.text().casefold().strip()
        self.files.setSortingEnabled(False)
        self.files.clear()
        rows = {}
        for entry in self.members:
            if query:
                if query not in entry.name.casefold():
                    continue
                name, directory = entry.name, entry.directory
            else:
                if not entry.name.startswith(self.folder):
                    continue
                relative = entry.name[len(self.folder):].rstrip('/')
                if not relative:
                    continue
                name = relative.split('/')[0]
                directory = '/' in relative or entry.directory
            full_name = (name if query else self.folder + name) + ('/' if directory and not name.endswith('/') else '')
            if full_name in rows:
                continue
            exact = not directory or entry.name.rstrip('/') == full_name.rstrip('/')
            size, packed = (entry.size, entry.packed) if exact and not directory else (None, None)
            saved = f'{(1 - packed / size) * 100:.0f}%' if size and packed is not None else '—'
            item = ArchiveItem(self.files, [name.rstrip('/'), size_text(size), size_text(packed), saved,
                                                  entry.modified if exact else '', 'Encrypted' if exact and entry.encrypted else ''])
            item.setData(0, qt.Qt.ItemDataRole.UserRole, (full_name, directory))
            role = int(qt.Qt.ItemDataRole.UserRole) + 1
            for column, value in ((1, size), (2, packed), (3, (1 - packed / size) if size and packed is not None else 0)):
                item.setData(column, role, value)
            item.setIcon(0, self.style().standardIcon(qt.QStyle.StandardPixmap.SP_DirIcon if directory else qt.QStyle.StandardPixmap.SP_FileIcon))
            item.setToolTip(0, full_name)
            rows[full_name] = item
        self.files.setSortingEnabled(True)
        self.files.sortItems(0, qt.Qt.SortOrder.AscendingOrder)
        self.breadcrumb.setText('Search results' if query else '/ ' + self.folder)
        self.empty.setVisible(not self.path)
        self.folders.setVisible(bool(self.path))
        self.preview_panel.setVisible(bool(self.path))
        self.search.setVisible(bool(self.path))
        self.breadcrumb.setVisible(bool(self.path))
        self.up.setVisible(bool(self.path))
        self.files.setVisible(bool(self.path))
        self._selection()


    def context_menu(self):
        if not self.files.selectedItems() or self.busy:
            return None
        menu = qt.QMenu(self)
        if self.preview_button.isEnabled():
            menu.addAction('Preview file', self._request_preview)
        menu.addAction('Extract selected…', lambda: self.extract_requested.emit(self.selected_paths()))
        if self.editable:
            menu.addSeparator()
            menu.addAction('Remove from ZIP…', lambda: self.remove_requested.emit(self.selected_paths()))
        return menu

    def _context_menu(self, position):
        menu = self.context_menu()
        if menu is not None:
            menu.exec(self.files.viewport().mapToGlobal(position))


    def _activate(self, item, column=0):
        name, directory = item.data(0, qt.Qt.ItemDataRole.UserRole)
        if directory:
            self.folders.setCurrentItem(self._folder_nodes[name])
        else:
            self.preview_requested.emit(name)


    def up_folder(self):
        if self.folder and not self.busy:
            parent = self.folder.rstrip('/').rsplit('/', 1)[0] + '/' if '/' in self.folder.rstrip('/') else ''
            self.folders.setCurrentItem(self._folder_nodes[parent])


    def _selection(self):
        selection = self.files.selectedItems()
        self.preview_text.clear()
        self.preview_image.clear()
        self.image_scroll.hide()
        self.preview_text.show()
        if len(selection) == 1:
            name, directory = selection[0].data(0, qt.Qt.ItemDataRole.UserRole)
            entry = self._member_lookup.get(name.rstrip('/'))
            details = f'{"FOLDER" if directory else "FILE"}\n{name}'
            if entry and not directory:
                details += f'\n\nSize: {size_text(entry.size)}\nPacked: {size_text(entry.packed)}\nModified: {entry.modified}'
                details += '\nProtection: ' + ('Encrypted' if entry.encrypted else 'None')
            self.details.setText(details)
        else:
            self.details.setText(f'{len(selection)} entries selected' if selection else 'ENTRY DETAILS')
        self._selection_state()
        self.selection_changed.emit()
