"""Filtered filesystem traversal without following directory links.

Unlike Directory.list_files(), this scanner does not resolve registered file types.
max_depth=0 means unlimited; max_depth=1 includes immediate subfolder contents.
Cancellation raises OperationCancelled.
"""
from pathlib import Path
import fnmatch
import os
import re
import stat
from .operations import OperationCancelled


def natural_path_key(path):
    return tuple(int(part) if part.isdigit() else part.casefold()
                 for part in re.split(r'(\d+)', str(path)))


def scan_directory(directory, *, mask='*', files=True, folders=False, hidden=False,
                   recursive=False, max_depth=0, regex=False, match_case=False,
                   cancelled=lambda: False):
    """List candidates without following directory symlinks. max_depth=0 means unlimited."""
    root = Path(directory).resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(str(root))
    pattern = re.compile(mask, 0 if match_case else re.IGNORECASE) if regex else None
    matches = []
    stack = [(root, 0)]
    while stack:
        if cancelled():
            raise OperationCancelled('Folder scan cancelled')
        parent, depth = stack.pop()
        with os.scandir(parent) as iterator:
            for entry in iterator:
                if cancelled():
                    raise OperationCancelled('Folder scan cancelled')
                if not hidden:
                    info = entry.stat(follow_symlinks=False)
                    hidden_flags = (getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_HIDDEN', 0)
                                    or getattr(info, 'st_flags', 0) & getattr(stat, 'UF_HIDDEN', 0))
                    if entry.name.startswith('.') or hidden_flags:
                        continue
                directory = entry.is_dir(follow_symlinks=False)
                accepted = bool(pattern.search(entry.name)) if pattern else fnmatch.fnmatchcase(
                    entry.name if match_case else entry.name.casefold(), mask if match_case else mask.casefold())
                if accepted and ((directory and folders) or (not directory and files)):
                    matches.append(Path(entry.path))
                if recursive and directory and (not max_depth or depth < max_depth):
                    stack.append((Path(entry.path), depth + 1))
    return sorted(matches, key=natural_path_key)
