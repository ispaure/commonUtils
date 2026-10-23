"""Disk-spooled binary command capture with separate diagnostic progress.

Unlike pipe-based run_bytes, this permits completion before reporting truncation
and retains a stderr tail. Memory reads are bounded; spool disk usage is not.
"""

from dataclasses import dataclass
import os
import errno
import subprocess
from tempfile import TemporaryFile
from time import monotonic
from .process import get_process_group_kwargs, ProcessSupervisor
from ....runtime.operations import check_cancelled


class CommandStartError(OSError):
    """Process creation failed; callers translate/redact the diagnostic."""


class CommandTimeout(TimeoutError):
    """The elapsed command deadline expired."""


@dataclass(frozen=True)
class CapturedCommand:
    stdout: bytes
    stderr: bytes
    returncode: int
    truncated: bool = False


def run_captured(
    command,
    *,
    cwd=None,
    environment=None,
    input_data=None,
    limit=8 * 1024 * 1024,
    timeout=120,
    cancelled=lambda: False,
    progress=lambda data: None,
    discard_output=False,
):
    """Run shell-free; callbacks receive raw diagnostic bytes for caller filtering.

    Cancellation and callback failures terminate the process tree. On platforms
    without pread, callers can present the final stderr tail after completion.
    discard_output routes both outputs to DEVNULL and publishes no progress.
    Hosts own argument/environment policy and validation of input size.
    """
    from ....runtime.platform.capabilities import Capability, require_capability
    require_capability(Capability.SUBPROCESS, 'run_captured')
    if limit < 0 or timeout is not None and timeout < 0:
        raise ValueError('Invalid capture limits.')
    check_cancelled(cancelled)
    started = monotonic()
    with TemporaryFile() as output, TemporaryFile() as errors:
        try:
            process = subprocess.Popen(
                command,
                cwd=str(cwd) if cwd else None,
                env=environment,
                stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
                stdout=subprocess.DEVNULL if discard_output else output,
                stderr=subprocess.DEVNULL if discard_output else errors,
                **get_process_group_kwargs(),
            )
        except OSError as exc:
            raise CommandStartError(str(exc)) from exc
        position = 0
        writer = None
        write_errors = []
        with ProcessSupervisor(process) as supervisor:
            if input_data is not None:
                # Keep credential input off disk, but never let a full stdin pipe
                # prevent the supervising thread from enforcing cancellation.
                def write_input():
                    try:
                        with process.stdin:
                            process.stdin.write(input_data)
                    except BrokenPipeError:
                        pass
                    except OSError as error:
                        # Match subprocess.communicate: Windows may report a
                        # child closing stdin as EINVAL rather than EPIPE.
                        if error.errno != errno.EINVAL:
                            write_errors.append(error)
                    except BaseException as error:
                        write_errors.append(error)
                writer = supervisor.start(write_input, name='command-capture-stdin')
            while True:
                check_cancelled(cancelled)
                if write_errors:
                    raise write_errors[0]
                if timeout and monotonic() - started > timeout:
                    raise CommandTimeout("Command timed out.")
                try:
                    code = process.wait(timeout=0.05)
                except subprocess.TimeoutExpired:
                    code = None
                # Read through a separate descriptor: seeking the writer's file
                # offset would corrupt concurrent child writes on POSIX.
                size = os.fstat(errors.fileno()).st_size
                if size > position:
                    if hasattr(os, "pread"):
                        chunk = os.pread(
                            errors.fileno(), min(size - position, 65536), position
                        )
                    else:
                        # Windows doesn't offer pread; stream at completion there.
                        chunk = b""
                    position += len(chunk)
                    if chunk and not discard_output:
                        progress(chunk)
                if code is not None:
                    if writer is None or not writer.is_alive():
                        if write_errors:
                            raise write_errors[0]
                        break
                    # A descendant may still hold stdin after its parent exits.
                    # Continue supervision until the writer retires or is stopped.
                    writer.join(timeout=0.05)
        output.seek(0)
        data = output.read(limit + 1)
        errors.seek(max(0, os.fstat(errors.fileno()).st_size - 65536))
        stderr = errors.read() if not discard_output else b""
        return CapturedCommand(
            b"" if discard_output else data[:limit], stderr, code, len(data) > limit
        )
