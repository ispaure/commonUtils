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
