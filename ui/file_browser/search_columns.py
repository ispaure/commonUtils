"""Search result layout: names get space first; paths remain inspectable."""
from .. import pyside as qt


def configure_search_columns(tree):
    header = tree.header()
    header.setStretchLastSection(False)
    header.setSectionResizeMode(0, qt.QHeaderView.ResizeMode.Stretch)
    for column in (1, 2):
        header.setSectionResizeMode(column, qt.QHeaderView.ResizeMode.Fixed)
    header.setSectionResizeMode(3, qt.QHeaderView.ResizeMode.Interactive)
    tree.setColumnWidth(3, 260)
    tree.setTextElideMode(qt.Qt.TextElideMode.ElideMiddle)
    tree.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    tree._search_columns = SearchColumnLayout(tree)


def describe_search_row(row, tree=None):
    for column in range(4):
        row.setToolTip(column, row.text(column))
    if tree is not None:
        style_search_row(row, tree)


def style_search_row(row, tree):
    font = qt.QFont(tree.font())
    font.setWeight(qt.QFont.Weight.DemiBold)
    row.setFont(0, font)
    row.setForeground(3, tree.palette().color(qt.QPalette.ColorRole.PlaceholderText))


class SearchColumnLayout(qt.QObject):
    """Keep Path subordinate on narrow tabs; honor subsequent manual resizing."""
    def __init__(self, tree):
        super().__init__(tree)
        self.tree = tree
        self.manual = False
        self.adjusting = False
        self.timer = qt.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(0)
        self.timer.timeout.connect(self._compact_columns)
        tree.installEventFilter(self)
        tree.header().sectionResized.connect(self._resized)
        for signal in (tree.model().rowsInserted, tree.model().rowsRemoved,
                       tree.model().dataChanged, tree.model().modelReset):
            signal.connect(lambda *args: self.timer.start())
        self._compact_columns()

    def _resized(self, column, before, after):
        if column == 3 and not self.adjusting and self.tree.isVisible():
            self.manual = True

    def _compact_columns(self):
        metrics = self.tree.fontMetrics()
        for column, maximum in ((1, 130), (2, 110)):
            texts = [self.tree.headerItem().text(column)]
            texts.extend(self.tree.topLevelItem(row).text(column)
                         for row in range(min(self.tree.topLevelItemCount(), 1000)))
            width = max(metrics.horizontalAdvance(text) for text in texts) + 24
            self.tree.setColumnWidth(column, min(maximum, width))

    def eventFilter(self, watched, event):
        if event.type() in (qt.QEvent.Type.Show, qt.QEvent.Type.FontChange):
            self._compact_columns()
        if event.type() in (qt.QEvent.Type.PaletteChange, qt.QEvent.Type.FontChange):
            for row in range(self.tree.topLevelItemCount()):
                style_search_row(self.tree.topLevelItem(row), self.tree)
        if event.type() == qt.QEvent.Type.Resize and not self.manual:
            self.adjusting = True
            self.tree.setColumnWidth(3, min(300, max(110, int(self.tree.width() * .27))))
            self.adjusting = False
        return False
