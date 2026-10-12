"""An application-local picked source shared by all reusable browser views."""
import os
from pathlib import Path
from .. import pyside as qt

SOURCE_PROPERTY = 'commonUtilsLinkSource'


def picked_source():
    value = qt.QApplication.instance().property(SOURCE_PROPERTY)
    return Path(value) if value else None


def pick_source(path):
    source = Path(path).resolve(strict=True)
    if not source.is_file() and not source.is_dir():
        raise ValueError('Pick a regular file or folder')
    qt.QApplication.instance().setProperty(SOURCE_PROPERTY, str(source))


def cancel_source():
    qt.QApplication.instance().setProperty(SOURCE_PROPERTY, None)


def add_link_actions(menu, browser, selection, directory, mutating):
    def action(title, callback, enabled=True):
        item = menu.addAction(title)
        item.setEnabled(enabled)
        item.triggered.connect(lambda checked=False: browser._run(callback))
        return item
    if len(selection) == 1:
        action('Pick Link Source', lambda: pick_source(selection[0].path), not browser.stopping)
    source = picked_source()
    if source is None:
        return
    if directory is not None:
        available = mutating and source.exists() and Path(directory).is_dir()
        drop = qt.QMenu('Drop Link As', menu)
        menu.addMenu(drop)
        menu._link_drop_menu = drop
        drop.setToolTip(str(source))
        def add(title, kind, enabled):
            item = drop.addAction(title)
            item.setEnabled(enabled)
            item.triggered.connect(lambda checked=False: browser.file_actions.drop_link(source, directory, kind))
        add('Symbolic Link', 'symbolic', available)
        try:
            hard = available and source.is_file() and source.stat().st_dev == Path(directory).stat().st_dev
        except OSError:
            hard = False
        if source.is_file():
            add('Hard Link', 'hard', hard)
        if os.name == 'nt' and source.is_dir():
            add('Junction', 'junction', available)
    action('Cancel Link Creation', cancel_source, not browser.stopping)
