"""Optional, explicitly requested Mermaid CLI rendering without GUI-thread work.

No runtime download or shell command interpolation. A parented QProcess runs the
installed mmdc with strict configuration, a bounded input/timeout, and a private
commonUtils Temp workspace. Failed diagrams remain readable code blocks.
"""
from collections import OrderedDict
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil

from .. import pyside as qt
from ...storage import temporary_workspace
from ...markdownUtils import split_frontmatter
from .extensions import mermaid_blocks


def diagram_key(source, dark):
    return sha256((str(dark) + source).encode()).hexdigest()


def safe_diagram(source):
    """Disallow note-level configuration and remote/HTML resource declarations."""
    if len(source) > 50_000:
        raise ValueError('Diagram exceeds the 50,000-character rendering limit.')
    if re.search(r'%%\s*\{|^\s*---\s*$|https?://|file:|<\s*(?:img|iframe|script)|\bimage\s*:', source, re.I | re.M):
        raise ValueError('This diagram uses configuration or external resources. Its source is shown instead.')
    return source


class MermaidRenderer(qt.QObject):
    def __init__(self, viewer):
        super().__init__(viewer)
        self.viewer = viewer
        self.images = OrderedDict()
        self.process = qt.QProcess(self)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._failed)
        self.timer = qt.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(20_000)
        self.timer.timeout.connect(self._timeout)
        self.workspace = None
        self.pending = []
        self.current = None
        self.errors = []
        self.source = ''
        self.cancelled = False

    def render(self):
        if self.current is not None:
            return
        executable = shutil.which('mmdc')
        if not executable:
            qt.QMessageBox.information(self.viewer, 'Mermaid diagrams',
                'Diagram rendering needs the optional Mermaid CLI (mmdc).\n\n'
                'Install @mermaid-js/mermaid-cli using npm, then restart Logistics. '
                'Until then, Mermaid blocks remain visible as code. '
                'Your Markdown file is unchanged.')
            return
        self.source = split_frontmatter(self.viewer.markdown_text()).body
        self.cancelled = False
        self.dark = self.viewer.browser.palette().color(qt.QPalette.ColorRole.Base).lightness() < 128
        self.executable = executable
        self.errors = []
        self.pending = [(diagram_key(body, self.dark), body) for _, _, body in mermaid_blocks(self.source)[:12]
                        if diagram_key(body, self.dark) not in self.images]
        self.viewer.diagrams_button.setEnabled(False)
        self._next()

    def _next(self):
        if self.cancelled:
            return
        while self.pending:
            key, body = self.pending.pop(0)
            try:
                safe_diagram(body)
                self.workspace = temporary_workspace(prefix='markdown-diagram-', ignore_cleanup_errors=True)
                root = Path(self.workspace.name)
                (root / 'input.mmd').write_text(body, encoding='utf-8')
                (root / 'config.json').write_text(json.dumps({'securityLevel': 'strict',
                    'startOnLoad': False, 'maxTextSize': 50_000, 'flowchart': {'htmlLabels': False}}), encoding='utf-8')
            except (OSError, ValueError) as error:
                self.errors.append(str(error))
                self._cleanup()
                continue
            self.current = key
            self.viewer.status.setText('Rendering Mermaid diagrams…')
            self.process.setWorkingDirectory(str(root))
            self.process.start(self.executable, ['-i', str(root / 'input.mmd'), '-o', str(root / 'output.png'),
                '-c', str(root / 'config.json'), '-t', 'dark' if self.dark else 'default', '-b', 'transparent'])
            self.timer.start()
            return
        self.viewer.diagrams_button.setEnabled(True)
        if self.source == split_frontmatter(self.viewer.editor.toPlainText()).body:
            self.viewer._render_source(self.viewer.editor.toPlainText())
            self.viewer.status.setText('Some diagrams could not be rendered; their code is still shown. ' + self.errors[0]
                                       if self.errors else 'Mermaid diagrams rendered. Your Markdown file is unchanged.')

    def _finished(self, code, status):
        if self.current is None:
            return
        self.timer.stop()
        image = qt.QImage()
        if self.workspace:
            reader = qt.QImageReader(str(Path(self.workspace.name) / 'output.png'))
            size = reader.size()
            if size.isValid() and size.width() * size.height() <= 16_000_000:
                image = reader.read()
        if code == 0 and status == qt.QProcess.ExitStatus.NormalExit and not image.isNull() and image.width() * image.height() <= 16_000_000:
            self.images[self.current] = image
            while len(self.images) > 24:
                self.images.popitem(last=False)
        else:
            self.errors.append(bytes(self.process.readAllStandardError()).decode('utf-8', 'replace')[:500]
                               or 'The local Mermaid renderer did not return an image.')
        self.current = None
        self._cleanup()
        self._next()

    def _failed(self, error):
        if error == qt.QProcess.ProcessError.FailedToStart:
            self._finished(-1, qt.QProcess.ExitStatus.CrashExit)

    def _timeout(self):
        self.errors.append('Diagram rendering timed out after 20 seconds.')
        self.process.kill()

    def _cleanup(self):
        if self.workspace:
            self.workspace.cleanup()
            self.workspace = None

    def substitute(self, source, document):
        """Insert cached images through QTextDocument resources, never filesystem links."""
        dark = self.viewer.browser.palette().color(qt.QPalette.ColorRole.Base).lightness() < 128
        lines = source.splitlines()
        for start, end, body in reversed(mermaid_blocks(source)):
            key = diagram_key(body, dark)
            image = self.images.get(key)
            if image is not None:
                url = qt.QUrl('mermaid:' + key)
                document.addResource(qt.QTextDocument.ResourceType.ImageResource, url, image)
                lines[start:end + 1] = [f'![Mermaid diagram]({url.toString()})'] + [''] * (end - start)
        return '\n'.join(lines)

    def cancel(self):
        active = self.current is not None
        self.cancelled = True
        self.pending.clear()
        self.timer.stop()
        if self.process.state() != qt.QProcess.ProcessState.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1000)
        self.current = None
        self._cleanup()
        self.viewer.diagrams_button.setEnabled(True)
        if active:
            self.viewer.status.setText('Diagram rendering cancelled. Source remains available.')
