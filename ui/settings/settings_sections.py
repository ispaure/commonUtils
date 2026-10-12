"""Reusable storage-scope navigation for retained settings editors and panels."""
from dataclasses import dataclass
from .. import pyside as qt

SCOPES = (('application', 'Application Settings'), ('personal', 'Personal'))


@dataclass(frozen=True)
class SettingsSection:
    scope: str
    key: str
    title: str
    widget: qt.QWidget
    nested: bool = False


class _ScopePage(qt.QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.row = qt.QVBoxLayout(self)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.tabs = qt.QTabWidget(self)
        self.tabs.setAccessibleName('Settings sections')
        self.row.addWidget(self.tabs)
        self._sections = ()
        self.direct = None

    def set_sections(self, sections):
        if sections == self._sections:
            return
        current = self.tabs.currentWidget() if self.tabs.count() else self.direct
        for section in self._sections:
            section.widget.hide()
            self.row.removeWidget(section.widget)
        while self.tabs.count():
            self.tabs.removeTab(0)
        self._sections = tuple(sections)
        self.direct = None
        nested = len(sections) > 1 or any(section.nested for section in sections)
        self.tabs.setVisible(nested)
        if nested:
            for section in sections:
                self.tabs.addTab(section.widget, section.title)
            if current in [section.widget for section in sections]:
                self.tabs.setCurrentWidget(current)
        elif sections:
            self.direct = sections[0].widget
            self.row.addWidget(self.direct)
            self.direct.show()


class ScopedSettings(qt.QWidget):
    """Show only applicable scopes; a single custom panel needs no inner tab.

    Mark the combined INI section nested=True to retain an INI files subtab.
    Repeated updates keep editor objects and selections, including dirty buffers.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = qt.QTabWidget(self)
        self.tabs.setAccessibleName('Settings storage scope')
        layout.addWidget(self.tabs)
        self.pages = {}

    def set_sections(self, sections):
        sections = tuple(sections)
        keys = [(section.scope, section.key) for section in sections]
        if len(keys) != len(set(keys)):
            raise ValueError('Settings section identities must be unique within each scope')
        if any(section.scope not in dict(SCOPES) for section in sections):
            raise ValueError('Settings scope must be application or personal')
        current = self.tabs.currentWidget()
        for scope, title in SCOPES:
            entries = tuple(section for section in sections if section.scope == scope)
            page = self.pages.get(scope)
            if entries and page is None:
                page = self.pages[scope] = _ScopePage(self)
            if page is None:
                continue
            page.set_sections(entries)
            index = self.tabs.indexOf(page)
            if entries and index < 0:
                self.tabs.addTab(page, title)
            elif not entries and index >= 0:
                self.tabs.removeTab(index)
                page.hide()
        for position, (scope, _) in enumerate((pair for pair in SCOPES
                                               if pair[0] in self.pages and self.tabs.indexOf(self.pages[pair[0]]) >= 0)):
            index = self.tabs.indexOf(self.pages[scope])
            if index != position:
                self.tabs.tabBar().moveTab(index, position)
        self.tabs.setVisible(bool(self.tabs.count()))
        if current is not None and self.tabs.indexOf(current) >= 0:
            self.tabs.setCurrentWidget(current)
