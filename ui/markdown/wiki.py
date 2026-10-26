"""Inline documentation navigation for the shared Markdown viewer."""
from ...formats.markdown.wiki import MarkdownWiki, documentation_root
from .. import pyside as qt
from ..readers.reader_chrome import reader_button


class WikiPanel(qt.QWidget):
    def __init__(self, viewer, directory):
        super().__init__(viewer)
        self.viewer = viewer
        self.catalog = MarkdownWiki(directory)
        for button, label in ((viewer.back_button, 'Back'), (viewer.forward_button, 'Forward')):
            button.setText(label)
            button.setToolButtonStyle(qt.Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.up_button = reader_button(viewer, 'Up', icon='up')
        self.up_button.setToolTip('Open the parent folder’s documentation page')
        self.up_button.clicked.connect(self.go_up)
        viewer.navigation_toolbar.insertWidget(2, self.up_button)
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.search = qt.QLineEdit()
        self.search.setPlaceholderText('Search documentation…')
        self.search.setClearButtonEnabled(True)
        from ..appearance.icons import painted_icon
        from ..readers.reader_chrome import ReaderIcon
        self.search.addAction(painted_icon(ReaderIcon, 'search'), qt.QLineEdit.ActionPosition.LeadingPosition)
        self.search.setAccessibleName('Search documentation library')
        self.search.setToolTip('Filter pages across this library; use Find in this page for the open document')
        self.mode = qt.QComboBox()
        self.mode.addItem('File names & titles', 'filename')
        self.mode.addItem('Page text', 'content')
        self.mode.setAccessibleName('Documentation search mode')
        self.mode.hide()
        self.tree = qt.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setDragDropMode(qt.QAbstractItemView.DragDropMode.NoDragDrop)
        self.tree.setEditTriggers(qt.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setAccessibleName('Documentation files and folders')
        self.notice = qt.QLabel()
        self.notice.setWordWrap(True)
        self.notice.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.notice.hide()
        search_row = qt.QHBoxLayout()
        search_row.addWidget(qt.QLabel('Documentation Library'))
        search_row.addWidget(self.search, 1)
        layout.addLayout(search_row)
        for widget in (self.mode, self.tree, self.notice):
            layout.addWidget(widget)
        layout.setStretch(2, 1)
        self.timer = qt.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(400)
        self.timer.timeout.connect(self.populate)
        self.search.textChanged.connect(self.query_changed)
        self.mode.currentIndexChanged.connect(self.populate)
        self.tree.currentItemChanged.connect(self.selection_changed)
        self.tree.itemClicked.connect(lambda item, column:
            self.open_item(item) if not item.data(0, qt.Qt.ItemDataRole.UserRole) else None)
        self.tree.itemActivated.connect(self.open_item)
        viewer.path_changed.connect(self.select_path)
        self.populate()

    def query_changed(self):
        self.mode.setVisible(bool(self.search.text().strip()))
        self.timer.start()
        if hasattr(self.viewer, 'search_highlights'):
            if not self.search.text().strip():
                self.viewer._clear_search_selection('library')
            self.viewer._refresh_search_highlights()

    def populate(self):
        self.timer.stop()
        blocked = self.tree.blockSignals(True)
        self.tree.setCurrentItem(None)
        # Detach nodes before retiring their Python wrappers. Keep them alive
        # through the replacement so a model reset cannot delete an item still
        # referenced by selection or document-navigation handlers.
        retired = []
        while self.tree.topLevelItemCount():
            retired.append(self.tree.takeTopLevelItem(0))
        role = qt.Qt.ItemDataRole.UserRole
        def add(entries, parent):
            for entry in entries:
                item = qt.QTreeWidgetItem(parent, [entry.title])
                item.setData(0, role, entry.page)
                item.setToolTip(0, str(entry.location.relative_to(self.catalog.root)))
                add(entry.children, item)
                if entry.location == self.catalog.root:
                    item.setExpanded(True)
        add(self.catalog.search(self.search.text(), self.mode.currentData()), self.tree)
        if self.search.text().strip():
            self.tree.expandAll()
        self.notice.setText('No matching pages.' if not self.tree.topLevelItemCount() else
                            (f'{len(self.catalog.errors)} pages or folders could not be read.' if self.catalog.errors else ''))
        self.notice.setVisible(bool(self.notice.text()))
        self.select_path(self.viewer.current_path)
        self.tree.blockSignals(blocked)

    def selection_changed(self, item, previous):
        if item is not None and item.data(0, qt.Qt.ItemDataRole.UserRole):
            self.open_item(item)

    def open_item(self, item, column=0):
        path = item.data(0, qt.Qt.ItemDataRole.UserRole)
        if path:
            if path != self.viewer.current_path:
                self.viewer.open_document(path)
            self.select_path(self.viewer.current_path)
            self.viewer._reveal_library_match()
        else:
            item.setExpanded(not item.isExpanded())

    def go_up(self):
        target = self.catalog.parent_page(self.viewer.current_path)
        if target is not None:
            return self.viewer.open_document(target)
        return False

    def select_path(self, path):
        if path:
            root = documentation_root(path, self.catalog.root)
            if root != self.catalog.root:
                self.catalog = MarkdownWiki(root)
                self.search.clear()
                self.populate()
                return
        target = self.catalog.parent_page(path)
        self.up_button.setEnabled(target is not None)
        self.up_button.setToolTip(f'Up: {target.name}' if target else 'No parent folder page')
        iterator = qt.QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            if path and item.data(0, qt.Qt.ItemDataRole.UserRole) == path:
                blocked = self.tree.blockSignals(True)
                self.tree.setCurrentItem(item)
                self.tree.blockSignals(blocked)
                parent = item.parent()
                while parent:
                    parent.setExpanded(True)
                    parent = parent.parent()
                return
            iterator += 1
        blocked = self.tree.blockSignals(True)
        self.tree.setCurrentItem(None)
        self.tree.blockSignals(blocked)
