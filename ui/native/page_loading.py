"""Compact page-load feedback kept outside native toolbars and document content."""
import toga
from toga.style import Pack
from toga.style.pack import ROW, CENTER


class PageLoading:
    def __init__(self, article):
        self.article = article
        self.spinner = toga.ActivityIndicator(style=Pack(width=24, height=24))
        self.caption = toga.Label('Loading page…', style=Pack(flex=1))
        self.row = toga.Box(children=[self.spinner, self.caption],
                            style=Pack(direction=ROW, align_items=CENTER, margin=4))
        self.active = False

    def start(self):
        self.active = True
        if self.row.parent is None:
            self.article.insert(0, self.row)
        self.spinner.start()

    def finish(self):
        self.active = False
        self.spinner.stop()
        if self.row.parent is not None:
            self.row.parent.remove(self.row)
