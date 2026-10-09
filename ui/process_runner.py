"""Asynchronous process execution and retry state, independent of presentation."""
from dataclasses import dataclass
from collections import deque
import codecs
import re
from . import pyside as qt


@dataclass(frozen=True)
class ProcessUpdate:
    done: float = 0
    total: float = 0
    message: str = ''
    state: str = 'running'
    attempt: int = 0


@dataclass(frozen=True)
class ProcessResult:
    state: str
    exit_code: int | None
    attempt: int
    error: str = ''

    @property
    def succeeded(self):
        return self.state == 'succeeded'


class ProcessRunner(qt.QObject):
    output = qt.Signal(str)
    status = qt.Signal(str, int, str)
    progress = qt.Signal(object)
    completed = qt.Signal(object)

    def __init__(self, parent=None, *, parser=None, max_attempts=1, retry_delay_ms=1000):
        super().__init__(parent)
        self.parser = parser
        self.max_attempts = max(1, max_attempts)
        self.retry_delay_ms = max(0, retry_delay_ms)
        self.process = qt.QProcess(self)
        self.process.setProcessChannelMode(qt.QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)
        self.retry_timer = qt.QTimer(self)
        self.retry_timer.setSingleShot(True)
        self.retry_timer.timeout.connect(self._launch)
        self.kill_timer = qt.QTimer(self)
        self.kill_timer.setSingleShot(True)
        self.kill_timer.setInterval(2000)
        self.kill_timer.timeout.connect(self.process.kill)
        self.busy = False
        self.cancel_requested = False
        self.attempt = 0
        self.execution_attempt = 0

    def start(self, program, arguments=(), *, working_directory=None):
        if self.busy:
            raise RuntimeError('Process is already running')
        self.program, self.arguments = str(program), [str(value) for value in arguments]
        self.process.setWorkingDirectory(str(working_directory) if working_directory else '')
        self.busy = True
        self.cancel_requested = False
        self.execution_attempt = 0
        self._launch()

    def _launch(self):
        if self.cancel_requested:
            self._complete(ProcessResult('cancelled', None, self.attempt))
            return
        self.execution_attempt += 1
        self.attempt = self.execution_attempt
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        self.pending = ''
        self.tail = deque(maxlen=20)
        self.status.emit('running', self.attempt, 'Starting process…')
        self.process.start(self.program, self.arguments)

    def _read(self):
        self._consume(self.decoder.decode(bytes(self.process.readAllStandardOutput())))

    def _consume(self, text):
        if not text:
            return
        self.output.emit(text)
        self.pending += text
        lines = re.split(r'\r\n|[\r\n]', self.pending)
        self.pending = lines.pop()
        for line in lines:
            self._line(line)

    def _line(self, line):
        if line.strip():
            self.tail.append(line)
        if self.parser:
            try:
                update = self.parser(line)
            except (ValueError, TypeError, KeyError):
                update = None
            if update:
                self.attempt = update.attempt or self.attempt
                self.progress.emit(update)
                self.status.emit(update.state, self.attempt, update.message)

    def _finished(self, exit_code, exit_status):
        self.kill_timer.stop()
        self._read()
        self._consume(self.decoder.decode(b'', final=True))
        if self.pending:
            self._line(self.pending)
            self.pending = ''
        if self.cancel_requested:
            self._complete(ProcessResult('cancelled', exit_code, self.attempt))
        elif exit_status == qt.QProcess.ExitStatus.NormalExit and exit_code == 0:
            self._complete(ProcessResult('succeeded', exit_code, self.attempt))
        else:
            error = f'Process exited with code {exit_code}.\n' + '\n'.join(self.tail)
            self._failure(exit_code, error)

    def _process_error(self, error):
        if error == qt.QProcess.ProcessError.FailedToStart:
            self._failure(None, self.process.errorString())

    def _failure(self, exit_code, error):
        if self.cancel_requested:
            self._complete(ProcessResult('cancelled', exit_code, self.attempt))
        elif self.execution_attempt < self.max_attempts:
            self.status.emit('retrying', self.execution_attempt + 1, error)
            self.retry_timer.start(self.retry_delay_ms)
        else:
            self._complete(ProcessResult('failed', exit_code, self.attempt, error))

    def _complete(self, result):
        if not self.busy:
            return
        self.busy = False
        self.retry_timer.stop()
        self.kill_timer.stop()
        message = (f'Succeeded on attempt {result.attempt}.' if result.succeeded else
                   'Cancelled.' if result.state == 'cancelled' else result.error)
        self.status.emit(result.state, result.attempt, message)
        self.completed.emit(result)

    def cancel(self):
        if not self.busy:
            return
        self.cancel_requested = True
        self.retry_timer.stop()
        self.status.emit('running', self.attempt, 'Cancellation requested…')
        if self.process.state() != qt.QProcess.ProcessState.NotRunning:
            self.process.terminate()
            self.kill_timer.start()
        else:
            self._complete(ProcessResult('cancelled', None, self.attempt))
