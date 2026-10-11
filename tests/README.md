# Testing commonUtils

Run the suite before changing a consumer's pinned or vendored copy. Tests cover
file preservation, archive validation, indexing, compatibility imports and Qt
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
