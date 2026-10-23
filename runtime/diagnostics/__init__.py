"""Logging defaults are namespace-local; applications explicitly install presentation."""
from .logger import DebugLogger, DebugException, Severity, LoggingOptions, LogEvent, ConsoleSink, FileSink, noninteractive_logging


default_logger = DebugLogger()
log = default_logger.log_debug
configure = default_logger.configure


def print_debug_msg(msg, show_verbose):
    if show_verbose:
        print(msg)
