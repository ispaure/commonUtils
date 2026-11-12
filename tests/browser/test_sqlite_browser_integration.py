"""SQLite context action preserves existing activation and retained host lifetimes."""
from contextlib import closing
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from threading import Event
from unittest.mock import patch

from commonUtils.testing.stages import TestStage
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser import FileBrowser
from commonUtils.ui.resources.browser import ResourceBrowser
from commonUtils.ui.sqlite_browser.controller import SQLiteController
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.provider import ResourceCapabilities

TEST_STAGE = TestStage.REGRESSION


class SQLiteBrowserIntegrationTests(QtTestCase):
    def setUp(self):
        self.temp = self.temporary_directory()
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / 'example.sqlite3'
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT)')
            db.execute("INSERT INTO records VALUES (1, 'before')")
        network = patch('commonUtils.filesystem.network.is_network_location', return_value=False)
        network.start()
        self.addCleanup(network.stop)

    def browser(self, *, writable=False):
        browser = FileBrowser(self.root, calculate_folder_sizes=False,
                              sqlite_write_allowed=(lambda path: True) if writable else None)
        browser.show()
        self.wait_until(lambda: browser.model.index(str(self.path)).isValid())
        return browser

    def wait_editor(self, editor):
        from shiboken6 import isValid
        def discard_fixture():
            if isValid(editor):
                self.wait_until(lambda: not isValid(editor) or not editor.busy)
                if isValid(editor):
                    editor.discard()
        self.addCleanup(discard_fixture)
        self.wait_until(lambda: not editor.busy)
        self.assertIsNotNone(editor.page, editor.status.text())

    def test_context_action_and_default_readonly_preserve_activation(self):
        browser = self.browser()
        received = []
        browser.install_extension('existing', activation_handlers=(lambda item, context: received.append(item.path) or True,))
        index = browser.model.index(str(self.path))
        menu = browser.context_menu_for(index)
        self.addCleanup(menu.deleteLater)
        action = next(item for item in menu.actions() if item.text() == 'Inspect SQLite…')
        action.trigger()
        editor = browser.sqlite_browser.windows[0]
        self.wait_editor(editor)
        self.assertFalse(editor.editing)
        editor.enable_editing()
        self.wait_until(lambda: not editor.busy)
        self.assertFalse(editor.editing)
        browser._activate(index)
        self.assertEqual(received, [self.path])
        editor.close()

    def test_host_save_and_dirty_close_veto_keep_browser_visible(self):
        browser = self.browser(writable=True)
        editor = browser.sqlite_browser.open(self.path)
        self.wait_editor(editor)
        editor.enable_editing()
        self.wait_until(lambda: not editor.busy)
        self.assertTrue(editor.editing, editor.status.text())
        self.assertTrue(editor.stage_update(0, {'value': 'after'}))
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel):
            self.assertFalse(browser.close())
        self.assertTrue(browser.isVisible())
        self.assertFalse(browser.stopping)
        self.assertTrue(editor.dirty)
        editor.save()
        self.wait_until(lambda: not editor.busy)
        self.assertFalse(editor.dirty, editor.status.text())
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT value FROM records').fetchone()[0], 'after')
        editor.close()

    def test_local_resource_uses_explicit_hook_and_same_guard(self):
        browser = ResourceBrowser(LocalFiles(self.root), sqlite_write_allowed=lambda path: True)
        browser.show()
        self.wait_until(lambda: not browser.busy)
        self.assertTrue(browser.sqlite_browser.available(self.path))
        editor = browser.sqlite_browser.open(self.path)
        self.wait_editor(editor)
        editor.enable_editing()
        self.wait_until(lambda: not editor.busy)
        self.assertTrue(editor.editing, editor.status.text())
        editor.close()
        self.wait_until(lambda: not browser.sqlite_browser.windows)
        browser.stop()
        self.wait_until(lambda: not browser.busy)

    def test_replace_and_mapped_providers_have_no_sqlite_action(self):
        browser = self.browser()
        fake = SimpleNamespace(root=self.root, physical_root=self.root,
                               capabilities=ResourceCapabilities(replace=True))
        controller = SQLiteController(browser, provider=fake)
        self.assertFalse(controller.available(self.path))
        class MappedFiles(LocalFiles):
            pass
        controller = SQLiteController(browser, provider=MappedFiles(self.root))
        self.assertFalse(controller.available(self.path))

    def test_resource_parent_observes_dirty_veto_before_releasing_provider(self):
        from commonUtils.ui.resources.lifecycle import ResourceOperations
        browser = ResourceBrowser(LocalFiles(self.root), sqlite_write_allowed=lambda path: True)
        browser.show()
        self.wait_until(lambda: not browser.busy)
        owner = ResourceOperations()
        owner.bind(browser.provider)
        owner.own(browser, cancel=browser.stop)
        editor = browser.sqlite_browser.open(self.path)
        self.wait_editor(editor)
        editor.enable_editing()
        self.wait_until(lambda: not editor.busy)
        self.assertTrue(editor.stage_update(0, {'value': 'unsaved'}))
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel):
            self.assertTrue(owner.stop())
        self.assertTrue(owner.busy)
        self.assertFalse(browser.can_retire)
        editor.discard()
        editor.close()
        self.wait_until(lambda: not browser.sqlite_browser.windows)
        owner.stop()
        self.wait_until(lambda: not owner.busy)

    def test_known_managed_path_cannot_enable_editing(self):
        browser = self.browser(writable=True)
        browser.sqlite_browser.readonly_paths = (self.path,)
        editor = browser.sqlite_browser.open(self.path)
        self.wait_editor(editor)
        editor.enable_editing()
        self.wait_until(lambda: not editor.busy)
        self.assertFalse(editor.editing)
        self.assertFalse(editor.stage_update(0, {'value': 'forbidden'}))
        editor.close()

    def test_parent_close_waits_for_sqlite_worker_and_retries(self):
        entered, release = Event(), Event()
        self.addCleanup(release.set)
        def policy(path):
            entered.set()
            if not release.wait(5):
                raise TimeoutError('Fixture did not release access check')
            return True
        browser = self.browser()
        browser.sqlite_browser.write_allowed = policy
        editor = browser.sqlite_browser.open(self.path)
        self.wait_until(entered.is_set)
        self.assertTrue(editor.busy)
        self.assertFalse(browser.close())
        self.assertTrue(editor.close_pending)
        release.set()
        self.wait_until(lambda: not browser.sqlite_browser.windows and not browser.isVisible(),
                        drain_deferred=True)
