"""Generic, case-preserving INI documents with non-destructive atomic updates.

Values are strings; application schemas, suffixes and UI controls belong to callers.
Interpolation is disabled, duplicate keys/sections are rejected, and UTF-8 BOMs,
newlines, comments and unchanged formatting survive edits. DEFAULT inheritance
follows ConfigParser. The legacy configUtils API is independent and unchanged.
"""
from configparser import ConfigParser
import os
from pathlib import Path
import re
import stat
from tempfile import NamedTemporaryFile

from .txtType import TXTFile


class INIFile(TXTFile):
    def __init__(self, path):
        super().__init__(Path(path))
        self._original = None
        self.text = ''
        self._parser = self.parse('')

    @staticmethod
    def parse(text):
        parser = ConfigParser(interpolation=None, strict=True)
        parser.optionxform = str
        parser.read_string(text)
        return parser

    def read(self):
        data = self.path.read_bytes()
        text = data.decode('utf-8-sig')
        parser = self.parse(text)
        self._original, self.text, self._parser = data, text, parser
        return self

    def sections(self):
        """Return explicit sections, plus DEFAULT when it has values."""
        return (['DEFAULT'] if self._parser.defaults() else []) + self._parser.sections()

    def items(self, section):
        """Return string pairs; normal sections include inherited defaults."""
        return list(self._parser[section].items())

    def get(self, section, key, fallback=None):
        return self._parser.get(section, key, fallback=fallback)

    @classmethod
    def updated_text(cls, text, changes):
        """Replace/add (section, key): string values while retaining other text.

        Multiline values use indented continuations. Parse and semantic validation
        happen before returning any text; unsupported ambiguous formatting fails
        safely instead of silently changing unrelated settings.
        """
        expected = cls.parse(text)
        for (section, key), value in changes.items():
            if not isinstance(value, str):
                raise TypeError('INI values must be strings')
            if any(c in key for c in '\r\n=:') or not key.strip() or key.startswith(('#', ';', '[')):
                raise ValueError('Invalid INI key')
            if any(c in section for c in '\r\n[]') or not section:
                raise ValueError('Invalid INI section')
            if section != 'DEFAULT' and not expected.has_section(section):
                expected.add_section(section)
            expected[section][key] = value
        newline = '\r\n' if '\r\n' in text else '\n'
        lines = text.splitlines(keepends=True)
        for (section, key), value in changes.items():
            current = 'DEFAULT'
            found = None
            section_end = len(lines)
            in_section = section == 'DEFAULT'
            for index, line in enumerate(lines):
                stripped = line.strip()
                if not stripped or stripped.startswith(('#', ';')):
                    continue
                header = re.match(r'^\s*\[([^]]+)\]', line)
                if header:
                    if in_section:
                        section_end = index
                        in_section = False
                    current = header[1]
                    if current == section:
                        in_section = True
                        section_end = len(lines)
                    continue
                option = re.match(r'^([ \t]*)([^=:\r\n]+?)([ \t]*[=:][ \t]*)(.*?)(?:\r?\n)?$', line)
                if current == section and option and option[2].strip() == key:
                    found = (index, option)
                    break
            parts = value.split('\n')
            if found:
                index, option = found
                indent = len(option[1])
                end = index + 1
                comments = []
                while end < len(lines):
                    candidate = lines[end]
                    if not candidate.strip() or candidate.lstrip().startswith(('#', ';')):
                        comments.append(candidate)
                    elif len(candidate) - len(candidate.lstrip()) > indent:
                        pass  # Old multiline continuation.
                    else:
                        break
                    end += 1
                ending = newline if lines[index].endswith('\n') or end < len(lines) else ''
                replacement = [option[1] + option[2] + option[3] + parts[0] + (newline if len(parts) > 1 else ending)]
                replacement += ['    ' + part + (newline if n < len(parts) - 1 else ending)
                                for n, part in enumerate(parts[1:], 1)]
                lines[index:end] = replacement + comments
            else:
                if lines and not lines[-1].endswith('\n'):
                    lines[-1] += newline
                block = [key + ' = ' + parts[0] + newline]
                block += ['    ' + part + newline for part in parts[1:]]
                if section == 'DEFAULT' and not any(re.match(r'^\s*\[DEFAULT\]', line) for line in lines):
                    lines[0:0] = ['[DEFAULT]' + newline] + block + [newline]
                elif section in cls.parse(''.join(lines)).sections() or section == 'DEFAULT':
                    lines[section_end:section_end] = block
                else:
                    lines.extend([newline, '[' + section + ']' + newline] + block)
        updated = ''.join(lines)
        actual = cls.parse(updated)
        if actual.defaults() != expected.defaults() or actual.sections() != expected.sections() or any(
                dict(actual[section]) != dict(expected[section]) for section in expected.sections()):
            raise ValueError('Cannot safely preserve this INI layout; use the source editor')
        return updated

    def set(self, section, key, value):
        self.text = self.updated_text(self.text, {(section, key): value})
        self._parser = self.parse(self.text)

    def save(self):
        """Atomically save; refuse to replace a file changed since read()."""
        self.parse(self.text)
        current = self.path.read_bytes() if self.path.exists() else None
        if current != self._original:
            raise OSError('The INI changed on disk; read it again before saving')
        newline = '\r\n' if self._original and b'\r\n' in self._original else '\n'
        content = self.text.replace('\r\n', '\n').replace('\n', newline).encode('utf-8')
        if self._original and self._original.startswith(b'\xef\xbb\xbf'):
            content = b'\xef\xbb\xbf' + content
        mode = stat.S_IMODE(self.path.stat().st_mode) if current is not None else None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        staged = None
        try:
            with NamedTemporaryFile(dir=self.path.parent, prefix='.' + self.path.name,
                                    suffix='.tmp', delete=False) as stream:
                staged = Path(stream.name)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if mode is not None:
                staged.chmod(mode)
            # Recheck after writing the temporary file, before replacement.
            if (self.path.read_bytes() if self.path.exists() else None) != self._original:
                raise OSError('The INI changed on disk; read it again before saving')
            os.replace(staged, self.path)
        finally:
            if staged is not None:
                staged.unlink(missing_ok=True)
        self._original = content
        self.size = len(content)


from .registry import register_file_type
register_file_type(INIFile, 'ini', priority=-100)
