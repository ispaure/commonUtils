# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

import queue

from ... import debugUtils


# ----------------------------------------------------------------------------------------------------------------------
# CODE

tool_name = 'commonUtils/wrappers/cmdShellWrapper'


def read_stream(stream, stream_name: str, output_queue: queue.Queue):
    """
    Read binary chunks from a subprocess stream.

    Reading chunks instead of complete lines ensures output such as progress updates using carriage returns or
    partial writes still counts as activity and resets the idle timeout.
    """
    try:
        while True:
            if hasattr(stream, 'read1'):
                chunk = stream.read1(4096)
            else:
                chunk = stream.read(4096)

            if not chunk:
                break

            output_queue.put((stream_name, chunk))

    except (OSError, ValueError):
        # The stream may be closed by timeout handling while this reader is blocked.
        pass

    finally:
        output_queue.put((stream_name, None))


def drain_output_queue(output_queue: queue.Queue, stdout_output: bytearray, stderr_output: bytearray):
    """Drain any output that reached the queue immediately before the process streams were closed."""
    while True:
        try:
            stream_name, chunk = output_queue.get_nowait()
        except queue.Empty:
            break

        if chunk is None:
            continue

        if stream_name == 'stdout':
            stdout_output.extend(chunk)
        else:
            stderr_output.extend(chunk)


def output_bytes_to_lines(output: bytes) -> list[bytes]:
    """
    Convert captured output bytes into lines while preserving the previous newline-based behavior.

    Carriage returns embedded within a line are preserved. A trailing newline does not create an additional empty
    output entry.
    """
    if not output:
        return []

    lines = output.split(b'\n')

    if lines[-1] == b'':
        lines.pop()

    return lines


def clean_output_line(line_str: bytes) -> str:
    """Clean an output line so it only keeps relevant information."""
    decoded_line = line_str.decode(errors='replace')
    cleaned_line = decoded_line.rstrip('\n').rstrip('\r')

    debugUtils.log(debugUtils.Severity.DEBUG, tool_name, cleaned_line)
    return cleaned_line