# Using the Perforce wrapper

The wrapper runs the `p4` CLI and exposes file, group and connection models.
It does not install Perforce, create a workspace or perform interactive login.
Set up the CLI, workspace mapping and authentication before running these examples.
Make the parent of `commonUtils` importable; see [getting started](../../../../developer/getting-started.md).

Examples use illustrative paths. Replace `/workspace/project` with your local
workspace root (for example, `r"C:\work\project"` on Windows). Commands operate on
the configured workspace. Checkout opens files for edit or add; it does not submit
a changelist. Unless stated otherwise, examples require a working Perforce server.

## Configure the executable and connection

If `p4` is on `PATH` and your CLI connection is already configured, no runtime
configuration is needed. To select an executable explicitly:

```python
from commonUtils.integrations.wrappers.perforce import (
    PerforceRuntime,
    configure_runtime,
)

configure_runtime(PerforceRuntime(
    executable=lambda platform: "/opt/perforce/bin/p4",
))
```

The callback receives the commonUtils `OS` enum. Return an installed executable
path appropriate for that platform, such as `r"C:\Program Files\Perforce\p4.exe"`.
On macOS/Linux the wrapper checks that the path is a file and makes it executable.
The default callback resolves `p4` with `shutil.which`.

Applications can also supply connection settings:

```python
from commonUtils.integrations.wrappers.perforce import (
    P4Info,
    PerforceRuntime,
    configure_runtime,
)

settings = {
    "P4PORT": "ssl:perforce.example.com:1666",
    "P4USER": "alice",
    "P4CLIENT": "alice-workstation",
}
configure_runtime(PerforceRuntime(environment=lambda: settings))
info = P4Info()  # Applies the supplied settings, then queries login and info.
```

Only `P4USER`, `P4PORT` and `P4CLIENT` are accepted. Despite its name, the
`environment` callback is applied through `p4 set KEY=VALUE`, not as a per-command
subprocess environment. Those settings can persist according to the platform's
`p4 set` behavior. Constructing `P4Info` applies them and marks the connection unavailable if applying them fails; `info.update_fields()` only
refreshes login/info. Low-level commands and file status refreshes do not apply
the callback themselves. To apply it explicitly, call
`set_p4_env_settings()` from `.p4_utils`.

Callbacks are evaluated when used, so changes to `settings` can be picked up on
the next application of the settings. Configuration is shared across this imported
library, not scoped to a file or repository. `configure_runtime(None)` restores
default callbacks; it does not undo settings already written by `p4 set`.

## Get server and workspace information

`P4Info()` immediately runs `p4 login -s` and `p4 info`; there is no separate
connect call. Check its status before consuming its fields:

```python
from commonUtils.integrations.wrappers.perforce import P4Info

info = P4Info()
if info.status is not True:
    raise RuntimeError("Could not read Perforce connection information")

print("Server:", info.server_address)
print("Server uptime:", info.server_uptime)
print("User:", info.user_name)
print("Workspace:", info.client_name)
print("Workspace root:", info.client_root)

info.update_fields()  # Refresh after a connection or login change.
if info.status is True:
    print("Server date:", info.server_date)
```

The parser currently populates these string fields:

| Area | Fields |
| --- | --- |
| User and workspace | `user_name`, `client_name`, `client_host`, `client_root`, `client_cwd` |
| Network | `peer_address`, `client_address`, `server_address` |
| Server | `server_root`, `server_date`, `server_uptime` |

Other declared fields, including `server_version`, `server_id`, `client_stream`
and `case_handling`, remain empty strings in the current implementation. Use the
raw `p4 info` example below if you need the complete response.

`is_server_accessible(silent=True)` checks cached status and logs a message; it
does not probe the server again. `dialog_box_p4_info()` presents a short summary
through commonUtils diagnostics. The parser expects English CLI labels and
specific keys. Failed commands and incomplete or empty connection output set `status=False`. A failed refresh may leave earlier
field values in place, so always check the refreshed status.

## Inspect a file without checking it out

Constructing `P4File` only initializes a model. Call `update_fields()` to query
`p4 fstat` and populate it:

```python
from commonUtils.integrations.wrappers.perforce import P4File, P4FileStatus

item = P4File(client_file="/workspace/project/config.txt")
if not item.update_fields():
    raise RuntimeError("Could not refresh file status")

print("Depot path:", item.depotFile)
print("Status:", item.status.value)
print("Local/server revision:", item.haveRev, item.headRev)
if item.status is P4FileStatus.CHECKOUT_BY_OTHER:
    print("Opened by:", item.otherOpen0)
```

Use absolute local path strings for `client_file`. Constructor parameters use
snake case, while populated fields retain Perforce names such as `clientFile`
and `depotFile`. Most fstat values, including revisions, are strings or `None`;
convert them explicitly if you need numeric comparisons.

The simplified status enum includes `NOT_ADDED`, `MARKED_FOR_ADD`,
`MARKED_FOR_DELETE`, `CHECKOUT_BY_ME`, `CHECKOUT_BY_OTHER`, `LATEST_REVISION`,
`NOT_LATEST_REVISION` and `INVALID`. It is derived from selected fstat fields,
not a complete representation of all Perforce states. Inspect `action`,
`headAction`, `otherOpen` and `notInClientView` when those details matter.
For example, an `edit` action takes precedence over another user's checkout in
the simplified status.

A no-argument `update_fields()` queries the client path, or the depot path when no client path is known. Empty or malformed records return `False` and clear the simplified status without replacing the original path. Parsed model records must contain `clientFile`.

## Check out one file

```python
from commonUtils.integrations.wrappers.perforce import P4File

item = P4File(client_file="/workspace/project/config.txt")
if not item.open_for_edit(silent=True, allow_sync=False):
    raise RuntimeError("Checkout did not complete; inspect the Perforce log")

# Make your application changes only after checkout succeeds.
print("Ready to edit:", item.clientFile)
```

`open_for_edit()` checks connection information, the workspace root, client view,
other checkouts and delete status using the wrapper's existing checks. It then
adds, syncs or opens the file as required and refreshes its state. A `True` result
means the final simplified status is `CHECKOUT_BY_ME` or `MARKED_FOR_ADD`.
Known command failures, incomplete status and declined prompts return `False`; unexpected exceptions can still propagate. Failed add/sync/edit phases stop the remaining checkout commands.

- `silent=False` (default) asks for confirmation before add, sync and edit through
  commonUtils UI dialogs. Use this from an application with the UI configured.
- `silent=True` skips those confirmations and performs the actions automatically.
  It is not a dry run or a guarantee that all diagnostics are suppressed.
- `allow_sync=False` refuses checkout of a file classified as an older revision.
  This is useful when your application should not replace local content.
- `allow_sync=True` (default) permits `p4 sync -f` before checkout when needed.
  Review local changes before allowing a forced sync.

Single-file and group model operations pass paths as separate subprocess arguments without a shell. Spaces and shell characters retain their argument boundaries. Perforce filespec syntax still applies; these methods do not escape Perforce wildcards or revision selectors.

## Add a new file

Use the same checkout entry point for a file not yet in the depot. Create the
intended content first when its type matters:

```python
from pathlib import Path
from commonUtils.integrations.wrappers.perforce import P4File

path = Path("/workspace/project/new_config.txt")
with path.open("x", encoding="utf-8") as stream:
    stream.write("enabled=true\n")

item = P4File(client_file=str(path))
if not item.open_for_edit(silent=True, allow_sync=False):
    raise RuntimeError("File was created locally but could not be opened for add")
print(item.status.value)
```

The parent directory must already exist in this example. Opening with `"x"`
prevents overwriting an existing file. The wrapper leaves existing content intact
when adding. If an add target is absent, it instead creates parent directories and
a binary placeholder containing one NUL byte, or copies the file supplied by the
optional `PerforceRuntime.binary_template` callback. The callback returns a `Path`
or `None`. This placeholder behavior may be unsuitable for new text files.

## Check out several files together

Use `P4FileGroup` instead of repeatedly calling single-file checkout. It batches
fstat and mutation commands into path lists:

```python
from commonUtils.integrations.wrappers.perforce import P4FileGroup, P4FileStatus

group = P4FileGroup()
for path in (
    "/workspace/project/config.txt",
    "/workspace/project/read me.txt",
):
    group.append_p4_file_to_group_from_client_file(path)

if not group.open_for_edit():
    raise RuntimeError("Batch checkout did not complete")

ready = {P4FileStatus.CHECKOUT_BY_ME, P4FileStatus.MARKED_FOR_ADD}
for item in group.get_p4_file_lst():
    if item.status not in ready:
        raise RuntimeError(f"Not ready for editing: {item.clientFile}")
    print(item.clientFile, item.status.value)
```

Group checkout adds untracked files, force-syncs older revisions and opens eligible
files for edit without confirmation prompts. It has no `silent` or `allow_sync`
parameter. Use it only when those actions are intended. It is not transactional:
earlier commands may already have changed files if a later command fails.

A `True` return means all commands succeeded, all requested status records were refreshed, and every member ended in `CHECKOUT_BY_ME` or `MARKED_FOR_ADD`. A failed command stops later batches/phases and returns `False`; failures can leave earlier files changed. Failed readiness checks log the affected paths. The example also shows how to inspect individual results.

For a read-only batch refresh, call `group.update_fields_client_n_depot()` instead
of `group.open_for_edit()`. You can add depot paths with
`append_p4_file_to_group_from_depot_file("//depot/project/config.txt")` and refresh
to obtain their mapped client paths. Refresh depot-only entries before checkout:
the checkout workspace-root check runs before its internal refresh.

## Force-sync a group

```python
from commonUtils.integrations.wrappers.perforce import P4FileGroup

group = P4FileGroup()
group.append_p4_file_to_group_from_client_file("/workspace/project/config.txt")
group.force_get_latest()  # Runs p4 sync -f; may replace local content.
if not group.update_fields_client_n_depot():
    raise RuntimeError("Could not refresh status after sync")
for item in group.get_p4_file_lst():
    print(item.clientFile, item.status.value)
```

`force_get_latest()` returns a boolean command outcome, performs no checkout preflight checks and does not refresh model fields itself. Use it only after deciding a forced sync is appropriate; refresh afterward to inspect the resulting state.

## Read raw command output and fstat records

Helpers are imported from `p4_utils`, rather than the package root:

```python
from commonUtils.integrations.wrappers.perforce.p4_utils import (
    exec_p4_command,
    p4_fstat_dict,
)

for line in exec_p4_command("p4 info"):
    print(line)

records = p4_fstat_dict("/workspace/project/...")
if records is None:
    raise RuntimeError("Could not query file records")
for record in records:
    print(record.get("clientFile"), record.get("headRev"))
```

`exec_p4_command()` requires the literal `p4 ` prefix and substitutes the configured
executable. It returns output lines, not an exit code or a structured success
result. Commands run through a shell with a 15-second **idle** timeout. Timeouts,
cancellation and unsuccessful exits without output produce critical diagnostics
(which raise `DebugException` under the standard diagnostics implementation).
Nonzero exits with output are returned to callers because fstat diagnostics such
as “no such file(s)” are meaningful to the parser. Output alone is not proof that
a mutation succeeded. Do not interpolate untrusted strings into commands.

`p4_fstat_dict()` returns a list of records, retains the final record without a
trailing blank line, and preserves spaces in field values. It converts “no such
file(s)” to a record containing `clientFile`, and “not in client view” to one with
`notInClientView=True`. A recognized expired-session message returns `None`.
Unknown diagnostic lines and empty results return `None` with an error report. The helper also accepts a sequence of paths; this form uses shell-free execution and rejects failed/timed-out partial output except recognized missing-file/client-view diagnostics. Model operations use this form. Handle unexpected exceptions at the application operation boundary as well as checking boolean results.

## Structured command outcomes

`p4_utils.exec_p4_arguments(["edit", path])` returns the shared `CommandResult`
(`success`, `returncode`, `stdout`, `stderr`, `timed_out`, `cancelled`, `lines`).
It resolves the configured executable and runs without a shell, retaining the
15-second idle timeout and executable-permission handling. Launch errors and
unsuccessful outcomes are logged with the command, arguments and diagnostics;
ordinary command failures return to the caller rather than imposing save policy.
`set_p4_env_settings()` returns a boolean and retains the existing `p4 set`
persistence behavior. The legacy `exec_p4_command(string)` output-list entry point
remains available with its existing shell and critical-error behavior.

## Extension hooks and other entry points

Subclasses of `P4File` can override `_callback_pre_add`, `_callback_post_add`,
`_callback_pre_sync`, `_callback_post_sync`, `_callback_pre_edit` and
`_callback_post_edit` to save or reload application state. They take only `self`.
These hooks wrap the corresponding single-file command helpers. Post hooks run only after a successful command exit; failed or skipped commands do not invoke them. They do not independently re-query the resulting file state. In Blue Hole the post-sync hook reloads the scene before the existing checkout flow continues. Batch operations do not invoke these
per-file hooks. BlueHole keeps its `BlendP4File` and scene-specific behavior in
its own adapter; the shared wrapper does not import Blender or add-on preferences.

`P4File.run_p4_move(destination)` issues `p4 move` with separate path arguments and returns a boolean command outcome. It performs no checkout preflight or subsequent refresh. The caller must satisfy Perforce's move requirements and refresh if it needs resulting metadata. There are no high-level submit
or revert methods in these models.

`create_p4_user_workspace_cls(computer_name, username, workspace)` returns a
`P4UserWorkspace` data holder with `computername`, `username` and `workspace`
attributes. It does not create a server-side workspace.

The focused [wrapper tests](../../../../../tests/test_perforce.py) use fixture output
and mocked execution; they do not establish live-server or consumer compatibility.

[Wrapper overview](perforce.md) · [Other wrappers](../wrappers.md)
