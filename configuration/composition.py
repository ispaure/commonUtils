"""INI parsing policy and layer precedence, independent of UI and registration."""
from configparser import ConfigParser
from pathlib import Path


def parse_defaults(path, *, case_sensitive, allow_duplicates, normalize_after_parse):
    parser = ConfigParser(interpolation=None, strict=not allow_duplicates)
    if case_sensitive or normalize_after_parse:
        parser.optionxform = str
    parser.read_string(Path(path).read_text(encoding='utf-8-sig'))
    if normalize_after_parse and not case_sensitive:
        normalized = ConfigParser(interpolation=None)
        normalized.read_dict({section: dict(parser[section]) for section in parser.sections()})
        return normalized
    return parser


def overlay(parser, values):
    """Personal fields take precedence using the receiving parser's key policy."""
    for (section, key), value in values.items():
        if not parser.has_section(section):
            parser.add_section(section)
        parser.set(section, key, value)
    return parser
