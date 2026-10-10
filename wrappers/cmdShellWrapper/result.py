"""Shell-free, cancellable command execution with explicit completion outcomes."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
import os
import queue
import subprocess
import threading
import time

from . import output, process


@dataclass(frozen=True)
class CommandResult:
    returncode: int | None
    stdout: tuple[str, ...] = ()
    stderr: tuple[str, ...] = ()
    timed_out: bool = False
    cancelled: bool = False

    @property
    def success(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.cancelled

    @property
    def lines(self) -> list[str]:
        return list(self.stdout + self.stderr)


def run_command(arguments: Sequence[str | os.PathLike] | str, *, cwd: str | Path | None = None,
                timeout: float | None = None, idle_timeout: float | None = None,
                cancelled: Callable[[], bool] = lambda: False, shell: bool = False,
                stdin: int | None = subprocess.DEVNULL) -> CommandResult:
    """Wait for completion and capture both streams; terminate the tree on cancellation.

    Pass an argument sequence by default. Shell strings require shell=True.
    timeout bounds elapsed time; idle_timeout bounds time without output. Neither
    limit is enabled by default. Launch errors propagate as OSError.
    """
    if isinstance(arguments, str) != shell:
        raise TypeError('Use an argument sequence, or a string with shell=True')
    for limit in (timeout, idle_timeout):
        if limit is not None and limit <= 0:
            raise ValueError('Command timeouts must be positive')
    if cancelled():
        return CommandResult(None, cancelled=True)
    child = subprocess.Popen(arguments, shell=shell, cwd=cwd, stdin=stdin,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             **process.get_process_group_kwargs())
    events = queue.Queue()
    buffers = {'stdout': bytearray(), 'stderr': bytearray()}
    readers = [threading.Thread(target=output.read_stream, args=(stream, name, events), daemon=True)
               for name, stream in (('stdout', child.stdout), ('stderr', child.stderr))]
    for reader in readers:
        reader.start()
    started = last_output = time.monotonic()
    active = 2
    timed_out = was_cancelled = False
    try:
        # Continue polling after EOF: a command can close its streams before exiting.
        while active or child.poll() is None:
            now = time.monotonic()
            was_cancelled = bool(cancelled())
            timed_out = ((timeout is not None and now - started >= timeout)
                         or (idle_timeout is not None and now - last_output >= idle_timeout))
            if was_cancelled or timed_out:
                process.terminate_process_tree(child)
                break
            try:
                name, chunk = events.get(timeout=.05)
            except queue.Empty:
                continue
            if chunk is None:
                active -= 1
            else:
                buffers[name].extend(chunk)
                last_output = time.monotonic()
        child.wait()
    except BaseException:
        process.terminate_process_tree(child)
        raise
    finally:
        for reader in readers:
            reader.join(timeout=1)
        output.drain_output_queue(events, buffers['stdout'], buffers['stderr'])
        process.close_process_streams(child)
    def lines(name):
        return tuple(line.decode('utf-8', errors='replace').rstrip('\r')
                     for line in output.output_bytes_to_lines(bytes(buffers[name])))
    return CommandResult(child.returncode, lines('stdout'), lines('stderr'), timed_out, was_cancelled)
