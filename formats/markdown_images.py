"""Obsidian-compatible image size hints shared by desktop and native renderers."""
import re

_SIZE = re.compile(r'([1-9][0-9]{0,5})(?:x([1-9][0-9]{0,5}))?\Z')


def image_size(label):
    """Return (caption, width, height); invalid hints remain literal alt text."""
    caption, separator, size = label.rpartition('|')
    match = _SIZE.fullmatch(size if separator else label)
    if match is None:
        return label, None, None
    return (caption if separator else '', int(match[1]), int(match[2]) if match[2] else None)
