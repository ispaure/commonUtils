"""Repeatable disposable SQLite workload; the caller owns fixture/evidence paths.

Run in a consumer's retained scratch workspace, never against application data.
The legacy wrapper has no successful save operation, so committed stdlib writes
are recorded separately as the honest write-performance comparison baseline.
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

from contextlib import closing
import argparse
import gc
import json
from itertools import count
from pathlib import Path
import platform
import sqlite3
import statistics
import time
import tracemalloc

from commonUtils.integrations.wrappers.sqlWrapper import exec_sql_command, fetch_sql_table


COLUMNS = ('id', 'category', 'score', 'name', 'payload')
PAGE_SIZE = 100
SAVE_SERIAL = count(1)


def create_fixture(path, count):
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute('CREATE TABLE records (id INTEGER PRIMARY KEY, category INTEGER NOT NULL, '
                           'score REAL NOT NULL, name TEXT NOT NULL, payload BLOB)')
        connection.executemany('INSERT INTO records VALUES (?, ?, ?, ?, ?)',
                               ((i, i % 20, (i * 17 % 10000) / 100, f'record-{i:09}', bytes([i % 256]) * 64)
                                for i in range(1, count + 1)))
        connection.execute('CREATE INDEX records_category_score ON records(category, score, id)')


def measure(callback, repeats):
    samples = []
    for _ in range(repeats):
        gc.collect()
        start = time.perf_counter()
        result = callback()
        samples.append((time.perf_counter() - start) * 1000)
        del result
    gc.collect()
    tracemalloc.start()
    result = callback()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    del result
    return dict(median_ms=round(statistics.median(samples), 3),
                samples_ms=[round(value, 3) for value in samples],
                python_peak_bytes=peak)


def committed_save(path, count):
    serial = next(SAVE_SERIAL)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.executemany('UPDATE records SET name=? WHERE id=?',
                               ((f'edited-{serial}-{index}', index) for index in range(1, count + 1)))


def benchmark(path, count, repeats):
    create_fixture(path, count)
    first_sql = 'SELECT id, category, score, name, payload FROM records ORDER BY id LIMIT 100'
    filter_sql = ('SELECT id, name, score FROM records WHERE category=7 '
                  'ORDER BY score, id LIMIT 100')
    page = lambda: fetch_sql_table(path, 'records', COLUMNS)[:PAGE_SIZE]
    measurements = {
        'legacy_full_table_to_first_page': measure(page, repeats),
        'legacy_bounded_first_page_sql': measure(lambda: exec_sql_command(path, first_sql), repeats),
        'legacy_bounded_filtered_sorted_sql': measure(lambda: exec_sql_command(path, filter_sql), repeats),
        'stdlib_committed_single_edit': measure(lambda: committed_save(path, 1), repeats),
        'stdlib_committed_batch_100': measure(lambda: committed_save(path, 100), repeats),
    }
    missing_columns_error = None
    try:
        fetch_sql_table(path, 'records')
    except Exception as error:
        missing_columns_error = f'{type(error).__name__}: {error}'
    exec_sql_command(path, "UPDATE records SET name='legacy-save-probe' WHERE id=1")
    with closing(sqlite3.connect(path)) as connection:
        persisted = connection.execute('SELECT name FROM records WHERE id=1').fetchone()[0]
        plan = [list(row) for row in connection.execute('EXPLAIN QUERY PLAN ' + filter_sql)]
    return dict(rows=count, database_bytes=path.stat().st_size, page_size=PAGE_SIZE,
                measurements=measurements, query_plan=plan,
                legacy_default_columns_error=missing_columns_error,
                legacy_write_persisted=persisted == 'legacy-save-probe')


def shared_benchmark(path, count, repeats):
    from commonUtils.integrations.sqlite import Database, Filter, Sort
    create_fixture(path, count)

    def first():
        with Database(path) as db:
            return db.page('records', limit=PAGE_SIZE)

    def filtered():
        with Database(path) as db:
            return db.page('records', columns=('id', 'name', 'score'),
                           filters=Filter('category', 'eq', 7),
                           sort=(Sort('score'), Sort('id')), limit=PAGE_SIZE)

    def save(number):
        serial = next(SAVE_SERIAL)
        # Include reading the typed original rows, opening a writable handle,
        # acquiring a write transaction, validation, mutation and durable commit.
        with Database(path) as db:
            rows = db.page('records', limit=number).rows
        with Database(path, writable=True) as db, db.transaction() as tx:
            for row in rows:
                tx.update(row.token, {'name': f'shared-{serial}-{row["id"]}'})

    measurements = {
        'shared_first_page': measure(first, repeats),
        'shared_filtered_sorted_projected_page': measure(filtered, repeats),
        'shared_committed_single_edit': measure(lambda: save(1), repeats),
        'shared_committed_batch_100': measure(lambda: save(100), repeats),
    }
    with Database(path) as db:
        plan = db.query('EXPLAIN QUERY PLAN SELECT id,name,score FROM records '
                        'WHERE category=? ORDER BY score,id LIMIT 100', (7,))
        # A fresh handle verifies durable commit and bounded public row results.
        reopened = db.page('records', limit=1)
    return dict(rows=count, database_bytes=path.stat().st_size, page_size=PAGE_SIZE,
                measurements=measurements, query_plan=[list(row.values) for row in plan.rows],
                shared_write_persisted=reopened.rows[0]['name'].startswith('shared-'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rows', type=int, nargs='+', default=[1000, 250000])
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--implementation', choices=('legacy', 'shared'), default='legacy')
    args = parser.parse_args()
    if not args.workspace.is_dir():
        parser.error('The caller must supply an existing disposable workspace.')
    if args.repeats < 1 or any(count < 100 for count in args.rows):
        parser.error('Choose positive repeats and fixtures with at least 100 rows.')
    result = dict(python=platform.python_version(), sqlite=sqlite3.sqlite_version,
                  platform=platform.platform(), repeats=args.repeats,
                  measurement='Warm-process wall clock including connection open/close; '
                  'tracemalloc peak includes Python allocations, not SQLite native memory. '
                  'Single-thread local filesystem; no claim of cold-disk or native UI latency.',
                  implementation=args.implementation, fixtures=[])
    for count in args.rows:
        path = args.workspace / f'sqlite-benchmark-{count}.db'
        if path.exists():
            parser.error(f'Refusing existing fixture: {path}')
        runner = shared_benchmark if args.implementation == 'shared' else benchmark
        result['fixtures'].append(runner(path, count, args.repeats))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
