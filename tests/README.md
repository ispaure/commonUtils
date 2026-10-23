# Testing commonUtils

Cross-process indexing tests allow a bounded 30 seconds for cold interpreter
startup and durable checkpoints on slower hosts. Marker waits report child
exit status and stderr immediately if a runner dies. Browser subscription tests
retry transient SQLite queue locks within their deadline, matching production
followers; assertions still verify completion, totals and durable task ownership.

See [maintenance and documentation ownership](../docs/developer/maintenance.md).

Run the suite before changing a consumer's pinned or vendored copy. Tests cover
file preservation, archive validation, indexing, direct package imports and Qt
worker ownership. External applications, native dialogs and drivers also need
platform checks.

## Development and validation

`test_batch.py` owns portable batch outcomes with plain unittest and no toolkit
imports. `test_operations.py` retains Qt worker/progress ownership checks. Native
or mobile runtimes can reuse the batch suite without installing Qt or duplicating
its assertions in a consumer.

GUI tests inherit `QtTestCase`. Use `self.temporary_directory()` instead of a raw
`TemporaryDirectory` for files referenced by Qt widgets. It supports both `with`
scopes and `.name`/`.cleanup()` fixtures, registers cleanup automatically, and
destroys the scope's windows/watchers before removing the directory. Register
fixture-specific callbacks after creating it so buffer discard and private
database shutdown happen first. Context managers must enclose the widget's whole
lifetime. Existing windows outside the scope are preserved.

Use `self.wait_until(condition, timeout=5, message='operation description')`
for asynchronous Qt operations. It pumps events, succeeds
when the condition holds, and fails with the supplied message at the deadline.
Explicit deferred-deletion draining is reserved for shutdown; ordinary waits do
not prematurely destroy widgets whose owners are still processing close events.
Managed directory scopes also retain ThreadPoolExecutor jobs submitted during the
scope, including jobs whose QObject owner was deleted by the test body. They wait
for those jobs before removing files and always restore submission instrumentation
after cleanup, including failed shutdown. This prevents native Windows directory
handles outliving already-closed panes without ignoring cleanup errors.

Shutdown waits honor pending owners and running QThreads. An executor task exposed
as an owner's `future` (a `concurrent.futures.Future`) is also awaited after owner
destruction, allowing cancellation callbacks to release process/file handles.
Cleanup errors remain test failures. The base class also releases unscoped windows
between tests.

Raw SQLite fixture connections need explicit closure (for example,
`contextlib.closing(sqlite3.connect(...))`). A connection's own context manager
only commits or rolls back; it does not release Windows database file handles
before temporary-directory cleanup.

The base creates QApplication before fixture setup when needed. On Windows with
Qt's offscreen backend, it loads Segoe UI, Arial, Courier New and Georgia from the
existing Windows Fonts directory once per application. This supplies real outline
font metadata for font validation and prevents font-role coverage from being
silently skipped. Missing/unreadable fixture fonts fail with their file path.

Keep domain-specific file classes, application configuration and platform software
manifests in the consuming project. Reusable code should preserve established
public names, arguments and fields so dependent projects can update safely.

From the package's parent directory, run its tests with the project interpreter:

```sh
QT_QPA_PLATFORM=offscreen python -m unittest discover -s commonUtils/tests -v
```

For a checkout beneath `Python/`, run from the application's root:

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=Python python -m unittest discover -s Python/commonUtils/tests -v
```

On PowerShell, set `$env:QT_QPA_PLATFORM = "offscreen"` and the appropriate
`$env:PYTHONPATH` first. Optional test dependencies must be available. Tests use
fixtures and mocked integrations; native dialogs, external applications and system
installation/mount behavior need separate platform validation. Test consumers
before updating their submodule references.

## Mobile foundation checks

From the consuming checkout root:

```sh
PYTHONPATH=Python python -m unittest commonUtils.tests.test_mobile_platform commonUtils.tests.test_mobile_portability -v
```

These tests simulate five OS identities plus legacy mobile identifiers. Fresh
interpreters reject optional desktop dependency imports; actual document and ZIP
I/O uses temporary files on the test host. They do not run a mobile interpreter,
mobile filesystem provider or mobile UI. Keep real-device results separate from
these mocked contracts. The [mobile audit](../docs/developer/mobile-foundation.md)
records policy, integration prerequisites and remaining deployment blockers.

`mobile_smoke.py` is a separate, dependency-free suite for embedded runtimes.
Unlike the mocked compatibility tests above it does not replace OS identifiers.
Use `--target host` only to check the harness locally. The manual Android/iOS
workflow and first-run instructions are in the [mobile test guide](../docs/developer/mobile-testing.md).

Default-storage fixtures clear host storage overrides while checking OS defaults;
all paths remain inside their temporary homes. Speech tests inspect the owned
session or published highlights instead of retired facade fields. Optional Toga
consumer subprocesses retain the discovered dependency directory when the backend
comes from another existing environment, while continuing to import shared source
from this checkout and rejecting consumer/application imports.
