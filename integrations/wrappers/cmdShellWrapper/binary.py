"""Bounded, shell-free binary subprocess I/O with cooperative cancellation."""
from io import RawIOBase
import subprocess
import threading
import time
from .process import get_process_group_kwargs, terminate_process_tree


class _BinarySink(RawIOBase):
    """A pipe is append-only, even when Windows reports a successful seek."""
    def __init__(self, stream):
        super().__init__()
        self.stream = stream

    def writable(self):
        return True

    def write(self, data):
        return self.stream.write(data)

    def flush(self):
        if not self.stream.closed:
            self.stream.flush()


def run_bytes(arguments, *, environment=None, input_data=None, input_writer=None, max_output=1024 * 1024,
              timeout=60, cancelled=lambda: False):
    from ....runtime.operations import check_cancelled
    from ....runtime.platform.capabilities import Capability, require_capability
    require_capability(Capability.SUBPROCESS, "run_bytes")
    check_cancelled(cancelled)
    if max_output < 0 or timeout <= 0:
        raise ValueError('Invalid binary command limits.')
    child = subprocess.Popen(arguments, env=environment, stdin=subprocess.PIPE if input_data is not None or input_writer is not None else subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, **get_process_group_kwargs())
    overflow = threading.Event()
    output = bytearray()
    errors = []
    def read(stream, keep):
        try:
            while chunk := stream.read(65536):
                if keep:
                    if len(output) + len(chunk) > max_output:
                        overflow.set()
                        return
                    output.extend(chunk)
                # stderr is drained but never retained: a provider can echo secrets.
        except OSError:
            errors.append(True)
    def write():
        try:
            if input_writer is not None:
                input_writer(_BinarySink(child.stdin))
            else:
                for offset in range(0, len(input_data), 65536):
                    child.stdin.write(input_data[offset:offset + 65536])
            child.stdin.close()
        except Exception:
            errors.append(True)
            try:
                child.stdin.close()
            except OSError:
                pass
    threads = [threading.Thread(target=read, args=(child.stdout, True), daemon=True),
               threading.Thread(target=read, args=(child.stderr, False), daemon=True)]
    if input_data is not None or input_writer is not None:
        threads.append(threading.Thread(target=write, daemon=True))
    for thread in threads:
        thread.start()
    started = time.monotonic()
    try:
        while child.poll() is None or any(thread.is_alive() for thread in threads):
            check_cancelled(cancelled)
            if overflow.is_set():
                raise ValueError('Document operation exceeds its output limit.')
            if time.monotonic() - started > timeout:
                raise TimeoutError('Document operation timed out.')
            time.sleep(.02)
        if overflow.is_set():
            raise ValueError('Document operation exceeds its output limit.')
        if child.returncode or errors:
            raise OSError('Document operation failed.')
        return bytes(output)
    finally:
        if child.poll() is None:
            terminate_process_tree(child)
        for stream in (child.stdin, child.stdout, child.stderr):
            if stream:
                try:
                    stream.close()
                except OSError:
                    pass
        for thread in threads:
            thread.join(timeout=1)
