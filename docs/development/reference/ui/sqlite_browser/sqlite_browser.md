# SQLite browser integration

`commonUtils.ui.sqlite_browser.SQLiteBrowser` is an optional Qt dialog backed by
the headless [SQLite API](../../integrations/sqlite.md). It runs database work in
`OperationProgress`, uses a fresh connection per job, and keeps staged edits until
an explicit successful save or discard. Read the [user guide](../../../../user/sqlite_browser/sqlite_browser.md)
for controls and typed values.

`FileBrowser` contributes **Inspect SQLite…** for a single local `.db`, `.db3`,
`.sqlite` or `.sqlite3` file. This suffix check is only a cheap menu hint; SQLite
validates content on the worker. Double-click handlers retain their existing
behavior. `ResourceBrowser` offers the action only for a provider declaring the
SQLite local-access hook. No database data is copied out or written back.

Both browsers accept `sqlite_write_allowed(path)` and `sqlite_readonly_paths`.
The former is a worker-safe host callback that must return literal `True` to
permit editing. Its absence means browse-only. The latter is an iterable of
managed paths, or a worker-safe callback supplying current paths. Host callbacks
may raise an actionable access error. Independent-file, existing local-access,
link, mount, permissions and managed-store checks run again before each job.
These checks are application routing safeguards, not an OS security sandbox.

The explicit provider hook is `sqlite_local_path(path, *, writable=False)`.
It must return the same direct local path or `None`; neither `replace`
capability nor a physical root grants access. `LocalFiles` implements it for its
exact ordinary provider type. Mapped subclasses must opt in explicitly and enforce
their own policy. Private, remote, encrypted, archive and native document resources
do not gain access. Network mounts, symlinks, junctions and hard-linked files are
rejected. A custom host must not opt a virtual path or temporary decoded copy in.

Managed directory-index and job paths are always browse-only. The browser also
recognizes their table groups conservatively in renamed copies. Hosts must supply
other application-owned database paths explicitly. This feature does not change
index schemas, writer queues, snapshots, refresh or retention ownership.

For direct embedding, construct `SQLiteBrowser(path, parent, writable=False,
access_check=callback)`. The optional callback is invoked on the worker with a
`writable` keyword before opening a connection. It must reject revoked access by
raising or returning `False`. Set `writable=True` only after defining this host
policy; it permits the explicit editing control, not immediate writes.

Retain the dialog until destruction. `busy` describes active worker I/O, `dirty`
describes staged edits, `can_retire` forbids hiding a dirty editor, and
`close_pending` identifies a user-authorized save/worker retirement for close.
`prepare_close()` and `close()` may veto while edits are unresolved. `idle`
arrives after worker retirement; `saved` arrives only after successful commit.
The existing browser controller retains dialogs and asks them to close before
retiring the browser. Hosts with background tab retirement must consult
`browser.sqlite_browser.can_retire` first, so Cancel leaves the browser visible.

Tests live in `tests/browser/test_sqlite_access.py`, `test_sqlite_browser.py`
and `test_sqlite_browser_integration.py`. They use disposable databases and Qt
event-loop checks. Such host tests do not establish native mobile UI support or
provider-specific locking guarantees.

## Responsiveness measurement

`tests/integrations/sqlite_ui_benchmark.py` runs real database jobs and a 5 ms Qt
heartbeat in a caller-owned disposable workspace. On macOS arm64 with Qt 6.12
and SQLite 3.51, a 250,000-row fixture took about 208 ms for an unindexed descending
sort, 274 ms for its next page and 214 ms for a single save followed by a sorted
reload. The largest heartbeat gap during those operations was 8.2 ms. The query
plan confirmed a table scan and temporary sort tree; no artificial delay was
used. Reopening verified the saved value. These offscreen host measurements
demonstrate worker/event-loop separation, not native user-interaction acceptance
or process RSS. Indexed reads and transaction-only costs are reported in the
[API guide](../../integrations/sqlite.md).
