"""Inline documentation navigation for the shared Markdown viewer."""
from ...formats.markdown_wiki import MarkdownWiki, documentation_root
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
        self.search.setAccessibleName('Search documentation')
        self.mode = qt.QComboBox()
        self.mode.addItem('File names & titles', 'filename')
        self.mode.addItem('Page text', 'content')
        self.mode.setAccessibleName('Documentation search mode')
        self.tree = qt.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setAccessibleName('Documentation files and folders')
        self.notice = qt.QLabel()
        self.notice.setWordWrap(True)
        for widget in (self.search, self.mode, self.tree, self.notice):
            layout.addWidget(widget)
        layout.setStretch(2, 1)
        self.timer = qt.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.populate)
        self.search.textChanged.connect(lambda: self.timer.start())
        self.mode.currentIndexChanged.connect(self.populate)
        self.tree.itemClicked.connect(self.open_item)
        self.tree.itemActivated.connect(self.open_item)
        viewer.path_changed.connect(self.select_path)
        self.populate()

    def populate(self):
        self.tree.clear()
        role = qt.Qt.ItemDataRole.UserRole
        def add(entries, parent):
            for entry in entries:
                item = qt.QTreeWidgetItem(parent, [entry.title])
                item.setData(0, role, entry.page)
                item.setToolTip(0, str(entry.location.relative_to(self.catalog.root)))
                add(entry.children, item)
        add(self.catalog.search(self.search.text(), self.mode.currentData()), self.tree)
        if self.search.text().strip():
            self.tree.expandAll()
        self.notice.setText('No matching pages.' if not self.tree.topLevelItemCount() else
                            (f'{len(self.catalog.errors)} pages or folders could not be read.' if self.catalog.errors else ''))
        self.select_path(self.viewer.current_path)

    def open_item(self, item, column=0):
        path = item.data(0, qt.Qt.ItemDataRole.UserRole)
        if path:
            self.viewer.open_document(path)
            self.select_path(self.viewer.current_path)
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
                self.tree.setCurrentItem(item)
                parent = item.parent()
                while parent:
                    parent.setExpanded(True)
                    parent = parent.parent()
                return
            iterator += 1
        self.tree.setCurrentItem(None)
