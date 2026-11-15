"""Qt list selection with a detail pane rebuilt for the selected item."""

from . import QGroupBox, QHBoxLayout, QListWidget, QPushButton, QVBoxLayout, QWidget


class SelectionDetails(QGroupBox):
    """Host a list and details built by `show_details(entry)` on the GUI thread."""

    def __init__(self, title, show_details, parent=None, *, list_header=None,
                 list_width=(150, 240)):
        super().__init__(title, parent)
        self._entries = ()
        self._show_details = show_details

        self.selection_list = QListWidget()
        minimum_width, maximum_width = list_width
        self.selection_list.setMinimumWidth(minimum_width)
        self.selection_list.setMaximumWidth(maximum_width)
        list_panel = QWidget()
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(6)
        if list_header is not None:
            list_layout.addWidget(list_header)
        list_layout.addWidget(self.selection_list, 1)

        details = QWidget()
        self.details_layout = QVBoxLayout(details)
        self.details_layout.setContentsMargins(0, 0, 0, 0)
        self.details_layout.setSpacing(8)

        layout = QHBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(list_panel)
        layout.addWidget(details, 1)
        self.selection_list.currentRowChanged.connect(self._select_row)

    def set_entries(self, entries, *, label):
        """Replace the list and select the first entry, if present."""
        entries = tuple(entries)
        labels = [label(entry) for entry in entries]
        self.selection_list.clear()
        self._entries = entries
        self.selection_list.addItems(labels)
        if entries:
            self.selection_list.setCurrentRow(0)

    def _select_row(self, row):
        while self.details_layout.count():
            item = self.details_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        if 0 <= row < len(self._entries):
            self._show_details(self._entries[row])
            self.details_layout.addStretch()

    def add_detail_action(self, label, callback, *, enabled=True, tooltip=''):
        """Add a button that calls a no-argument action for the selected entry."""
        button = QPushButton(label)
        button.setEnabled(enabled)
        button.setToolTip(tooltip)
        button.clicked.connect(lambda: callback())
        self.details_layout.addWidget(button)
        return button
