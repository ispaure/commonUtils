# SQLite resource API

Use `commonUtils.integrations.sqlite` to inspect and edit an existing local
SQLite file. It uses the standard-library `sqlite3` module with SQLite 3.37 or
newer for schema introspection. Callers own file selection and policy, worker
scheduling, and presenting errors. The directory index has its own schema,
writer lifecycle and read snapshots. Use its [index API](../filesystem/index/index.md)
for managed data.

## Read a page

```python
from commonUtils.integrations.sqlite import All, Database, Filter, Sort

with Database(path) as db:
    objects = db.tables()
    records = db.table("records")
    page = db.page(
        records,
        columns=("id", "name", "score"),
        filters=All(Filter("category", "eq", 7), Filter("score", "not_null")),
        sort=(Sort("score", descending=True),),
        limit=100,
        offset=0,
    )
    for row in page.rows:
        print(row["name"])
```

`Database` opens only existing regular files and closes its connection when the
context ends. Keep each handle on the thread that opened it. The default is
read-only. `timeout` controls SQLite's lock wait in seconds and defaults to 0.25.
A `cancelled` callable may read a caller-owned cancellation flag. SQLite's
progress handler polls during longer statements, and the API checks cancellation
at operation boundaries.

`tables()` and `table(name)` describe the main schema. `Table.kind` is
`table`, `view`, `virtual`, or `shadow`. Columns report their declared type,
NOT NULL flag, default SQL expression, position in the primary key, and the
SQLite `table_xinfo` hidden code. Code 0 is an ordinary column, 1 is a virtual
table's hidden column, and 2 or 3 is generated. The default page projection
includes ordinary and generated columns. An explicit projection can also request
virtual hidden columns. Use the exact names returned by the API.

`Filter` accepts `eq`, `ne`, `lt`, `le`, `gt`, `ge`, `contains`,
`starts_with`, `is_null` and `not_null`. Text matching is literal and
case-sensitive, so characters such as `%` and `_` match themselves. Use the
explicit null tests with no value. `All(*filters)` and `Any(*filters)` compose
predicates recursively. An empty `All()` matches every row and an empty `Any()`
matches none. Values are bound parameters and names are validated against the
current schema before quoting.

A `Page` has `columns`, `rows`, `has_more`, `offset` and `limit`. Page
limits are 1 through 1000. Each table read fetches one extra row to determine
`has_more`. The primary key is appended to explicit sort terms and used as the
default ordering when present. SQLite's rowid can order unkeyed rowid tables or
break ties among nullable keys when an unshadowed alias is available. Objects
without a usable key or rowid fall back to ordering by their visible values.
Each page is a fresh snapshot. Concurrent changes or volatile view expressions
may move rows between successive offsets.

Rows retain the original SQLite value types as Python `None`, `int`, `float`,
`str` or `bytes`. `Row.columns` and `Row.values` are parallel tuples. Name
lookup returns the first column with that name. Inputs accept signed 64-bit
integers and finite reals. `parse_value(kind, text)` converts the explicitly
selected storage class from a text field. The available kinds are `null`,
`integer`, `real`, `text` and `blob`. Null accepts blank text or `NULL`,
integers use signed decimal, reals support decimal exponents, text preserves
whitespace, and blobs use hex byte pairs such as `00 ff`.

## Inspect a SQL result

```python
with Database(path) as db:
    page = db.query("SELECT * FROM records WHERE score >= ?", (10,), limit=100)
```

SQLite parses and authorizes one read statement. This permits SELECT, read CTEs
and read query plans. The authorizer denies writes, schema changes, PRAGMAs,
transaction control, extension loading and attachment, including on a writable
handle. Bind positional or named parameters. Raw-query rows have no edit
tokens. The fetch cap bounds the Python result. SQLite may still scan or sort
the input, execute expensive functions, or materialize a query before producing
a row. Cancellation is cooperative.

## Commit edits

Capture a `Table.schema_token` and the original row tokens when the user sees
the data. Reopen the same file with explicit write permission at save time:

```python
with Database(path, writable=True) as db:
    with db.transaction() as tx:
        tx.update(original_row.token, {"name": "revised"})
        tx.insert(records, {"name": "new"}, schema_token=records.schema_token)
        tx.delete(other_original_row.token)
```

`Table.editable` describes a table's schema capability. An ordinary table needs
a declared primary key. Views, virtual and shadow tables, SQLite system tables,
and tables without a declared key remain read-only. A nullable primary key may
still produce rows without tokens. Inserts use SQLite defaults and may create
such rows, which can be read afterward. Insert and update accept mappings of
writable column names to typed values. Omit fields to use insert defaults,
including an automatic INTEGER PRIMARY KEY where defined. Generated and hidden
columns cannot be assigned. A primary-key edit is validated like any other
change. Reload after a successful save to get current values and tokens.

A row token retains the file device and inode, schema token, and the original
**full** row including its storage types. Even a narrow projection keeps that
baseline. Inside `BEGIN IMMEDIATE`, the writer checks that the file and schema
still match and resolves exactly one row using SQLite's declared key
comparisons, including composite keys and their collations. It compares the
entire original row before issuing an update or delete. The schema token
includes the schema version and can be invalidated by unrelated schema changes.
Snapshots and tokens are intended for staging edits during a session.

Writes enforce foreign keys and run database triggers with SQLite's trusted
schema disabled. Insert and update explicitly use `OR ABORT` to prevent a
uniqueness collision from replacing a different row or silently substituting a
NOT NULL default. SQLite applies that outer conflict policy to statements
inside triggers as well. Ordinary trigger effects and foreign-key cascades may
change other rows as defined by the database.

A transaction is usable only inside its context. Any failed mutation dooms the
batch even if the caller catches the exception inside the context. Cancellation,
exceptions leaving the block and commit failures roll back the batch. Close
also rolls back outstanding work. Error types inherit `SQLiteError`. Use
`ValidationError` for invalid requests, `ReadOnlyError` for denied operations,
`StaleDataError` to reload changed data, `BusyError` to report lock contention,
`ConstraintError` for rejected changes and `CancelledError` for cancellation.
Underlying SQLite exceptions remain available as causes.

## Performance and compatibility

On a local macOS fixture with 250,000 rows and a 100-row limit, the median
first-page read across three warm-process runs was 0.46 ms with about 65 KB
peak traced Python allocations. Fetching the entire table through the legacy
wrapper before slicing took 182 ms and about 153 MB on that fixture. The
indexed filtered page with a narrow projection took 0.68 ms and about 68 KB.
A 100-row transactional save with original-row checks took 7.75 ms including
the page read and opening the writer. Measurements include connection overhead
and exclude SQLite native allocations. Large cells, deep offsets and unindexed
sorts still add work. The page limit bounds the row count, while byte usage
depends on values and the full originals retained for editable rows.

The legacy `integrations.wrappers.sqlWrapper.fetch_sql_table` returns the
**whole** table as numbered dictionaries. Its optional column list selects
existing named columns. Omitting it returns SQLite's default visible columns.
`exec_sql_command` runs and commits one statement and returns all result tuples.
That helper accepts trusted caller SQL and has no read-only authorizer, typed
edit tokens or result bound. Use the resource API for interactive inspection
and transactional editing.

[Integration reference](integrations.md)
