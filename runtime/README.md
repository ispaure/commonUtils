# Runtime

Cross-cutting mechanisms used by the filesystem, archives, UI and applications.
Import the specific module you need; importing this area loads no GUI backend.

- `platform`: OS detection and platform constants.
- `diagnostics`: logging, severity and scoped debug settings.
- `logging`: timestamp helpers.
- `operations`: progress events and cooperative cancellation.
- `streams`: bounded copying, hashing and verified downloads.
- `helpers`: small shared helpers.

Example: `from commonUtils.runtime.operations import check_cancelled`.

[Library overview](../README.md).
