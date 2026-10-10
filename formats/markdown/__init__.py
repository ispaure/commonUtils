"""Dependency-free basic Markdown properties; preserve complex YAML as raw text.

This deliberately supports a small frontmatter subset, not general YAML. Updates
patch only the selected property's lines so unrelated YAML never gets reserialized.
"""
from dataclasses import dataclass
from datetime import date, datetime
import json
import re


@dataclass(frozen=True)
class Frontmatter:
    prefix: str
    yaml_text: str
    body: str
    complete: bool = True

    @property
    def present(self):
        return bool(self.prefix)


@dataclass(frozen=True)
class RawYAML:
    """Uninterpreted complex YAML value, retained for display and source editing."""
    text: str
    tag: str = 'raw'


def _lines(text):
    lines = re.findall(r'[^\r\n]*(?:\r\n|\r|\n|$)', text)
    return lines[:-1] if lines and not lines[-1] else lines


def split_frontmatter(text):
    """Recognize frontmatter only on the first line; retain its source verbatim."""
    lines = _lines(text)
    if not lines or lines[0].strip() != '---':
        return Frontmatter('', '', text)
    for index, line in enumerate(lines[1:], 1):
        if line.strip() in ('---', '...'):
            return Frontmatter(''.join(lines[:index + 1]), ''.join(lines[1:index]),
                               ''.join(lines[index + 1:]))
    return Frontmatter(text, ''.join(lines[1:]), '', False)


def _content(text):
    """Split inline comments outside quotes; never treat URL fragments as comments."""
    quote = None
    escaped = False
    for index, character in enumerate(text):
        if escaped:
            escaped = False
        elif quote == '"' and character == '\\':
            escaped = True
        elif quote == "'" and character == "'" and text[index + 1:index + 2] == "'":
            escaped = True
        elif character == quote:
            quote = None
        elif quote is None and character in ('"', "'") and (index == 0 or (text.startswith('[') and re.search(r'[\[,]\s*$', text[:index]))):
            quote = character
        elif quote is None and character == '#' and (index == 0 or text[index - 1].isspace()):
            return text[:index].rstrip(), text[index:]
    if quote:
        raise ValueError('Invalid YAML properties: unterminated quoted value.')
    return text.strip(), ''


def parse_property_value(text):
    """Parse a scalar or simple inline list; return RawYAML for complex syntax."""
    value, _ = _content(text.strip())
    if not value or value in ('null', 'Null', 'NULL', '~'):
        return None
    if value.startswith('"'):
        try:
            decoded = json.loads(value)
        except ValueError as error:
            # YAML-specific escapes are outside the basic subset; keep them raw.
            if value.endswith('"'):
                return RawYAML(value)
            raise ValueError('Invalid YAML properties: malformed quoted value.') from error
        return decoded
    if value.startswith("'"):
        if not value.endswith("'"):
            raise ValueError('Invalid YAML properties: malformed quoted value.')
        return value[1:-1].replace("''", "'")
    if value.startswith('['):
        if not value.endswith(']'):
            raise ValueError('Invalid YAML properties: unclosed inline list.')
        entries, start, quote, escaped = [], 1, None, False
        for index, character in enumerate(value[1:-1], 1):
            if escaped:
                escaped = False
            elif quote == '"' and character == '\\':
                escaped = True
            elif quote == "'" and character == "'" and value[index + 1:index + 2] == "'":
                escaped = True
            elif character == quote:
                quote = None
            elif quote is None and character in ('"', "'") and re.search(r'[\[,]\s*$', value[:index]):
                quote = character
            elif quote is None and character in '[{':
                return RawYAML(value)
            elif quote is None and character == ',':
                entries.append(value[start:index])
                start = index + 1
        entries.append(value[start:-1])
        return [parse_property_value(entry) for entry in entries if entry.strip()]
    if value.startswith(('{', '!', '&', '*', '|', '>')):
        return RawYAML(value)
    if value.lower() in ('true', 'false'):
        return value.lower() == 'true'
    if re.fullmatch(r'[+-]?(?:0|[1-9]\d*)', value):
        return int(value)
    if re.fullmatch(r'[+-]?(?:(?:\d+\.\d*|\d*\.\d+)(?:[eE][+-]?\d+)?|\d+[eE][+-]?\d+)', value):
        return float(value)
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:[Tt ]\d{2}:\d{2}.*)?', value):
        try:
            return datetime.fromisoformat(value) if len(value) > 10 else date.fromisoformat(value)
        except ValueError:
            return value
    if ': ' in value:
        raise ValueError('Invalid YAML properties: quote text containing a colon followed by a space.')
    return value


@dataclass(frozen=True)
class _PropertyRecord:
    name: str
    start: int
    end: int
    value: object
    comment: str


def _records(frontmatter):
    if not frontmatter.complete:
        raise ValueError('Missing closing --- for YAML properties. Repair it in Source mode.')
    lines = _lines(frontmatter.yaml_text)
    records, current = [], None
    for index, line in enumerate(lines):
        clean = line.rstrip('\r\n')
        if not clean.strip() or clean.lstrip().startswith('#') or clean.strip() == '{}':
            continue
        if clean[0].isspace() or clean.startswith('- '):
            if current is None:
                raise ValueError('Invalid YAML properties: expected a property name.')
            continue
        match = re.fullmatch(r'((?:"(?:[^"\\]|\\.)*"|\'(?:[^\']|\'\')*\'|[^:#]+)):[ \t]*(.*)', clean)
        if not match:
            raise ValueError('Unsupported or invalid YAML properties. Edit complex mappings in Source mode.')
        key = match[1].strip()
        if key.startswith(('"', "'")):
            key = parse_property_value(key)
        elif re.fullmatch(r'[+-]?\d+(?:\.\d+)?', key) or key.lower() in ('true', 'false', 'null'):
            raise ValueError('Properties must have nonempty text names; quote numeric names.')
        if not isinstance(key, str) or not key:
            raise ValueError('Properties must have nonempty text names.')
        if any(record[0] == key for record in records):
            raise ValueError(f'Invalid YAML properties: duplicate property {key}.')
        current = (key, index, match[2])
        records.append(current)
    result = []
    for position, (key, start, value) in enumerate(records):
        boundary = records[position + 1][1] if position + 1 < len(records) else len(lines)
        end = boundary
        while end > start + 1 and (not lines[end - 1].strip() or lines[end - 1].lstrip().startswith('#')):
            end -= 1
        children = lines[start + 1:end]
        content, comment = _content(value)
        if children:
            meaningful = [line for line in children if line.strip() and not line.lstrip().startswith('#')]
            if not content and meaningful and all(re.match(r'^\s*-\s+', line) for line in meaningful):
                parsed = [parse_property_value(re.sub(r'^\s*-\s+', '', line).rstrip('\r\n')) for line in meaningful]
            else:
                parsed = RawYAML(value + '\n' + ''.join(children))
        else:
            parsed = parse_property_value(value)
        result.append(_PropertyRecord(key, start, end, parsed, comment))
    return lines, result


def parse_properties(frontmatter):
    """Read basic scalar/list fields. Complex values remain RawYAML objects."""
    return {record.name: record.value for record in _records(frontmatter)[1]}


def _scalar(value):
    if isinstance(value, RawYAML):
        raise ValueError('Edit complex YAML values in Source mode or Edit YAML.')
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise ValueError('Only text, numbers, dates, checkboxes and simple lists are supported.')


def replace_property(text, name, value=None, *, remove=False):
    """Patch one property's lines; preserve all other frontmatter and body text."""
    if not isinstance(name, str) or not name.strip() or any(char in name for char in '\r\n'):
        raise ValueError('Enter a nonempty single-line property name.')
    parts = split_frontmatter(text)
    lines, records = _records(parts)
    record = next((record for record in records if record.name == name), None)
    if remove and record is None:
        return text
    if record and not remove and type(record.value) is type(value) and record.value == value:
        return text
    newline = '\r\n' if '\r\n' in parts.prefix else '\n'
    key = name if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*', name) and name.lower() not in ('true', 'false', 'null') else json.dumps(name, ensure_ascii=False)
    comment = ' ' + record.comment if record and record.comment else ''
    if remove:
        replacement = []
    elif isinstance(value, list):
        replacement = [key + ':' + comment + newline] + ['  - ' + _scalar(item) + newline for item in value]
        if not value:
            replacement = [key + ': []' + comment + newline]
    else:
        replacement = [key + ': ' + _scalar(value) + comment + newline]
    if record:
        lines[record.start:record.end] = replacement
    else:
        lines = [line for line in lines if line.strip() != '{}']
        if lines and not lines[-1].endswith(('\n', '\r')):
            lines[-1] += newline
        lines.extend(replacement)
    if parts.present:
        original = _lines(parts.prefix)
        opening, closing = original[0], original[-1]
        if replacement and not closing.endswith(('\n', '\r')):
            closing += newline
    else:
        opening, closing = '---' + newline, '---' + newline
    return opening + ''.join(lines) + closing + parts.body


def replace_frontmatter(text, yaml_text):
    """Check the basic mapping structure; retain complex values without interpreting."""
    parts = split_frontmatter(text)
    replacement = Frontmatter('---\n' + yaml_text.rstrip('\n') + '\n---\n', yaml_text, parts.body)
    parse_properties(replacement)
    return replacement.prefix + replacement.body
