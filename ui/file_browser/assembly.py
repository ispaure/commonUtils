"""Reusable object-driven filesystem browser; applications supply domain behavior."""

from .. import pyside as qt
from .model import BrowserFileSystemModel, ByteSortModel, BrowserTree, _BrowserSelection
from .controls import ViewModeSelector, FolderSizeControl, ViewIcon, create_search_toggle, create_search_panel
from ..appearance.icons import set_painted_icon
from .navigation import NavigationBar
from .views import FileViews
from .editing import FilenameDelegate


class BrowserControls:
    """Construct browser widgets; workers, indexing and close policy stay on the browser."""
    def __init__(self, browser):
        self.browser = browser

    def build(self):
        browser = self.browser
        layout = qt.QVBoxLayout(browser)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.setSizeConstraint(qt.QLayout.SizeConstraint.SetMinimumSize)
        browser.search_bar = qt.QLineEdit()
        browser.search_bar.setAccessibleName('Search indexed files and folders')
        browser.search_bar.setPlaceholderText('Search this location and its subfolders')
        browser.search_bar.setToolTip('Search names, ignoring case. Words match in any order; '
                                  '"quoted phrases" keep word order. Spaces, underscores and '
                                  'hyphens are equivalent in phrases.')
        layout.addLayout(self.navigation())
        from .status import IndexStatusLabel, IndexActivityBar
        browser.index_status = IndexStatusLabel()
        browser.index_status.setTextFormat(qt.Qt.TextFormat.PlainText)
        browser.index_incomplete = False
        browser._index_details_dialog = None
        browser.index_details_button = qt.QPushButton('Index details…')
        browser.index_details_button.setToolTip('Show saved scan errors and unfinished folders')
        browser.index_details_button.clicked.connect(browser.show_index_details)
        browser.index_details_button.hide()
        browser.index_activity = IndexActivityBar()
        browser.index_activity.setRange(0, 0)
        browser.index_activity.setTextVisible(False)
        browser.index_activity.setAccessibleName('Background indexing in progress')
        browser.index_activity.hide()
        self.views()
        layout.addWidget(browser.splitter, 1)
        status_row = qt.QHBoxLayout()
        status_row.addWidget(browser.index_status,1)
        browser.index_activity.setFixedWidth(140)
        browser.index_activity.setMaximumHeight(14)
        status_row.addWidget(browser.index_activity)
        status_row.addWidget(browser.index_details_button)
        status_row.addWidget(browser.refresh_button)
        browser.index_status.setMinimumHeight(browser.refresh_button.sizeHint().height())
        layout.addLayout(status_row)
        self.preview()

    def navigation(self):
        browser = self.browser
        browser.navigation = NavigationBar(browser)
        browser.navigation.requested.connect(browser.navigate)
        toolbar = qt.QHBoxLayout()
        toolbar.setSpacing(5)
        toolbar.addWidget(browser.navigation, 1)
        controls = toolbar
        browser.view_selector = ViewModeSelector(browser)
        browser.view_selector.setAccessibleName('Browser view')
        browser.folder_size_button = FolderSizeControl(browser)
        browser.folder_size_slider = browser.folder_size_button.slider
        controls.addWidget(browser.folder_size_button)
        controls.addWidget(browser.view_selector)
        browser.preview_toggle = qt.QToolButton(browser)
        browser.preview_toggle.setText('Preview')
        set_painted_icon(browser.preview_toggle, ViewIcon, 4)
        browser.preview_toggle.setIconSize(qt.QSize(20, 20))
        browser.preview_toggle.setToolButtonStyle(qt.Qt.ToolButtonStyle.ToolButtonIconOnly)
        browser.preview_toggle.setCheckable(True)
        from ...configuration.settings import get_setting
        browser.preview_toggle.setChecked(get_setting('FileBrowser', 'preview_enabled', True))
        browser.preview_toggle.setText('Preview on' if browser.preview_toggle.isChecked() else 'Preview off')
        browser.preview_toggle.setToolTip('Show selection details, or current-folder properties when nothing is selected')
        browser.preview_toggle.setAccessibleName('Show file and folder preview')
        browser.preview_toggle.toggled.connect(browser._preview_toggled)
        controls.addWidget(browser.preview_toggle)
        controls.addWidget(browser.view_selector.storage_controls)
        # A host can append local tab controls after the size-map buttons.
        browser.workspace_controls = controls
        browser.search_button = create_search_toggle(browser, browser._search_toggled)
        controls.insertWidget(1, browser.search_button)
        browser.refresh_button = qt.QPushButton('Refresh index')
        browser.refresh_button.setToolTip('Check all files and saved sizes below the current folder')
        browser.refresh_button.clicked.connect(browser.refresh)
        return toolbar


    def views(self):
        browser = self.browser
        browser.model = BrowserFileSystemModel(browser)
        browser.model.setReadOnly(False)
        browser.model.setFilter(qt.QDir.Filter.AllDirs | qt.QDir.Filter.Files | qt.QDir.Filter.NoDotAndDotDot)
        browser.tree = BrowserTree()
        browser.sort_model = ByteSortModel(browser.model,browser)
        browser.tree.setModel(browser.sort_model)
        browser.tree.setSelectionModel(_BrowserSelection(browser.sort_model,browser.tree))
        browser.tree.expanded.connect(lambda index: browser.model.size_parents.add(browser.model.filePath(browser.sort_model.mapToSource(index))))
        browser.tree.collapsed.connect(lambda index: browser.model.size_parents.discard(browser.model.filePath(browser.sort_model.mapToSource(index))))
        browser.tree.setItemDelegate(FilenameDelegate(browser.tree))
        browser.tree.setSelectionBehavior(qt.QAbstractItemView.SelectionBehavior.SelectRows)
        browser.tree.setAlternatingRowColors(True)
        browser.tree.setUniformRowHeights(True)
        browser.tree.setSortingEnabled(True)
        browser.tree.sortByColumn(0, qt.Qt.SortOrder.AscendingOrder)
        browser.tree.setColumnWidth(0, 400)
        browser.tree.setColumnWidth(3, 180)
        browser.tree.setColumnWidth(1, 90)
        browser.tree.hideColumn(2)
        browser.tree.header().moveSection(3, 1)
        browser.tree.header().setStretchLastSection(False)
        browser.tree.header().setSectionResizeMode(0, qt.QHeaderView.ResizeMode.Stretch)
        for column in (1, 3):
            browser.tree.header().setSectionResizeMode(column, qt.QHeaderView.ResizeMode.ResizeToContents)
        browser.model.directory_boundary = browser.directory_boundary
        browser.views = FileViews(browser.model, browser.tree, browser, directory_handler=browser.handle_directory,
                               column_navigation=browser.column_navigation)
        browser.view_selector.buttons[2].setEnabled(browser.column_navigation)
        browser.views.selection_changed.connect(browser._selection_changed)
        browser.views.directory_changed.connect(browser.navigation.set_directory)
        browser.views.directory_changed.connect(browser._directory_changed)
        browser.views.directory_opened.connect(browser._directory_opened)
        browser.views.context_requested.connect(browser._context_menu)
        browser.views.activated.connect(browser._activate)
        browser.views.path_activated.connect(browser._activate_path)
        browser.views.idle.connect(browser._maybe_idle)
        browser.view_selector.currentIndexChanged.connect(browser.views.set_mode)
        browser.view_selector.currentIndexChanged.connect(lambda mode: browser.folder_size_button.setEnabled(mode < 3))
        browser.folder_size_slider.valueChanged.connect(browser.views.set_icon_scale)
        browser.splitter = qt.QSplitter()
        browser.splitter.setChildrenCollapsible(False)
        browser.list_stack = qt.QStackedWidget()
        browser.list_stack.addWidget(browser.views)
        from .index_search import IndexSearch
        browser.index_search = IndexSearch(browser)
        browser.index_search.idle.connect(browser._maybe_idle)
        browser.list_stack.addWidget(browser.index_search)
        browser.files_panel = qt.QWidget()
        files_layout = qt.QVBoxLayout(browser.files_panel)
        files_layout.setContentsMargins(0, 0, 0, 0)
        browser.search_panel, browser.close_search_button = create_search_panel(browser.files_panel, browser.search_bar, browser.close_search)
        files_layout.addWidget(browser.search_panel)
        files_layout.addWidget(browser.list_stack, 1)
        browser.search_panel.hide()
        browser.splitter.addWidget(browser.files_panel)


    def preview(self):
        browser = self.browser
        from .preview import create_preview_panel
        create_preview_panel(browser)

