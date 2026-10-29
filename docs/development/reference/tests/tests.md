# Testing commonUtils

Start with the [test-owner map](#find-a-regression-owner) and run the smallest
relevant module using the consumer's configured interpreter. The commands in this
guide assume the parent of the `commonUtils` checkout is on the import path.
For Logistics, `python3 dev.py test shared FILENAME` handles paths, isolated
processes and the relevant desktop/mobile-host legs for you.

A **portable** test exercises logic on the host. An **offscreen** Qt test runs Qt
without a visible window. A **dummy-backend** mobile test checks host-side behavior
without the native controls. Native acceptance runs on the actual supported
platform; none of the first three proves the last.

## Native filesystem notifications

Qt browser/watcher tests need access to the operating system's filesystem
notification service. A restricted macOS runner can list existing files while
missing later changes, causing rename/row-discovery timeouts, stale watches and
index-search update failures. Recheck these suites with native notification access
and isolated temporary storage before changing their event-driven behavior.
Keep their real watcher assertions; manually emitting notifications or extending
timeouts does not validate automatic updates.

Cross-process indexing tests allow a bounded 30 seconds for cold interpreter
startup and durable checkpoints on slower hosts. Marker waits report child
exit status and stderr immediately if a runner dies. A waiting child records its
Python stack after 20 seconds; checkpoint timeouts include that trace so a
Windows SQLite lock can be diagnosed before temporary evidence is removed. Browser subscription tests
retry transient SQLite queue locks within their deadline, matching production
followers; assertions still verify completion, totals and durable task ownership.
The no-duplicate-scan assertion counts exact folders across both process journals:
transient queue contention can hand off ownership after a durable checkpoint.

See [maintenance and documentation ownership](../../maintenance.md).

Command-failure fixtures instrument only the exact target argv. Windows cleanup
launches `taskkill` through the same subprocess module; preserve those helper
processes and check retirement of the command being tested.

Run the suite before changing a consumer's pinned or vendored copy. Tests cover
file preservation, archive validation, indexing, direct package imports and Qt
worker ownership. External applications, native dialogs and drivers also need
platform checks.

## Find a regression owner

Test filenames stay unique, but the test directory is grouped by responsibility:

| Owner | Tests |
| --- | --- |
| `archives/` | Members, rebuilds, extraction, ZIP safety and archive views |
| `filesystem/` | File objects, traversal, links, moves, copies and rename operations |
| `index/` | Persistent schema, scans, reconciliation, allocation and shared jobs |
| `formats/` | Image/EXIF encoding, text formats, tables and syntax data |
| `runtime/` | Streams, processes, cancellation, persistence, progress and transfers |
| `configuration/` | INI/settings layers, monitors and subscriptions |
| `integrations/` | Captured commands, launcher contracts and Perforce wrappers |
| `browser/` | File/entry browsers, extensions, search and presentation |
| `resources/` | Provider operations, selections and lifecycle |
| `editors/` | Code editing, diff/merge views and transforms |
| `markdown/` | Document synchronization, rendering, editing and wiki navigation |
| `native/` | Native controls, layout, rendering and portable lifecycle |
| `appearance/` | Shared controls, typography, reader chrome and display policy |
| `workspaces/` | Tabs, placement, containers and workspace lifetime |
| `tooling/` | Package boundaries, mobile staging, wiki layout and test harness contracts |

For example, from the parent of the commonUtils checkout:

```sh
python -m unittest commonUtils.tests.runtime.test_streams
QT_QPA_PLATFORM=offscreen python -m unittest commonUtils.tests.markdown.test_markdown
```

The isolated-module runner discovers matching filenames recursively, so existing
`--pattern test_streams.py` selections remain valid. Subfolder initializers have no
side effects; they support ordinary unittest discovery. Cross-folder test fixtures
use explicit package imports. The reusable `tests/qt_test_case.py` and standalone
`tests/mobile_smoke.py` remain at their established root paths for consumers and
native testbed staging. Blue Hole's selected portable suite uses the same classes
and methods through their new owner paths; it does not duplicate assertions.

## Development and validation

### Reusable consumer test mechanisms

`commonUtils.testing` is an opt-in package for host tests and native acceptance
drivers. Importing it loads no toolkit or application. Its modules use relative
library imports and contain no Logistics workflows:

| Module | Contract |
| --- | --- |
| `testing.stages` | `TestStage.SMOKE`, `REGRESSION`, `EXTENDED`, cumulative `PROFILES`, `@stage` overrides and source-only `classify`/`validate`. Each source declares one enum default; invalid or duplicate declarations fail together before imports. |
| `testing.settings` | Shared polling, keyboard acknowledgement, screenshot and rotation defaults. Runner budgets belong to consumers. Durations are seconds; attempts and stable samples are counts. |
| `testing.waiting` | `wait_until` returns the first truthy synchronous observation by a monotonic deadline; lazy timeout messages can describe the final state. `wait_for_assertion` retries only assertion failures and retains the final error. Other errors and cancellation propagate. |
| `testing.waiting.settled_keyboard` | Requires the served input and visible IME to agree for consecutive samples; retries requests after instability and returns false after its explicit attempt budget. |
| `testing.rotation.NativeRotation` | Dispatches native Toga window/Activity requests and observes acknowledgement. iOS checks the exact interface orientation; Android checks configuration and window aspect, which does not certify left/right direction on constrained firmware. `restored()` restores the original iOS pose or exact Android orientation policy after a scenario. |
| `testing.screenshots` | Captures the composited native window, including accelerated Android content, and releases encoding resources on failure. Callers choose evidence paths and reporting. |
| `testing.tasks.start_once` | Lazily schedules and retains one task per owner/attribute, including completion or failure, so repeated native lifecycle callbacks cannot launch duplicate checks. |
| `testing.event_loop.close_loop` | Cancels pending tasks, reports failed finalizers, closes async generators and joins the default executor before closing an isolated fixture loop. Callers first close windows and retire external workers. Never pass a live application loop. |

Consumers own app factories, credentials/backend fakes, scenario assertions,
evidence schemas and build/device cleanup. Keep workload-specific budgets explicit
at their owner instead of increasing shared defaults. Async wait predicates must
be synchronous and nonblocking; these helpers do not certify native behavior when
run against mocked bridges. The existing Qt fixture stays at
`commonUtils.tests.qt_test_case.QtTestCase` for its established consumers.

`TEST_STAGE = TestStage.REGRESSION` labels a Python module. Import the enum from
`commonUtils.testing.stages`. `@stage(TestStage.SMOKE)` on a class or method overrides
the default; method labels win, including inherited methods. Keep expensive soaks
and comprehensive native journeys EXTENDED. Standalone embedded scripts may use a
column-zero `# TEST_STAGE = TestStage.MEMBER` comment; Go/Swift/Java use `//`.
`validate(paths)` parses source without importing tests and returns classifications,
including locally inherited cases. Runtime `Classification.resolve(case)` covers
imported unittest bases and generated cases. Static inventories cannot enumerate
those dynamic cases. Consumers own root manifests, selection, execution, failure
gates and reports; `PROFILES` supplies smoke/daily/full cumulative stage tuples.
Library tests inherit their module default. Direct unittest discovery remains
supported but does not itself select stages or enforce a consumer's preflight.

Polling helpers reject observations or assertions that succeed after their deadline;
keep predicates synchronous and quick. Cleanup errors propagate, so consumers must
keep fixture files alive when worker retirement fails. The loop helper never removes
fixture roots itself.

Regression owners for these mechanisms are `tests/tooling/test_async_waiting.py`,
`test_keyboard_acknowledgement.py`, `test_native_rotation.py`,
`test_native_screenshots.py`, `test_test_event_loop.py` and `test_test_tasks.py`.

### Fixtures and lifecycle

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

After widget destruction and owned worker/future retirement, cleanup explicitly
collects eligible Python cycles on the GUI thread. Signal/callback cycles can
retain wrappers whose C++ widgets are already gone; leaving them for a later
worker allocation can run their finalizers on that worker. A real widget-cycle
regression checks collection after native destruction on the application thread.
Production application GC policy remains application-owned. Native crashes still
require their captured trace and affected-suite rechecks; a fixture contract does
not establish every possible crash cause.

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
PYTHONPATH=Python python -m unittest commonUtils.tests.native.test_mobile_platform commonUtils.tests.tooling.test_mobile_portability -v
```

These tests simulate five OS identities plus legacy mobile identifiers. Fresh
interpreters reject optional desktop dependency imports; actual document and ZIP
I/O uses temporary files on the test host. They do not run a mobile interpreter,
mobile filesystem provider or mobile UI. Keep real-device results separate from
these mocked contracts. The [mobile audit](../../mobile-foundation.md)
records policy, integration prerequisites and remaining deployment blockers.

`mobile_smoke.py` is a separate, dependency-free suite for embedded runtimes.
Unlike the mocked compatibility tests above it does not replace OS identifiers.
Use `--target host` only to check the harness locally. The manual Android/iOS
workflow and first-run instructions are in the [mobile test guide](../../mobile-testing.md).

Default-storage fixtures clear host storage overrides while checking OS defaults;
all paths remain inside their temporary homes. Speech tests inspect the owned
session or published highlights instead of retired facade fields. Optional Toga
consumer subprocesses retain the discovered dependency directory when the backend
comes from another existing environment, while continuing to import shared source
from this checkout and rejecting consumer/application imports.
