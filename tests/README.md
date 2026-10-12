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
