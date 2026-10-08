"""Previewable bulk filename transformations and rollback-capable rename batches.

No Qt dependency. Applications own the UI; this module owns rename planning and transactions.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass, fields, replace
from datetime import datetime, timedelta
from pathlib import Path
import ctypes
import errno
import os
import re
import stat
import sys
import unicodedata
import uuid

from .operations import OperationCancelled
from .traversal import natural_path_key


RenameCancelled = OperationCancelled


@dataclass(frozen=True)
class RenameMetadata:
    """Filesystem facts supplied to a transformation; no disk access required."""
    is_directory: bool = False
    modified: datetime | None = None
    created: datetime | None = None

    @classmethod
    def from_stat(cls, info):
        created = getattr(info, 'st_birthtime', info.st_ctime if os.name == 'nt' else None)
        return cls(stat.S_ISDIR(info.st_mode), datetime.fromtimestamp(info.st_mtime),
                   datetime.fromtimestamp(created) if created is not None else None)


@dataclass(frozen=True)
class RenameRules:
    """Rules apply in pipeline order; string modes use the documented lowercase values."""
    regex_pattern: str = ''
    regex_replacement: str = ''
    regex_include_extension: bool = False
    name_mode: str = 'keep'
    fixed_name: str = ''
    replace_from: str = ''
    replace_to: str = ''
    replace_case_sensitive: bool = True
    replace_first: bool = False
    case_mode: str = 'same'
    remove_first: int = 0
    remove_last: int = 0
    remove_start: int = 0
    remove_count: int = 0
    remove_chars: str = ''
    remove_digits: bool = False
    remove_symbols: bool = False
    remove_accents: bool = False
    trim: bool = False
    part_start: int = 0
    part_count: int = 0
    part_position: int = 0
    copy_part: bool = False
    prefix: str = ''
    insert: str = ''
    insert_position: int = 0
    suffix: str = ''
    date_mode: str = 'none'
    date_source: str = 'modified'
    date_format: str = '%Y-%m-%d'
    date_separator: str = '_'
    date_offset_days: int = 0
    folder_mode: str = 'none'
    folder_levels: int = 1
    folder_separator: str = '_'
    number_mode: str = 'none'
    number_start: int = 1
    number_step: int = 1
    number_padding: int = 0
    number_position: int = 0
    number_separator: str = '_'
    number_per_folder: bool = False
    extension_mode: str = 'same'
    extension: str = ''

    def validate(self):
        for field in fields(self):
            if type(getattr(self, field.name)) is not type(field.default):
                raise ValueError(f'{field.name} must be {type(field.default).__name__}')
        for field, options in {
            'name_mode': ('keep', 'fixed', 'remove'),
            'case_mode': ('same', 'lower', 'upper', 'title', 'sentence', 'swap'),
            'date_mode': ('none', 'prefix', 'suffix'),
            'date_source': ('modified', 'created', 'today'),
            'folder_mode': ('none', 'prefix', 'suffix'),
            'number_mode': ('none', 'prefix', 'suffix', 'insert'),
            'extension_mode': ('same', 'lower', 'upper', 'fixed', 'remove'),
        }.items():
            if getattr(self, field) not in options:
                raise ValueError(f'Invalid {field}: {getattr(self, field)}')
        for field in ('remove_first', 'remove_last', 'remove_start', 'remove_count',
                      'part_start', 'part_count', 'part_position', 'insert_position',
                      'number_padding', 'number_position'):
            if getattr(self, field) < 0:
                raise ValueError(f'{field} must be nonnegative')
        if self.number_padding > 255:
            raise ValueError('number_padding cannot exceed the filename byte limit')
        if self.folder_levels < 1:
            raise ValueError('folder_levels must be at least one')
        if self.regex_pattern:
            pattern = re.compile(self.regex_pattern)
            # Validate replacement backreferences even if no filename matches.
            pattern.sub(self.regex_replacement, '')

    def transform(self, path, index=0, *, metadata=None, now=None):
        """Transform a path without disk access. Supply metadata for folders/file dates."""
        path = Path(path)
        metadata = metadata or RenameMetadata()
        folder = metadata.is_directory
        extension = '' if folder else path.suffix
        name = path.name[:-len(extension)] if extension else path.name
        if self.regex_pattern:
            if self.regex_include_extension:
                complete = re.sub(self.regex_pattern, self.regex_replacement, path.name)
                extension = '' if folder else Path(complete).suffix
                name = complete[:-len(extension)] if extension else complete
            else:
                name = re.sub(self.regex_pattern, self.regex_replacement, name)
        if self.name_mode != 'keep':
            name = self.fixed_name if self.name_mode == 'fixed' else ''
        if self.replace_from:
            if self.replace_case_sensitive:
                name = name.replace(self.replace_from, self.replace_to, 1 if self.replace_first else -1)
            else:
                name = re.sub(re.escape(self.replace_from), lambda _: self.replace_to, name,
                              count=1 if self.replace_first else 0, flags=re.IGNORECASE)
        operations = {'lower': str.lower, 'upper': str.upper, 'title': str.title,
                      'sentence': str.capitalize, 'swap': str.swapcase}
        if self.case_mode in operations:
            name = operations[self.case_mode](name)
        name = name[self.remove_first:]
        if self.remove_last:
            name = name[:-self.remove_last]
        if self.remove_count:
            name = name[:self.remove_start] + name[self.remove_start + self.remove_count:]
        if self.remove_accents:
            name = ''.join(char for char in unicodedata.normalize('NFD', name)
                           if not unicodedata.combining(char))
            name = unicodedata.normalize('NFC', name)
        name = ''.join(char for char in name if char not in self.remove_chars
                       and not (self.remove_digits and char.isdigit())
                       and not (self.remove_symbols and unicodedata.category(char)[0] in 'PS'))
        if self.trim:
            name = name.strip()
        if self.part_count:
            part = name[self.part_start:self.part_start + self.part_count]
            if not self.copy_part:
                name = name[:self.part_start] + name[self.part_start + self.part_count:]
            name = name[:self.part_position] + part + name[self.part_position:]
        name = name[:self.insert_position] + self.insert + name[self.insert_position:]
        name = self.prefix + name + self.suffix
        if self.date_mode != 'none':
            if self.date_source == 'today':
                date = now or datetime.now()
            else:
                date = metadata.created if self.date_source == 'created' else metadata.modified
                if date is None:
                    raise ValueError(f'{self.date_source.capitalize()} date is unavailable; supply metadata or choose Today')
            text = (date + timedelta(days=self.date_offset_days)).strftime(self.date_format)
            name = _affix(name, text, self.date_mode, self.date_separator)
        if self.folder_mode != 'none':
            parents = list(path.parents)[:self.folder_levels]
            text = self.folder_separator.join(parent.name for parent in reversed(parents) if parent.name)
            name = _affix(name, text, self.folder_mode, self.folder_separator)
        if self.number_mode != 'none':
            text = str(self.number_start + index * self.number_step).zfill(self.number_padding)
            if self.number_mode == 'insert':
                name = name[:self.number_position] + text + name[self.number_position:]
            else:
                name = _affix(name, text, self.number_mode, self.number_separator)
        if not folder:
            if self.extension_mode == 'lower':
                extension = extension.lower()
            elif self.extension_mode == 'upper':
                extension = extension.upper()
            elif self.extension_mode == 'fixed':
                extension = '.' + self.extension.lstrip('.') if self.extension else ''
            elif self.extension_mode == 'remove':
                extension = ''
        return name + extension


def _affix(name, text, mode, separator):
    if not text:
        return name
    return separator.join(part for part in ((text, name) if mode == 'prefix' else (name, text)) if part)


def _absolute(path):
    path = Path(path).absolute()
    return path.parent.resolve() / path.name  # Keep the final symlink itself, not its target.


def _stamp(path):
    return _stamp_from_stat(path.lstat())


def _stamp_from_stat(info):
    return info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns


def _key(path, case_sensitive):
    text = unicodedata.normalize('NFC', str(path))
    return text if case_sensitive else text.casefold()


def _name_error(name):
    if not name or name in ('.', '..'):
        return 'Name is empty or reserved'
    if any(ord(char) < 32 or char in '<>:"/\\|?*' for char in name):
        return 'Name contains a path separator or a character unsupported on Windows'
    if name.endswith((' ', '.')):
        return 'Names cannot end with a space or dot'
    stem = name.split('.')[0].upper()
    if stem in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        return 'Name is a reserved Windows device name'
    if len(os.fsencode(name)) > 255:
        return 'Name exceeds 255 encoded bytes'
    return ''


@dataclass(frozen=True)
class RenameEntry:
    source: Path
    target: Path
    stamp: tuple
    error: str = ''

    @property
    def changed(self):
        return self.source != self.target


@dataclass(frozen=True)
class RenamePlan:
    entries: tuple
    case_sensitive: bool = False

    @property
    def valid(self):
        return not any(entry.error for entry in self.entries)

    @property
    def changes(self):
        return tuple(entry for entry in self.entries if entry.changed)


def _validate_entries(entries, case_sensitive=False):
    sources = Counter(_key(entry.source, case_sensitive) for entry in entries)
    targets = Counter(_key(entry.target, case_sensitive) for entry in entries)
    moving = {_key(entry.source, case_sensitive) for entry in entries if entry.changed}
    directories = [entry.source for entry in entries if entry.stamp and stat.S_ISDIR(entry.stamp[2])]
    occupied_by_parent = {}
    for parent in {entry.target.parent for entry in entries if entry.changed and not entry.error}:
        occupied_by_parent[parent] = Counter(_key(path, case_sensitive) for path in parent.iterdir())
    result = []
    for entry in entries:
        error = entry.error or _name_error(entry.target.name)
        source_key, target_key = _key(entry.source, case_sensitive), _key(entry.target, case_sensitive)
        if not error and (sources[source_key] > 1 or targets[target_key] > 1):
            error = 'Duplicate source or destination name (including case/Unicode equivalents)'
        if not error and entry.source.parent != entry.target.parent:
            error = 'Bulk renaming keeps each item in its current folder'
        if not error and any(folder in entry.source.parents for folder in directories):
            error = 'Select a folder or its children, not both in one batch'
        if not error and entry.changed:
            # Include differently-cased sibling names even on a case-sensitive filesystem.
            occupied = occupied_by_parent.get(entry.target.parent, {})
            if occupied.get(target_key, 0) and (target_key not in moving or occupied[target_key] > sources[target_key]):
                error = 'Destination already exists and is not being renamed'
        result.append(replace(entry, error=error))
    return RenamePlan(tuple(result), case_sensitive)


def plan_renames(paths, rules=None, *, case_sensitive=False, cancelled=lambda: False):
    """Plan in natural filename order; no disk changes. See each entry.error before applying."""
    rules = rules or RenameRules()
    rules.validate()
    paths = [_absolute(path) for path in paths]
    paths.sort(key=natural_path_key)
    counts = defaultdict(int)
    entries = []
    now = datetime.now()
    for index, path in enumerate(paths):
        if cancelled():
            raise RenameCancelled('Preview cancelled')
        stamp = ()
        try:
            info = path.lstat()
            stamp = _stamp_from_stat(info)
            number = counts[path.parent] if rules.number_per_folder else index
            target = path.with_name(rules.transform(path, number, metadata=RenameMetadata.from_stat(info), now=now))
            entries.append(RenameEntry(path, target, stamp))
        except (OSError, ValueError, OverflowError) as error:
            entries.append(RenameEntry(path, path, stamp, str(error)))
        counts[path.parent] += 1
    return _validate_entries(entries, case_sensitive)


def _rename_exclusive(source, target):
    """Publish without replacement, including racing destinations and empty directories."""
    if os.name == 'nt':
        os.rename(source, target)  # Windows rename refuses existing destinations.
        return
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == 'darwin':
        function = libc.renamex_np
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        arguments = (os.fsencode(source), os.fsencode(target), 0x4)  # SDK sys/stdio.h: RENAME_EXCL
    else:
        function = getattr(libc, 'renameat2', None)
        if function is None:
            raise OSError(errno.ENOTSUP, 'This platform lacks exclusive rename support')
        function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        arguments = (-100, os.fsencode(source), -100, os.fsencode(target), 1)  # AT_FDCWD, RENAME_NOREPLACE
    function.restype = ctypes.c_int
    if function(*arguments):
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), str(target))


def rename_path(source, target, *, overwrite=False):
    """Rename one file, directory or link; refuse replacement unless explicitly requested.

    Parents must already exist. Errors propagate to the caller. Identical paths
    are a no-op when the source exists; case-only renames use the batch engine.
    """
    source, target = _absolute(source), _absolute(target)
    if source == target:
        source.lstat()
        return
    if overwrite:
        os.replace(source, target)
    else:
        _rename_exclusive(source, target)


@dataclass(frozen=True)
class RenameResult:
    """Successful entries form the undo receipt; unresolved rollback errors retain paths."""
    entries: tuple = ()
    cancelled: bool = False
    error: str = ''
    recovery: tuple = ()
    case_sensitive: bool = False

    @property
    def success(self):
        return not self.error and not self.cancelled


def apply_renames(plan, *, cancelled=lambda: False, report=lambda done, total, message: None):
    """Revalidate, stage cycles safely, and roll the entire batch back on failure/cancel.

    Rollback never overwrites external files. If it cannot restore an original
    path, recovery lists (current_path, original_path, error) for manual recovery.
    Cancellation is checked between atomic renames; rollback is never cancelled.
    """
    if not plan.valid:
        raise ValueError('Fix all preview errors before renaming')
    # Reject stale source data and destinations before touching any source.
    for entry in plan.entries:
        if _stamp(entry.source) != entry.stamp:
            raise RuntimeError(f'Source changed since preview: {entry.source}')
    fresh = _validate_entries(plan.entries, plan.case_sensitive)
    if not fresh.valid:
        raise ValueError(next(entry.error for entry in fresh.entries if entry.error))
    changes = plan.changes
    stages = []
    published = []
    total = len(changes) * 2
    try:
        for entry in changes:
            if cancelled():
                raise RenameCancelled('Rename cancelled')
            temporary = entry.source.with_name(f'.bulk-rename-{uuid.uuid4().hex}')
            _rename_exclusive(entry.source, temporary)
            stages.append((entry, temporary))
            if _stamp(temporary) != entry.stamp:
                raise RuntimeError(f'Source changed while staging: {entry.source}')
            report(len(stages), total, f'Staging {entry.source.name}')
        for entry, temporary in stages:
            if cancelled():
                raise RenameCancelled('Rename cancelled')
            _rename_exclusive(temporary, entry.target)
            published.append((entry, temporary))
            report(len(stages) + len(published), total, f'Renamed {entry.target.name}')
        receipt = tuple(replace(entry, stamp=_stamp(entry.target)) for entry in changes)
        return RenameResult(receipt, case_sensitive=plan.case_sensitive)
    except Exception as error:
        recovery = []
        # Free all published names before restoring originals, including swaps.
        locations = {entry.source: temporary for entry, temporary in stages}
        for entry, temporary in reversed(published):
            try:
                _rename_exclusive(entry.target, temporary)
            except OSError as problem:
                locations[entry.source] = entry.target
                recovery.append((entry.target, entry.source, str(problem)))
        for entry, temporary in reversed(stages):
            current = locations[entry.source]
            if current != temporary:
                continue
            try:
                _rename_exclusive(temporary, entry.source)
            except OSError as problem:
                recovery.append((temporary, entry.source, str(problem)))
        return RenameResult(cancelled=isinstance(error, RenameCancelled), error=str(error), recovery=tuple(recovery))


def undo_renames(receipt, **kwargs):
    """Undo a successful batch if its files and original destinations are still unchanged."""
    entries = tuple(RenameEntry(entry.target, entry.source, entry.stamp) for entry in receipt.entries)
    return apply_renames(_validate_entries(entries, receipt.case_sensitive), **kwargs)
