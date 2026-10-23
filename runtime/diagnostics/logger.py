"""Instance-owned logging, output sinks and explicit failure policy; no UI imports."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from pathlib import Path
from threading import RLock
import os
import sys


class DebugException(Exception):
    pass


class Severity(Enum):
    DEBUG = 'DBG'
    INFO = 'INF'
    WARNING = 'WRN'
    ERROR = 'ERR'
    CRITICAL = 'CRT'


@dataclass
class LoggingOptions:
    project_prefix: str | None = None
    include_time: bool = False
    use_time_delta: bool = True
    verbose_debug: bool = True
    write_to_log: bool = False


@dataclass(frozen=True)
class LogEvent:
    severity: Severity
    title: str
    message: str
    text: str
    colored: str


class ConsoleSink:
    def __init__(self):
        self._initialized = False

    def __call__(self, event):
        if not self._initialized:
            if sys.platform == 'win32':
                os.system('')
            self._initialized = True
        print(event.colored)


class FileSink:
    def __init__(self, path):
        self.path = Path(path)

    def __call__(self, event):
        with self.path.open('a') as stream:
            stream.write(event.text + '\n')


_interactive = ContextVar('interactive_logging', default=True)


@contextmanager
def noninteractive_logging():
    token = _interactive.set(False)
    try:
        yield
    finally:
        _interactive.reset(token)


class DebugLogger:
    def __init__(self, log_file='debug.log', *, options=None, sinks=None, presenter=None, raise_critical=True):
        self.options = replace(options) if options is not None else LoggingOptions()
        self.sinks = tuple(sinks) if sinks is not None else (ConsoleSink(),)
        self.file_sink = FileSink(log_file)
        self.presenter = presenter
        self.raise_critical = raise_critical
        self._last_timestamp = None
        self._lock = RLock()

    def configure(self, *, presenter=..., **options):
        with self._lock:
            self.options = replace(self.options, **options)
            if presenter is not ...:
                self.presenter = presenter

    def log_debug(self, severity, title, message, popup=False):
        with self._lock:
            options = replace(self.options)
            presenter = self.presenter
            if severity == Severity.DEBUG and not options.verbose_debug:
                return
            now = datetime.now()
            if options.include_time:
                timestamp = now.strftime('%H:%M:%S')
            elif options.use_time_delta:
                delta = 0 if self._last_timestamp is None else (now - self._last_timestamp).total_seconds()
                timestamp = f'{delta:.3f}s'
            else:
                timestamp = ''
            self._last_timestamp = now
        if options.project_prefix:
            title = f'{options.project_prefix} | {title}'
        skip = ' ' if timestamp else ''
        if '\n' not in message:
            text = f'{timestamp}{skip}[{severity.value}] {title}: {message}'
        else:
            text = f'{timestamp}{skip}[{severity.value}] {title}\n{message}'
            text = text.replace('\n', '\n' + ' ' * (len(timestamp) + len(skip) + len(severity.value) + 3)) + '\n'
        color = {Severity.DEBUG: '90', Severity.WARNING: '33', Severity.ERROR: '31', Severity.CRITICAL: '41;37'}.get(severity)
        colored = f'\033[{color}m{text}\033[0m' if color else text
        event = LogEvent(severity, title, message, text, colored)
        for sink in self.sinks:
            sink(event)
        if options.write_to_log:
            self.file_sink(event)
        if (popup or severity == Severity.CRITICAL) and _interactive.get() and presenter is not None:
            presenter(title, message)
        if severity == Severity.CRITICAL and self.raise_critical:
            raise DebugException(text)
