# Command Shell Wrapper

The `commonUtils.integrations.wrappers.cmdShellWrapper` package provides cross-platform command execution for **Windows, macOS, and Linux**.

It supports captured command output, detached execution, custom working directories, idle-output timeouts, process-tree cleanup, and launching commands in new terminal windows.

## Commands with explicit outcomes

Use `run_command()` for new callers. It accepts an argument vector and waits for
completion without a shell:

```python
from commonUtils.integrations.wrappers.cmdShellWrapper import run_command

result = run_command(["tool", "--input", "a file.txt"], timeout=120)
if not result.success:
    print(result.returncode, result.stderr, result.timed_out, result.cancelled)
```

`CommandResult` contains the exit status, separate stdout/stderr line tuples,
`timed_out`, and `cancelled`. `lines` returns stdout followed by stderr as a list.
`success` requires exit status zero with neither timeout nor cancellation.
A missing executable raises `OSError`. A cancelled call does not start a process.

Pass `cancelled=event.is_set` to stop a running process tree. `timeout` limits
elapsed time; `idle_timeout` limits time without output. Both are disabled unless
specified. Even a process that closes both output streams remains subject to
these checks until it exits. New commands are noninteractive (`stdin=DEVNULL`);
explicitly pass `stdin=None` when inheriting standard input is intentional.
Shell strings require `shell=True`.

`exec_cmd()` accepts shell strings: captured calls return output lines and
retain their idle timeout and inherited stdin. It does not expose
exit status. A new terminal window returns immediately regardless of
`wait_for_output`; terminal launch acceptance is not command completion.

## Basic Usage

`exec_cmd()` is the entry point for shell strings:

```python
from commonUtils.integrations.wrappers import cmdShellWrapper

output = cmdShellWrapper.exec_cmd(
    "python --version",
    wait_for_output=True
)
```

Available options include:

- `wait_for_output` — wait for and capture stdout/stderr
- `in_new_window` — launch the command in a separate terminal window and return immediately
- `time_out` — maximum idle time without stdout/stderr activity
- `cwd` — working directory for the command

The `time_out` value is an **idle-output timeout**, not a maximum runtime. A command may continue indefinitely as long as it continues producing output.

## Modules

### 📄 `__init__.py`

Exports `run_command()`, `CommandResult`, `exec_cmd()` and `minimize_console_window()`. Command execution lives in `result.py` and the shell-string adapter in `command.py`.

When output is captured, stdout and stderr are read concurrently so either stream counts as activity for the idle timeout.

### 📄 `output.py`

Handles subprocess output collection and cleanup.

It reads stdout/stderr as binary chunks rather than waiting for complete lines. This allows partial output and carriage-return-based progress updates to reset the idle timeout correctly.

Captured output is converted back into cleaned string lines before being returned by `exec_cmd()`.

### 📄 `process.py`

Provides process-group and process-tree management.

Commands that capture output are placed into their own process group/session where supported. If an idle timeout occurs, the wrapper attempts to terminate the entire process tree rather than only the shell process.

Platform behavior includes:

- **Windows** — new process groups and `taskkill`
- **macOS/Linux** — new sessions with `SIGTERM` / `SIGKILL`

The module also provides `minimize_console_window()`, currently implemented for Windows.

### 📄 `terminal.py`

Handles commands launched in separate terminal windows.

```python
cmdShellWrapper.exec_cmd(
    "python my_script.py",
    in_new_window=True
)
```

New-window execution returns immediately and does not capture output in the parent process.

Supported behavior includes:

- **Windows** — opens a new CMD window
- **macOS** — opens Terminal.app through AppleScript
- **Linux** — detects an available terminal emulator and launches the command there

On Linux, the wrapper respects `$TERMINAL` when available and supports common terminals including Konsole, GNOME Terminal, KGX, Ptyxis, XTerm, Kitty, Alacritty, WezTerm, Foot, Tilix, XFCE Terminal, LXTerminal, and MATE Terminal.

New terminal windows are intentionally kept open after the launched command completes.

## Return Values

When `wait_for_output=True`, `exec_cmd()` returns captured stdout followed by stderr as a list of strings:

```python
[
    "First output line",
    "Second output line"
]
```

Commands launched without captured output or in a new terminal window return immediately.

## Cross-Platform Design

Platform-specific terminal and process behavior is isolated inside the package so callers can generally use the same `exec_cmd()` interface on Windows, macOS, and Linux.

For Windows-specific PowerShell execution, use the separate `powerShellWrapper.py` module.

`run_command(..., environment=mapping)` supplies a complete child environment without
mutating the parent or including values in command arguments. `None` inherits the
parent environment. The caller owns filtering and secret lifetime.

`binary.run_bytes()` accepts bounded binary output and an optional `input_writer`
callback. The callback receives a write-only, nonseekable binary stream. Archive
writers therefore use streaming headers on every platform, including Windows
pipes whose native seek operations can appear to succeed. The wrapper drains
stderr without retaining it and applies cancellation and elapsed time limits.
Failed commands raise `binary.BinaryCommandError`, an `OSError` subclass with
`returncode` and `stderr` attributes. Diagnostics are empty by default; callers
may set `max_stderr` to retain at most that many bytes in memory while the rest
is drained. The exception message never includes these bytes. They may contain
secrets: consumers must translate or redact them before presentation or logging.

## Disk-spooled binary capture

`capture.run_captured(arguments, ...)` is the alternative for commands requiring
separate binary stdout, stderr progress and a final diagnostic tail. It returns
`CapturedCommand(stdout, stderr, returncode, truncated)`; nonzero exit status is
returned for the caller to interpret. Stdout reads use the requested `limit` and
stderr retains its final 64 KiB. Temporary spool files can grow on disk while the
command runs; these are memory bounds, not disk quotas. The existing `run_bytes`
API retains its pipe-based bounded-output behavior.

Supply `environment`, `cwd`, `input_data`, `timeout`, `cancelled` and a raw-byte
`progress` callback as needed. Timeouts and cooperative cancellation terminate the
process tree. On platforms without `os.pread`, progress is left to the caller using
the final stderr tail. `discard_output=True` routes both streams to DEVNULL.
Input stays in a pipe rather than a disk spool. A supervised writer keeps a
non-reading child from blocking timeout/cancellation; the writer retires before
return. Already-cancelled requests do not launch a process. Callers own input-size
limits, environment filtering, tool options and diagnostics.
Process creation raises `CommandStartError`, elapsed deadlines raise
`CommandTimeout`, and cooperative cancellation raises `OperationCancelled`.

`runtime.diagnostics.redaction.redact(text)` filters URL userinfo/query strings and
common authorization/password/token assignments in complete diagnostic text. It is
best effort, cannot recognize every secret, and cannot safely redact credentials
split across arbitrary streaming chunks. Discard output for sensitive commands.
