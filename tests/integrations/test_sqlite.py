"""Real SQLite fixtures for the headless resource and legacy wrapper contracts."""

from contextlib import closing
from dataclasses import FrozenInstanceError
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from commonUtils.integrations.sqlite import (
    All, Any, BusyError, CancelledError, ConstraintError, Database, Filter, ReadOnlyError,
    Sort, SQLiteError, StaleDataError, ValidationError, parse_value,
)
from commonUtils.integrations.wrappers.sqlWrapper import exec_sql_command, fetch_sql_table
from commonUtils.testing.stages import TestStage


TEST_STAGE = TestStage.REGRESSION


class SQLiteTest(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        # Keep reserved URI characters on every platform. Windows forbids '?' in filenames.
        filename = 'sample #% &.db' if os.name == 'nt' else 'sample ?#% &.db'
        self.path = Path(temporary.name) / filename

    def fixture(self, sql):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.executescript(sql)

    def execute(self, sql, parameters=()):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            return connection.execute(sql, parameters).fetchall()

    def test_existing_file_only_and_permission_error(self):
        for writable in (False, True):
            with self.subTest(writable=writable), self.assertRaises(SQLiteError):
                with Database(self.path, writable=writable):
                    self.fail('A missing file was opened.')
        self.assertFalse(self.path.exists())
        self.path.write_bytes(b'invalid data')
        with self.assertRaises(SQLiteError) as caught:
            with Database(self.path):
                self.fail('An invalid database was opened.')
        self.assertIsInstance(caught.exception.__cause__, sqlite3.DatabaseError)
        self.path.unlink()
        self.fixture('CREATE TABLE t(id INTEGER PRIMARY KEY)')
        with Database(self.path) as db:
            with self.assertRaises(ReadOnlyError):
                with db.transaction():
                    self.fail('The read-only handle started a write transaction.')
        self.path.chmod(0o444)
        try:
            with self.assertRaisesRegex(ReadOnlyError, 'writable copy'):
                with Database(self.path, writable=True):
                    self.fail('An explicitly read-only file was opened for writes.')
        finally:
            self.path.chmod(0o644)

    def test_table_metadata_projection_composed_filters_sort_and_bounds(self):
        self.fixture("""
            CREATE TABLE "data"" table" (
                id INTEGER PRIMARY KEY, label TEXT NOT NULL DEFAULT 'new',
                score REAL, payload BLOB, calc AS (score + 1) STORED
            );
            INSERT INTO "data"" table" (id, label, score, payload) VALUES
                (1, 'a%_tag', 5, X'0001'), (2, 'a%_Tag', 3, X'FF'),
                (3, 'a%_tag', 5, NULL), (4, 'xyz', 2, NULL), (5, 'nil', NULL, X'');
            CREATE VIEW "data view" AS SELECT id, label FROM "data"" table";
        """)
        name = 'data" table'
        with Database(self.path) as db:
            tables = {item.name: item for item in db.tables()}
            table, view = tables[name], tables['data view']
            self.assertEqual(table, db.table(name))
            self.assertEqual(table.primary_key, ('id',))
            self.assertEqual(table.kind, 'table')
            self.assertTrue(table.editable)
            self.assertEqual(table.columns[1].declared_type, 'TEXT')
            self.assertTrue(table.columns[1].not_null)
            self.assertEqual(table.columns[1].default, "'new'")
            self.assertEqual(table.columns[4].hidden, 3)
            self.assertEqual(view.kind, 'view')
            self.assertFalse(view.editable)
            self.assertIsNone(db.page(view).rows[0].token)
            predicates = All(
                Filter('label', 'starts_with', 'a%_'),
                Any(Filter('label', 'contains', 'tag'), Filter('score', 'lt', 4)),
                Filter('score', 'not_null'),
            )
            sort = (Sort('score', descending=True),)
            first = db.page(table, ('id', 'label'), predicates, sort, limit=2)
            self.assertEqual(first.columns, ('id', 'label'))
            self.assertEqual(first.limit, 2)
            self.assertEqual(first.offset, 0)
            self.assertEqual([row['id'] for row in first.rows], [1, 3])
            self.assertTrue(first.has_more)
            self.assertEqual(first.rows[0].values, (1, 'a%_tag'))
            self.assertEqual(first.rows[0].token.original, (1, 'a%_tag', 5.0, b'\x00\x01', 6.0))
            with self.assertRaises(KeyError):
                first.rows[0]['score']
            with self.assertRaises(FrozenInstanceError):
                first.rows[0].values = ()
            last = db.page(table, ('id', 'label'), predicates, sort, limit=2, offset=2)
            self.assertEqual(last.offset, 2)
            self.assertEqual([row['id'] for row in last.rows], [2])
            self.assertFalse(last.has_more)
            self.assertEqual([row['id'] for row in db.page(table, filters=Filter('score', 'is_null')).rows],
                             [5])
            self.assertEqual(len(db.page(table, filters=All()).rows), 5)
            self.assertEqual(db.page(table, filters=Any()).rows, ())
            for limit, offset in ((0, 0), (1001, 0), (True, 0), (1, -1), (1, 2**63)):
                with self.subTest(limit=limit, offset=offset), self.assertRaises(ValidationError):
                    db.page(table, limit=limit, offset=offset)
            for value, operator in ((True, 'eq'), (None, 'ne'), (0, 'is_null'), ('1', 'injection')):
                with self.subTest(value=value, operator=operator), self.assertRaises(ValidationError):
                    db.page(table, filters=Filter('score', operator, value))

    def test_read_only_fallback_sort_breaks_ties_by_visible_values(self):
        self.fixture("""
            CREATE TABLE t(rowid TEXT COLLATE NOCASE, _rowid_ TEXT, oid INTEGER);
            INSERT INTO t VALUES ('beta', 'c', 1), ('alpha', 'b', 1), ('Alpha', 'a', 1);
            CREATE VIEW v AS SELECT oid AS group_id, rowid AS name FROM t;
        """)
        with Database(self.path) as db:
            self.assertEqual([row['rowid'] for row in db.page('t').rows], ['Alpha', 'alpha', 'beta'])
            first = db.page('v', ('name',), sort=(Sort('group_id', True),), limit=2)
            second = db.page('v', ('name',), sort=(Sort('group_id', True),), limit=2, offset=2)
            self.assertEqual([row['name'] for row in first.rows], ['Alpha', 'alpha'])
            self.assertEqual([row['name'] for row in second.rows], ['beta'])

    def test_bound_values_and_quoted_identifiers(self):
        self.fixture("""
            CREATE TABLE "t; --" ("id" INTEGER PRIMARY KEY, "v""; --" TEXT);
            INSERT INTO "t; --" VALUES (1, 'x'' OR 1 = 1 --'), (2, 'other');
        """)
        name, column, value = 't; --', 'v"; --', "x' OR 1 = 1 --"
        with Database(self.path, writable=True) as db:
            table = db.table(name)
            page = db.page(table, (column,), filters=Filter(column, 'eq', value))
            self.assertEqual(page.rows[0][column], value)
            self.assertEqual(len(page.rows), 1)
            with db.transaction() as tx:
                tx.update(page.rows[0].token, {column: 'updated'})
            for target, fields, filters, sort in (
                (name + '"', (column,), None, ()),
                (name, (column + '"',), None, ()),
                (name, (column,), Filter(column + '"', 'eq', 1), ()),
                (name, (column,), None, (Sort(column + '"'),)),
            ):
                with self.assertRaises(ValidationError):
                    db.page(target, fields, filters=filters, sort=sort)
            self.assertEqual(db.page(table).rows[0][column], 'updated')

    def test_raw_query_sqlite_parsing_authorizer_and_restoration(self):
        self.fixture('CREATE TABLE t(id INTEGER PRIMARY KEY); INSERT INTO t VALUES (1),(2),(3)')
        with Database(self.path, writable=True) as db:
            table = db.table('t')
            result = db.query("""
                -- SELECT must remain available to CTEs and bindings.
                WITH RECURSIVE n(i) AS (VALUES (:low) UNION ALL SELECT i+1 FROM n WHERE i<4)
                SELECT i AS value, 'literal; semicolon' AS value FROM n;
            """, {'low': 2}, limit=2)
            self.assertEqual(result.columns, ('value', 'value'))
            self.assertEqual(result.rows[0]['value'], 2)
            self.assertEqual(result.rows[0].values, (2, 'literal; semicolon'))
            self.assertEqual(result.offset, 0)
            self.assertTrue(result.has_more)
            self.assertIsNone(result.rows[0].token)
            self.assertFalse(db.query('SELECT id FROM t WHERE id = ?', (1,), limit=1).has_more)
            denied = (
                'INSERT INTO t VALUES (10) RETURNING id',
                'WITH x(v) AS (VALUES (2)) DELETE FROM t WHERE id IN x RETURNING id',
                'UPDATE t SET id=10 WHERE id=1 RETURNING id',
                'CREATE TEMP TABLE bad (id)',
                'EXPLAIN DELETE FROM t',
                'ATTACH DATABASE ":memory:" AS another',
                'PRAGMA user_version=93',
                "SELECT * FROM pragma_table_info('t')",
                'ROLLBACK', 'COMMIT', 'END', 'BEGIN', 'SAVEPOINT x',
            )
            with db.transaction() as tx:
                tx.insert(table, {'id': 4}, schema_token=table.schema_token)
                for statement in denied:
                    with self.subTest(statement=statement), self.assertRaises(ReadOnlyError):
                        db.query(statement)
                with self.assertRaises(SQLiteError):
                    db.query('SELECT load_extension("test")')
                with self.assertRaises(ValidationError):
                    db.query('SELECT 1; SELECT 2')
                with self.assertRaises(ValidationError):
                    db.query('-- comments only')
                self.assertEqual(db.query('SELECT count(*) FROM t').rows[0].values, (4,))
            self.assertEqual(db.page('t').rows[-1]['id'], 4)
        self.assertEqual(self.execute('PRAGMA user_version'), [(0,)])

    def test_primary_keys_null_unkeyed_virtual_and_shadow_tables(self):
        self.fixture("""
            CREATE TABLE composite (a TEXT, b INTEGER, payload,
                PRIMARY KEY(a COLLATE NOCASE, b DESC)) WITHOUT ROWID;
            INSERT INTO composite VALUES ('z', 1, 'z'), ('A', 1, 'a1'), ('A', 2, 'a2');
            CREATE TABLE nullable (key TEXT PRIMARY KEY, value TEXT);
            INSERT INTO nullable VALUES (NULL, 'first'), (NULL, 'second'), ('a', 'third');
            CREATE TABLE unkeyed (rowid, v);
            INSERT INTO unkeyed VALUES (NULL, 'first'), (NULL, 'second');
            CREATE TABLE generated (id INTEGER PRIMARY KEY AUTOINCREMENT, doubled AS (id*2));
            CREATE VIEW noedit AS SELECT * FROM composite;
        """)
        with Database(self.path, writable=True) as db:
            table = db.table('composite')
            self.assertEqual(table.primary_key, ('a', 'b'))
            rows = db.page(table).rows
            self.assertEqual([row.values[:2] for row in rows], [('A', 2), ('A', 1), ('z', 1)])
            nullable = db.table('nullable')
            rows_with_null = db.page(nullable).rows
            self.assertEqual([row['value'] for row in rows_with_null], ['first', 'second', 'third'])
            self.assertEqual([row.token is None for row in rows_with_null], [True, True, False])
            with self.assertRaises(ReadOnlyError):
                with db.transaction() as tx:
                    tx.delete(rows_with_null[0].token)
            with db.transaction() as tx:
                tx.update(rows[0].token, {'a': 'renamed', 'b': 3})
                tx.insert(nullable, {'value': 'fourth'}, schema_token=nullable.schema_token)
            self.assertEqual(db.page(table).rows[1].values, ('renamed', 3, 'a2'))
            self.assertIsNone(db.page(nullable).rows[2].token)
            no_key = db.table('unkeyed')
            self.assertEqual([row['v'] for row in db.page(no_key).rows], ['first', 'second'])
            self.assertIsNone(db.page(no_key).rows[0].token)
            for name in ('unkeyed', 'noedit', 'sqlite_sequence'):
                table = db.table(name)
                self.assertFalse(table.editable)
                self.assertTrue(table.read_only_reason)
                with self.subTest(name=name), self.assertRaises(ReadOnlyError):
                    with db.transaction() as tx:
                        tx.insert(table, {}, schema_token=table.schema_token)
        try:
            self.fixture("CREATE VIRTUAL TABLE search USING fts5(body); INSERT INTO search VALUES ('word')")
        except sqlite3.OperationalError as error:
            if 'no such module' not in str(error):
                raise
        else:
            with Database(self.path) as db:
                virtual = db.table('search')
                self.assertEqual(virtual.kind, 'virtual')
                self.assertFalse(virtual.editable)
                self.assertEqual(db.page(virtual).columns, ('body',))
                self.assertIsNone(db.page(virtual).rows[0].token)
                shadow = db.table('search_content')
                self.assertEqual(shadow.kind, 'shadow')
                self.assertFalse(shadow.editable)
                self.assertIsNone(db.page(shadow).rows[0].token)

    def test_write_round_trip_with_affinity_defaults_and_triggers(self):
        self.fixture("""
            CREATE TABLE t (id INTEGER PRIMARY KEY, label TEXT DEFAULT 'new',
                payload BLOB, computed TEXT AS (upper(label)) STORED);
            CREATE TABLE audit (label TEXT);
            CREATE TRIGGER t_log AFTER UPDATE ON t BEGIN INSERT INTO audit VALUES (new.label); END;
        """)
        with Database(self.path, writable=True) as db:
            table = db.table('t')
            with db.transaction() as tx:
                tx.insert(table, {}, schema_token=table.schema_token)
                tx.insert('t', {'label': None, 'payload': b''}, schema_token=table.schema_token)
            first, second = db.page(table, ('label',)).rows
            self.assertEqual(first.values, ('new',))
            self.assertEqual(first.token.original, (1, 'new', None, 'NEW'))
            with db.transaction() as tx:
                tx.update(first.token, {'id': 7, 'label': 123, 'payload': b'\x80'})
                tx.delete(second.token)
            with self.assertRaises(ValidationError):
                tx.delete(first.token)
        with Database(self.path) as db:
            self.assertEqual(db.page('t').rows[0].values, (7, '123', b'\x80', '123'))
            self.assertEqual(db.page('audit').rows[0].values, ('123',))

    def test_caught_mutation_error_dooms_whole_batch(self):
        self.fixture("""
            CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT UNIQUE);
            INSERT INTO t VALUES(1, 'original');
        """)
        with Database(self.path, writable=True) as db:
            table = db.table('t')
            with self.assertRaises(ConstraintError) as failed:
                with db.transaction() as tx:
                    tx.insert(table, {'v': 'temporary'}, schema_token=table.schema_token)
                    with self.assertRaises(ConstraintError):
                        tx.insert(table, {'v': 'original'}, schema_token=table.schema_token)
                    with self.assertRaises(ValidationError):
                        tx.insert(table, {}, schema_token=table.schema_token)
            self.assertIsInstance(failed.exception.__cause__, sqlite3.IntegrityError)
            self.assertEqual([row.values for row in db.page(table).rows], [(1, 'original')])

    def test_commit_constraint_and_trigger_rollback(self):
        self.fixture("""
            CREATE TABLE parent(id INTEGER PRIMARY KEY);
            CREATE TABLE child(id INTEGER PRIMARY KEY,
                parent INTEGER REFERENCES parent(id) DEFERRABLE INITIALLY DEFERRED);
            CREATE TABLE t(id INTEGER PRIMARY KEY, name TEXT UNIQUE ON CONFLICT IGNORE);
            CREATE TRIGGER roll_back BEFORE INSERT ON t WHEN new.name='rollback'
                BEGIN SELECT RAISE(ROLLBACK, 'rejected'); END;
        """)
        with Database(self.path, writable=True) as db:
            parent, child, table = (db.table(name) for name in ('parent', 'child', 't'))
            with self.assertRaises(ConstraintError):
                with db.transaction() as tx:
                    tx.insert(parent, {'id': 1}, schema_token=parent.schema_token)
                    tx.insert(child, {'parent': 999}, schema_token=child.schema_token)
            self.assertEqual(db.page(parent).rows, ())
            self.assertEqual(db.page(child).rows, ())
            for invalid in ('duplicate', 'rollback'):
                with self.subTest(invalid=invalid), self.assertRaises(ConstraintError):
                    with db.transaction() as tx:
                        tx.insert(table, {'name': 'duplicate'}, schema_token=table.schema_token)
                        tx.insert(table, {'name': invalid}, schema_token=table.schema_token)
                self.assertEqual(db.page(table).rows, ())

    def test_conflict_replace_cannot_delete_rows_or_substitute_defaults(self):
        self.fixture("""
            CREATE TABLE t (
                id INTEGER PRIMARY KEY, label TEXT UNIQUE ON CONFLICT REPLACE,
                required TEXT NOT NULL ON CONFLICT REPLACE DEFAULT 'default'
            );
            CREATE TABLE audit (label TEXT UNIQUE, prior TEXT);
            INSERT INTO audit VALUES ('logged', 'original');
            CREATE TRIGGER log AFTER INSERT ON t WHEN new.label = 'logged'
                BEGIN INSERT OR REPLACE INTO audit VALUES (new.label, 'replacement'); END;
            INSERT INTO t (id, label, required) VALUES (1, 'a', 'one'), (2, 'b', 'two');
        """)
        with Database(self.path, writable=True) as db:
            table = db.table('t')
            row = db.page(table).rows[0]
            for write in (
                lambda tx: tx.insert(table, {'label': 'a'}, schema_token=table.schema_token),
                lambda tx: tx.insert(table, {'label': 'logged'}, schema_token=table.schema_token),
                lambda tx: tx.update(row.token, {'label': 'b'}),
                lambda tx: tx.update(row.token, {'required': None}),
            ):
                with self.assertRaises(ConstraintError):
                    with db.transaction() as tx:
                        tx.insert(table, {'label': 'temporary'}, schema_token=table.schema_token)
                        write(tx)
            self.assertEqual(self.execute('SELECT * FROM t ORDER BY id'),
                             [(1, 'a', 'one'), (2, 'b', 'two')])
            self.assertEqual(self.execute('SELECT * FROM audit'), [('logged', 'original')])

    def test_base_exception_close_and_nested_contexts(self):
        self.fixture('CREATE TABLE t(id INTEGER PRIMARY KEY)')
        class Stop(BaseException):
            pass

        with Database(self.path, writable=True) as db:
            table = db.table('t')
            with self.assertRaises(Stop):
                with db.transaction() as tx:
                    tx.insert(table, {}, schema_token=table.schema_token)
                    with self.assertRaises(ValidationError):
                        with db.transaction():
                            self.fail('A nested write transaction was allowed.')
                    raise Stop
            self.assertEqual(db.page(table).rows, ())
            with self.assertRaises(ValidationError):
                with db.transaction() as tx:
                    tx.insert(table, {}, schema_token=table.schema_token)
                    db.close()
        self.assertEqual(self.execute('SELECT * FROM t'), [])

    def test_stale_full_row_storage_type_schema_file_and_primary_key(self):
        self.fixture("""
            CREATE TABLE t(k TEXT, data, label TEXT, PRIMARY KEY(k COLLATE NOCASE));
            INSERT INTO t VALUES ('A', 1, 'original');
        """)
        with Database(self.path) as db:
            table = db.table('t')
            row = db.page(table, ('label',)).rows[0]
        self.execute('UPDATE t SET data = CAST(data AS REAL)')
        with Database(self.path, writable=True) as db:
            with self.assertRaises(StaleDataError):
                with db.transaction() as tx:
                    tx.update(row.token, {'label': 'new'})
            self.assertEqual(db.page(table).rows[0].values, ('A', 1.0, 'original'))
            changed = db.page(table, ('label',)).rows[0]
        self.execute("UPDATE t SET k = 'a'")
        with Database(self.path, writable=True) as db:
            with self.assertRaises(StaleDataError):
                with db.transaction() as tx:
                    tx.delete(changed.token)
            changed = db.page(table, ('label',)).rows[0]
        self.fixture('CREATE TRIGGER audit AFTER UPDATE ON t BEGIN SELECT 1; END')
        with Database(self.path, writable=True) as db:
            with self.assertRaises(StaleDataError):
                with db.transaction() as tx:
                    tx.delete(changed.token)
            with self.assertRaises(StaleDataError):
                with db.transaction() as tx:
                    tx.insert(table, {'k': 'b'}, schema_token=table.schema_token)
            current = db.table('t')
            changed = db.page(current).rows[0]
        backup = self.path.with_suffix('.old')
        self.path.rename(backup)
        self.path.write_bytes(backup.read_bytes())
        with Database(self.path, writable=True) as db:
            with self.assertRaises(StaleDataError):
                with db.transaction() as tx:
                    tx.delete(changed.token)
            with self.assertRaises(StaleDataError):
                with db.transaction() as tx:
                    tx.insert('t', {'k': 'b'}, schema_token=current.schema_token)

    def test_stale_file_replacement_during_transaction(self):
        self.fixture("CREATE TABLE t (id INTEGER PRIMARY KEY, v); INSERT INTO t VALUES (1, 'original')")
        backup = self.path.with_suffix('.old')
        copy = self.path.with_suffix('.new')
        copy.write_bytes(self.path.read_bytes())
        with Database(self.path, writable=True) as db:
            row = db.page('t').rows[0]
            with self.assertRaises(StaleDataError):
                with db.transaction() as tx:
                    tx.update(row.token, {'v': 'new'})
                    try:
                        self.path.rename(backup)
                    except PermissionError:
                        self.skipTest('This filesystem prevents replacing an open SQLite file.')
                    copy.rename(self.path)
        self.assertEqual(self.execute('SELECT v FROM t'), [('original',)])
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual(connection.execute('SELECT v FROM t').fetchone(), ('original',))

    def test_generated_columns_unknown_columns_and_bad_types_abort(self):
        self.fixture('CREATE TABLE t(id INTEGER PRIMARY KEY, g AS (id * 2))')
        with Database(self.path, writable=True) as db:
            table = db.table('t')
            for fields, error in (({'g': 2}, ReadOnlyError), ({'unknown': 2}, ValidationError),
                                  ({'id': True}, ValidationError), ({'id': float('inf')}, ValidationError),
                                  ({'id': 2 ** 63}, ValidationError)):
                with self.subTest(fields=fields), self.assertRaises(error):
                    with db.transaction() as tx:
                        tx.insert(table, fields, schema_token=table.schema_token)
            with db.transaction() as tx:
                tx.insert(table, {}, schema_token=table.schema_token)
            with self.assertRaises(ReadOnlyError):
                with db.transaction() as tx:
                    tx.update(db.page(table).rows[0].token, {'g': 10})

    def test_busy_on_second_writer_and_commit_reader_lock(self):
        self.fixture("CREATE TABLE t(id INTEGER PRIMARY KEY, v); INSERT INTO t VALUES (1, 'original')")
        with Database(self.path, writable=True) as first, Database(
            self.path, writable=True, timeout=0.001,
        ) as second:
            with first.transaction():
                with self.assertRaises(BusyError) as caught:
                    with second.transaction():
                        self.fail('Both SQLite writers entered simultaneous transactions.')
                self.assertIsInstance(caught.exception.__cause__, sqlite3.OperationalError)
            with closing(sqlite3.connect(self.path, isolation_level=None)) as reader:
                reader.execute('BEGIN')
                reader.execute('SELECT * FROM t').fetchall()
                with self.assertRaises(BusyError):
                    with second.transaction() as tx:
                        tx.update(second.page('t').rows[0].token, {'v': 'uncommitted'})
                reader.execute('ROLLBACK')
            self.assertEqual(first.page('t').rows[0]['v'], 'original')

    def test_progress_cancellation_and_cancel_before_commit(self):
        self.fixture('CREATE TABLE t(id INTEGER PRIMARY KEY)')
        calls = 0
        allow_calls = None

        def cancelled():
            nonlocal calls
            calls += 1
            return allow_calls is not None and calls >= allow_calls

        with Database(self.path, writable=True, cancelled=cancelled) as db:
            table = db.table('t')
            allow_calls = calls + 3
            with self.assertRaises(CancelledError) as caught:
                db.query('''
                    WITH RECURSIVE work(n) AS (
                        VALUES(0) UNION ALL SELECT n + 1 FROM work WHERE n < 10000000
                    ) SELECT sum(n) FROM work
                ''')
            self.assertIsInstance(caught.exception.__cause__, sqlite3.OperationalError)
            allow_calls = None
            self.assertEqual(db.query('SELECT 1').rows[0].values, (1,))
            with self.assertRaises(CancelledError):
                with db.transaction() as tx:
                    tx.insert(table, {}, schema_token=table.schema_token)
                    allow_calls = calls + 1
            allow_calls = None
            self.assertEqual(db.page(table).rows, ())

    def test_parse_values(self):
        for kind, text, expected in (
            ('null', ' NULL ', None), ('integer', '-9223372036854775808', -(2**63)),
            ('integer', '+9223372036854775807', 2**63 - 1), ('real', '-.25e+2', -25.0),
            ('text', '  NULL  ', '  NULL  '), ('blob', '00 ff', b'\x00\xff'),
            ('blob', '', b''),
        ):
            with self.subTest(kind=kind, text=text):
                value = parse_value(kind, text)
                self.assertIs(type(value), type(expected))
                self.assertEqual(value, expected)
        for kind, text in (
            ('null', '1'), ('integer', '9223372036854775808'), ('integer', '1.0'),
            ('integer', '1_000'), ('integer', True), ('real', 'inf'), ('real', 'nan'),
            ('real', '1e1000'), ('blob', '0x44'), ('blob', 'A'), ('other', '5'),
        ):
            with self.subTest(kind=kind, text=text), self.assertRaises(ValidationError):
                parse_value(kind, text)

    def test_legacy_wrapper_shapes_default_columns_and_persistence(self):
        self.fixture("""
            CREATE TABLE "t "" named" ("key" INTEGER PRIMARY KEY, "v; --" TEXT);
            INSERT INTO "t "" named" VALUES (1, 'old');
        """)
        name, column = 't " named', 'v; --'
        self.assertEqual(fetch_sql_table(self.path, name), [
            {'row_number': 1, 'key': 1, column: 'old'},
        ])
        self.assertEqual(fetch_sql_table(self.path, name, (column,)), [
            {'row_number': 1, column: 'old'},
        ])
        self.assertEqual(fetch_sql_table(self.path, name.upper(), (column.upper(),)), [
            {'row_number': 1, column.upper(): 'old'},
        ])
        self.assertEqual(exec_sql_command(self.path, 'SELECT 1'), [(1,)])
        self.assertEqual(exec_sql_command(self.path, """UPDATE "t "" named" SET "v; --"='new'"""), [])
        self.assertEqual(fetch_sql_table(self.path, name)[0][column], 'new')
        with self.assertRaises(sqlite3.Error):
            fetch_sql_table(self.path, name, ('*',))
        with self.assertRaises(sqlite3.Error):
            exec_sql_command(self.path, 'SELECT 1; SELECT 2')


if __name__ == '__main__':
    unittest.main()
