# Running the mobile foundation checks

The [manual workflow](../../.github/workflows/mobile-smoke.yml) builds embedded
CPython test applications for Android and the iOS Simulator. It has **only** a
`workflow_dispatch` trigger: pushes and pull requests do not start mobile builds.
The existing desktop workflow is unchanged and can still run on pushes.

## First run: Android, then iOS

1. Open [commonUtils Actions](https://github.com/ispaure/commonUtils/actions/workflows/mobile-smoke.yml).
2. Select **Run workflow**, branch **main**, target **android**.
3. Wait for the Android job. Open its logs and download the
   `commonutils-android-smoke` artifact. Look for `android-result.json`.
4. Once Android passes, repeat with target **ios** and inspect
   `commonutils-ios-smoke` / `ios-result.json`. Choose **both** for later paired runs.
5. Bring the failed step and its artifact back to the development chat if a job
   fails. Keep build/toolchain failures distinct from test failures.

Equivalent commands, if GitHub CLI is already authenticated:

```sh
gh workflow run mobile-smoke.yml --repo ispaure/commonUtils --ref main -f target=android
gh run list --repo ispaure/commonUtils --workflow mobile-smoke.yml --limit 5
# Substitute the selected run ID:
gh run view RUN_ID --repo ispaure/commonUtils --log-failed
gh run download RUN_ID --repo ispaure/commonUtils
```

Replace `android` with `ios` for the second run. These commands **start remote
work**; the setup process does not execute them on your behalf. The workflow must
be present on the default branch to appear in the manual-run UI. It requires
Actions enabled and permission to dispatch workflows, but no signing secrets,
store credentials, production documents or deployment configuration. The
simulator/testbed builds are not distributable mobile applications.

## What a green result proves

Seven tests execute inside the mobile interpreter: runtime identity, portable
imports, capability rejection, private temporary/cache paths, lossless text saves
and conflict rejection, Markdown/registry traversal and plain ZIP container I/O.
The last case uses EPUB/CBZ extensions; it does not certify either document format
or render pages. Desktop GUI imports and encrypted ZIP dependencies must remain
unloaded. All fixtures are generated under the test application's temporary area.

The host verifier requires one structured report, matching `sys.platform` and
an actual `ios-simulator` or `android-emulator` runtime report, all seven tests,
zero failures/errors and **zero skips**. The testbed exit code must also succeed;
pipeline failures cannot be hidden by `tee`. A build-only success or desktop run
cannot pass the mobile evidence step. Reports include Python version, machine,
test counts and runtime classification; source.json records the commonUtils commit.

A simulator/emulator result is evidence for that runtime configuration only.
It does not enable desktop capability flags, certify physical devices, prove
external document-provider permissions, validate background suspension, or show
that Logistics' Qt application runs on mobile. Failures must be fixed rather than
mocked out or converted to unconditional skips.

## Reproducible inputs and limits

The workflow pins CPython **3.14.7**, commit
`823f0323ee6ec1402088b73bce1a38473cac36dc`, including its upstream testbeds. Host
Python is also 3.14.7; Android uses Java 21. Existing desktop consumers keep their
own Python/dependency pins. Mobile payloads contain tracked commonUtils Python
sources only: no .git metadata, local INIs, symlink targets or desktop pip install.

Android runs on Ubuntu 24.04, building an x86_64 interpreter and using CPython's
`maxVersion` managed emulator (API 35 in the pinned testbed). The upstream driver
configures KVM access, SDK prerequisites and Gradle. iOS runs on ARM64 macOS 15,
building a host interpreter plus an arm64 simulator framework. The upstream
selector chooses an available entry-level iPhone simulator and records the
available devices in the artifact. Xcode/SDK runner images and downloaded build
dependencies can change despite the source pin; the logs are part of the evidence.

Both jobs have a 90-minute upper bound and are opt-in because cold interpreter,
SDK and emulator builds are substantial. This bound is not a time or cost
estimate. Start one target at a time; cancel a clearly stuck job in Actions.
Artifacts are retained for 14 days, including build/testbed logs on failures.
There is no release, upload to an app store, external tester dispatch or signing.

## Local validation and evidence status

From the Logistics checkout:

```sh
PYTHONPATH=Python .venv/bin/python -m commonUtils.tests.mobile_smoke --target host
PYTHONPATH=Python .venv/bin/python -m unittest commonUtils.tests.test_mobile_ci -v
```

`--target host` deliberately emits `environment: desktop-harness`; the mobile
verifier rejects it. Unit tests check wrong-platform, missing, duplicate,
failed/skipped reports and packaging exclusions. These host tests are not the
mobile smoke suite running on a mobile interpreter.

At implementation time the host harness, report tests and workflow lint were
validated locally. **The mobile workflows have not been dispatched.** No
simulator/emulator or physical-device pass has been recorded. The local Xcode
installation had no available simulator devices. The first hosted runs remain
necessary to validate the complete build/runtime setup.

## Next milestones

After both runtime jobs pass, extend them with the consuming application's
headless document tests. Then build one small mobile document-open/read/edit/save
prototype using a chosen UI and document-provider integration. Only after that
should physical-device testing and distribution/signing be introduced. Keep
physical-device results in a separate evidence category and follow the
[remaining deployment blockers](mobile-foundation.md#remaining-deployment-blockers).

Upstream source: [Android testbed instructions](https://github.com/python/cpython/blob/823f0323ee6ec1402088b73bce1a38473cac36dc/Android/README.md),
[iOS build/testbed instructions](https://github.com/python/cpython/blob/823f0323ee6ec1402088b73bce1a38473cac36dc/Apple/iOS/README.md).

The local shared regression run completed 735 tests in 100 isolated modules with
zero failing modules (two platform skips). The seven-case desktop harness and the
three report/packaging tests passed; actionlint accepted the workflow. These are
host validation results, not evidence that either mobile workflow has run.
