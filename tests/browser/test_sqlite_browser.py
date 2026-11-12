"""Exercise Qt SQLite inspection with real disposable database files."""

from contextlib import closing
import os
from pathlib import Path
import sqlite3
from threading import Event, get_ident
import unittest
from unittest.mock import patch

from commonUtils.testing.stages import TestStage

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from commonUtils.integrations.sqlite import Transaction
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.sqlite_browser import SQLiteBrowser
from shiboken6 import isValid


TEST_STAGE = TestStage.REGRESSION


def select(combo, value):
    combo.setCurrentIndex(combo.findData(value))


class SQLiteBrowserTests(QtTestCase):
    def setUp(self):
        self.path = Path(self.temporary_directory().name) / 'records.sqlite'
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.executescript("""
                CREATE TABLE records (
                    id INTEGER PRIMARY KEY, category TEXT DEFAULT 'even',
                    body UNIQUE, extra BLOB,
                    derived TEXT GENERATED ALWAYS AS (category || id) STORED
                );
                CREATE VIEW visible AS SELECT id, body FROM records;
                CREATE TABLE unkeyed (label TEXT);
                CREATE TABLE nullable (key TEXT PRIMARY KEY, label TEXT);
                INSERT INTO nullable VALUES (NULL, 'no reliable identity'), ('k', 'keyed');
                INSERT INTO unkeyed VALUES ('one');
            """)
            connection.executemany(
                'INSERT INTO records(id, category, body, extra) VALUES (?, ?, ?, ?)',
                ((i, 'even' if i % 2 == 0 else 'odd', f'row {i}', b'\x00\xff')
                 for i in range(1, 251)))

    def open_browser(self, *, writable=False, access_check=None):
        browser = SQLiteBrowser(self.path, writable=writable, access_check=access_check)
        browser.show()
        self.addCleanup(self.discard_browser, browser)
        self.wait_idle(browser)
        self.assertIsNotNone(browser.page, browser.status.text())
        return browser

    def discard_browser(self, browser):
        if isValid(browser):
            browser.operation.request_cancel()
            self.wait_until(lambda: not isValid(browser) or not browser.busy)
            if isValid(browser):
                browser.discard()

    def wait_idle(self, browser):
        self.wait_until(lambda: not browser.busy)

    def switch_table(self, browser, name):
        select(browser.table_selector, name)
        self.wait_idle(browser)
        self.assertEqual(browser.table.name, name, browser.status.text())

    def enable_edits(self, browser):
        browser.enable_editing()
        self.wait_idle(browser)
        self.assertTrue(browser.editing, browser.status.text())

    def rows(self, sql, parameters=()):
        with closing(sqlite3.connect(self.path)) as connection:
            return connection.execute(sql, parameters).fetchall()

    def test_initial_read_only_schema_pagination_filter_and_sort(self):
        browser = self.open_browser()
        self.assertFalse(browser.editing)
        self.assertFalse(browser.editing_button.isEnabled())
        self.assertEqual({table.name for table in browser.tables},
                         {'records', 'visible', 'unkeyed', 'nullable'})
        self.switch_table(browser, 'records')
        self.assertEqual(browser.table.primary_key, ('id',))
        self.assertEqual(browser.schema_view.item(1, 4).text(), "'even'")
        self.assertEqual(browser.schema_view.item(4, 5).text(), 'Stored generated')
        self.assertEqual(len(browser.page.rows), 100)
        self.assertEqual(browser.page.rows[0]['id'], 1)
        self.assertTrue(browser.page.has_more)
        browser.rows_view.setColumnWidth(0, 133)
        browser.next_page()
        self.wait_idle(browser)
        self.assertEqual(browser.rows_view.columnWidth(0), 133)
        self.assertEqual(browser.page.offset, 100)
        self.assertEqual(browser.page.rows[0]['id'], 101)
        browser.previous_page()
        self.wait_idle(browser)
        self.assertEqual(browser.page.rows[0]['id'], 1)
        select(browser.filter_column, 'category')
        select(browser.filter_operator, 'eq')
        browser.filter_value.setText('even')
        select(browser.sort_column, 'id')
        select(browser.sort_direction, True)
        browser.apply_query()
        self.wait_idle(browser)
        self.assertEqual(browser.page.rows[0]['id'], 250)
        browser.next_page()
        self.wait_idle(browser)
        self.assertEqual(len(browser.page.rows), 25)
        self.assertEqual(browser.page.rows[-1]['id'], 2)
        self.assertFalse(browser.page.has_more)

    def test_row_editor_uses_explicit_types_defaults_and_transactional_save(self):
        browser = self.open_browser(writable=True)
        self.switch_table(browser, 'records')
        self.assertFalse(browser.editing)
        self.assertFalse(browser.stage_insert({'id': 300}))
        self.enable_edits(browser)
        browser.rows_view.selectRow(0)
        browser.edit_button.click()
        editor = browser._row_editor
        fields = {name: (kind, value) for name, kind, value in editor._fields}
        self.assertNotIn('derived', fields)
        select(fields['body'][0], 'null')
        select(fields['extra'][0], 'blob')
        fields['extra'][1].setText('not hex')
        editor.accept()
        self.assertFalse(browser.dirty)
        self.assertIn('hexadecimal', editor.status.text())
        fields['extra'][1].setText('AB CD')
        editor.accept()
        self.assertTrue(browser.dirty)
        self.assertEqual(browser._rows.index(0, 2).data(), 'NULL')
        self.assertTrue(browser.stage_update(0, {'body': 'NULL'}))
        self.assertEqual(browser._rows.index(0, 2).data(), "'NULL'")
        browser.insert_button.click()
        editor = browser._row_editor
        fields = {name: (kind, value) for name, kind, value in editor._fields}
        select(fields['id'][0], 'integer')
        fields['id'][1].setText('300')
        select(fields['body'][0], 'text')
        fields['body'][1].setText('new\r\ntext')
        editor.accept()
        self.assertTrue(browser.stage_delete(1))
        self.assertEqual(self.rows('SELECT body FROM records WHERE id = 1'), [('row 1',)])
        self.assertFalse(browser.next_button.isEnabled())
        self.assertFalse(browser.table_selector.isEnabled())
        self.assertFalse(browser.refresh_button.isEnabled())
        self.assertFalse(browser.apply_button.isEnabled())
        browser.next_page()
        browser.refresh()
        self.assertFalse(browser.busy)
        self.assertEqual(browser.page.offset, 0)
        saved = []
        browser.saved.connect(lambda: saved.append(True))
        browser.save()
        self.wait_idle(browser)
        self.assertEqual(saved, [True])
        self.assertFalse(browser.dirty)
        self.assertEqual(browser.status.text(), 'Changes saved.')
        self.assertEqual(self.rows('SELECT id, category, body, extra FROM records WHERE id IN (1,2,300)'),
                         [(1, 'odd', 'NULL', b'\xab\xcd'), (300, 'even', 'new\r\ntext', None)])

    def test_save_reapplies_query_and_keeps_controls_aligned(self):
        browser = self.open_browser(writable=True)
        self.switch_table(browser, 'records')
        select(browser.filter_column, 'category')
        browser.filter_value.setText('even')
        select(browser.sort_column, 'id')
        select(browser.sort_direction, True)
        browser.apply_query()
        self.wait_idle(browser)
        self.enable_edits(browser)
        browser.rows_view.setColumnWidth(0, 133)
        self.assertTrue(browser.stage_update(0, {'body': 'changed'}))
        browser.save()
        self.wait_idle(browser)
        self.assertEqual(browser.filter_column.currentData(), 'category')
        self.assertEqual(browser.filter_value.text(), 'even')
        self.assertEqual(browser.sort_column.currentData(), 'id')
        self.assertIs(browser.sort_direction.currentData(), True)
        self.assertEqual(browser.page.rows[0]['body'], 'changed')
        self.assertEqual(browser.rows_view.columnWidth(0), 133)
        browser.next_page()
        self.wait_idle(browser)
        self.assertEqual(browser.page.rows[0]['id'], 50)

    def test_write_failure_rolls_back_and_keeps_the_staged_batch(self):
        browser = self.open_browser(writable=True)
        self.switch_table(browser, 'records')
        self.enable_edits(browser)
        self.assertTrue(browser.stage_update(0, {'body': 'first change'}))
        self.assertTrue(browser.stage_update(1, {'body': 'row 3'}))
        browser.save()
        self.wait_idle(browser)
        self.assertIn('UNIQUE constraint failed', browser.status.text())
        self.assertTrue(browser.dirty)
        self.assertTrue(browser.save_button.isEnabled())
        self.assertEqual(browser._rows.index(0, 2).data(), "'first change'")
        self.assertEqual(self.rows('SELECT body FROM records WHERE id IN (1,2)'), [('row 1',), ('row 2',)])
        browser.discard()
        self.assertFalse(browser.dirty)
        self.assertTrue(browser.next_button.isEnabled())

    def test_write_and_read_access_are_rechecked_on_worker(self):
        main = get_ident()
        calls = []
        allowed = {False: True, True: False}

        def check(*, writable=False):
            calls.append((writable, get_ident()))
            if not allowed[writable]:
                raise PermissionError('Access denied by the test host.')

        browser = self.open_browser(writable=True, access_check=check)
        self.switch_table(browser, 'records')
        self.assertFalse(browser.editing_button.isEnabled())
        self.assertIn('Access denied', browser.mode.text())
        allowed[True] = True
        browser.refresh()
        self.wait_idle(browser)
        self.enable_edits(browser)
        self.assertTrue(browser.stage_update(0, {'body': 'attempted change'}))
        allowed[True] = False
        browser.save()
        self.wait_idle(browser)
        self.assertTrue(browser.dirty)
        self.assertIn('Access denied', browser.status.text())
        self.assertEqual(self.rows('SELECT body FROM records WHERE id = 1'), [('row 1',)])
        browser.discard()
        allowed[False] = False
        browser.next_page()
        self.wait_idle(browser)
        self.assertIn('Access denied', browser.status.text())
        self.assertEqual(browser.page.offset, 0)
        self.assertGreaterEqual(sum(writable for writable, _ in calls), 4)
        self.assertTrue(all(thread != main for _, thread in calls))

    def test_commit_is_reported_separately_from_reload_failure(self):
        reads_allowed = True

        def check(*, writable=False):
            return writable or reads_allowed

        browser = self.open_browser(writable=True, access_check=check)
        self.switch_table(browser, 'records')
        self.enable_edits(browser)
        self.assertTrue(browser.stage_update(0, {'body': 'saved'}))
        reads_allowed = False
        browser.save()
        self.wait_idle(browser)
        self.assertIn('Changes saved. Reload failed.', browser.status.text())
        self.assertFalse(browser.dirty)
        self.assertIsNone(browser.page)
        self.assertEqual(self.rows('SELECT body FROM records WHERE id = 1'), [('saved',)])

    def test_view_unkeyed_and_null_key_rows_cannot_be_edited(self):
        browser = self.open_browser(writable=True)
        self.assertEqual(browser.table.name, 'nullable')
        self.enable_edits(browser)
        self.assertIsNone(browser.page.rows[0].token)
        self.assertFalse(browser.stage_update(0, {'label': 'change'}))
        self.assertFalse(browser.stage_delete(0))
        for name in ('visible', 'unkeyed'):
            self.switch_table(browser, name)
            self.assertFalse(browser.editing_button.isEnabled())
            self.assertFalse(browser.insert_button.isEnabled())
            self.assertIsNone(browser.page.rows[0].token)
            self.assertFalse(browser.stage_update(0, {}))

    def test_close_cancel_does_not_reprompt_until_fresh_close(self):
        browser = self.open_browser(writable=True)
        self.switch_table(browser, 'records')
        self.enable_edits(browser)
        self.assertTrue(browser.stage_delete(0))
        buttons = qt.QMessageBox.StandardButton
        with patch.object(qt.QMessageBox, 'question', return_value=buttons.Cancel) as question:
            self.assertFalse(browser.close())
            self.assertFalse(browser.prepare_close())
            question.assert_called_once()
        self.assertFalse(browser.can_retire)
        self.assertFalse(browser.close_pending)
        self.assertTrue(browser.dirty)
        with patch.object(qt.QMessageBox, 'question', return_value=buttons.Discard) as question:
            self.assertTrue(browser.close())
            question.assert_called_once()
        self.assertEqual(self.rows('SELECT body FROM records WHERE id = 1'), [('row 1',)])

    def test_close_save_waits_for_commit_and_worker_retirement(self):
        browser = self.open_browser(writable=True)
        self.switch_table(browser, 'records')
        self.enable_edits(browser)
        self.assertTrue(browser.stage_delete(0))
        saved = []
        browser.saved.connect(lambda: saved.append(not browser.operation._worker.thread.isRunning()))
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Save):
            self.assertFalse(browser.close())
            self.assertTrue(browser.close_pending)
        self.wait_until(lambda: not isValid(browser), drain_deferred=True)
        self.assertEqual(saved, [True])
        self.assertEqual(self.rows('SELECT body FROM records WHERE id = 1'), [])

    def test_failed_save_on_close_keeps_window_and_dirty_state(self):
        browser = self.open_browser(writable=True)
        self.switch_table(browser, 'records')
        self.enable_edits(browser)
        self.assertTrue(browser.stage_update(0, {'body': 'row 2'}))
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Save) as question:
            self.assertFalse(browser.close())
            self.wait_idle(browser)
            self.assertFalse(browser.prepare_close())
            question.assert_called_once()
        self.assertTrue(browser.isVisible())
        self.assertTrue(browser.dirty)
        self.assertFalse(browser.close_pending)
        self.assertIn('UNIQUE constraint failed', browser.status.text())

    def test_close_of_clean_query_waits_while_events_remain_responsive(self):
        waiting, release = Event(), Event()
        delay = False

        def check(*, writable=False):
            if delay:
                waiting.set()
                release.wait(2)

        browser = self.open_browser(access_check=check)
        self.switch_table(browser, 'records')
        delay = True
        self.addCleanup(release.set)
        idle = []
        heartbeat = []
        browser.idle.connect(lambda: idle.append(not browser.operation._worker.thread.isRunning()))
        browser.next_page()
        self.wait_until(waiting.is_set)
        self.assertFalse(browser.close())
        self.assertTrue(browser.close_pending)
        qt.QTimer.singleShot(0, lambda: heartbeat.append(browser.busy))
        self.wait_until(lambda: bool(heartbeat))
        self.assertEqual(heartbeat, [True])
        self.assertTrue(browser.isVisible())
        release.set()
        self.wait_until(lambda: not isValid(browser), drain_deferred=True)
        self.assertEqual(idle, [True])

    def test_save_cancellation_rolls_back_after_first_mutation(self):
        browser = self.open_browser(writable=True)
        self.switch_table(browser, 'records')
        self.enable_edits(browser)
        self.assertTrue(browser.stage_update(0, {'body': 'first change'}))
        self.assertTrue(browser.stage_update(1, {'body': 'second change'}))
        changed, release = Event(), Event()
        self.addCleanup(release.set)
        update = Transaction.update

        def pause_after_change(transaction, token, changes):
            update(transaction, token, changes)
            changed.set()
            release.wait(2)

        with patch.object(Transaction, 'update', pause_after_change):
            browser.save()
            try:
                self.wait_until(changed.is_set)
                self.assertEqual(self.rows('SELECT body FROM records WHERE id = 1'), [('row 1',)])
                browser.operation.request_cancel()
            finally:
                release.set()
            self.wait_idle(browser)
        self.assertTrue(browser.dirty)
        self.assertEqual(browser.status.text(), 'Cancelled. Staged changes were kept.')
        self.assertEqual(self.rows('SELECT body FROM records WHERE id IN (1,2)'), [('row 1',), ('row 2',)])


if __name__ == '__main__':
    unittest.main()
