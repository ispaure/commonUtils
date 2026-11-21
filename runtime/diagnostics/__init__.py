"""Logging defaults are namespace-local; applications explicitly install presentation."""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from .logger import DebugLogger, DebugException, Severity, LoggingOptions, LogEvent, ConsoleSink, FileSink, noninteractive_logging


default_logger = DebugLogger()
log = default_logger.log_debug
configure = default_logger.configure


def print_debug_msg(msg, show_verbose):
    if show_verbose:
        print(msg)
