"""Measure real Qt SQLite work in a caller-owned disposable workspace.

Retain JSON and a widget capture outside that workspace. This is a host event-loop
measurement, not native interaction or an OS-level memory measurement.
"""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

import argparse
from contextlib import closing
import json
from pathlib import Path
import platform
import sqlite3
import time

from commonUtils.ui import pyside as qt
from PySide6.QtTest import QTest
from shiboken6 import isValid
from commonUtils.tests.integrations.sqlite_benchmark import create_fixture
from commonUtils.ui.sqlite_browser.window import SQLiteBrowser


def run(workspace, output, *, rows):
    database = workspace / 'sqlite-ui.db'
    if database.exists():
        raise ValueError('Refusing an existing fixture database.')
    create_fixture(database, rows)
    app = qt.QApplication.instance() or qt.QApplication([])
    app.setFont(qt.QFont('Helvetica', 10))
    beats = []
    timer = qt.QTimer()
    timer.setInterval(5)
    timer.timeout.connect(lambda: beats.append(time.perf_counter()))
    timer.start()
    measurements = {}
    editor = None

    def measure(name, start):
        beats.clear()
        begin = time.perf_counter()
        start()
        while editor.busy:
            if time.perf_counter() - begin > 30:
                raise TimeoutError(f'{name}: worker did not retire')
            app.processEvents()
            QTest.qWait(1)
            time.sleep(.001)
        end = time.perf_counter()
        if editor.page is None:
            raise AssertionError(editor.status.text())
        points = [begin, *beats, end]
        measurements[name] = dict(elapsed_ms=round((end - begin) * 1000, 3),
            heartbeat_count=len(beats), max_event_gap_ms=round(max(b-a for a, b in zip(points, points[1:])) * 1000, 3),
            displayed_rows=len(editor.page.rows))

    try:
        started = time.perf_counter()
        editor = SQLiteBrowser(database, writable=True)
        editor.show()
        measure('initial_schema_and_page', lambda: None)
        measurements['initial_schema_and_page']['construction_to_visible_ms'] = round((time.perf_counter()-started)*1000, 3)
        editor.sort_column.setCurrentIndex(editor.sort_column.findData('name'))
        editor.sort_direction.setCurrentIndex(editor.sort_direction.findData(True))
        measure('unindexed_descending_sort_page', editor.apply_query)
        assert editor.page.rows[0]['id'] == rows
        measure('next_unindexed_page', editor.next_page)
        measure('enable_editing', editor.enable_editing)
        assert editor.editing, editor.status.text()
        identity = editor.page.rows[0]['id']
        assert editor.stage_update(0, {'score': 123.5})
        measure('save_and_reload', editor.save)
        assert not editor.dirty, editor.status.text()
        with closing(sqlite3.connect(database)) as db:
            assert db.execute('SELECT score FROM records WHERE id=?', (identity,)).fetchone() == (123.5,)
            plan = list(db.execute('EXPLAIN QUERY PLAN SELECT * FROM records ORDER BY name DESC,id LIMIT 101'))
        output.parent.mkdir(parents=True, exist_ok=True)
        screenshot = output.with_suffix('.png')
        app.processEvents()
        if not editor.grab().save(str(screenshot)):
            raise RuntimeError('Cannot save SQLite browser capture.')
        result = dict(python=platform.python_version(), sqlite=sqlite3.sqlite_version,
            qt=qt.qVersion() if hasattr(qt, 'qVersion') else 'PySide6', platform=platform.platform(),
            backend=app.platformName(), rows=rows, timer_interval_ms=5, measurements=measurements,
            query_plan=plan, saved_value_survives_reopen=True,
            scope='Real SQLite worker jobs and Qt heartbeat on disposable host fixtures. '
                  'No simulated delay, native user interaction or process RSS measurement.')
        output.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
    finally:
        timer.stop()
        if editor is not None and isValid(editor):
            editor.operation.request_cancel()
            deadline = time.monotonic() + 30
            while editor.busy and time.monotonic() < deadline:
                app.processEvents()
                QTest.qWait(1)
                time.sleep(.001)
            if editor.busy:
                raise RuntimeError('SQLite UI worker did not retire before fixture cleanup.')
            editor.discard()
            editor.close()
            app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rows', type=int, default=250000)
    args = parser.parse_args()
    if not args.workspace.is_dir() or args.rows < 1000:
        parser.error('Supply an existing disposable workspace and at least 1000 rows.')
    run(args.workspace, args.output, rows=args.rows)


if __name__ == '__main__':
    main()
