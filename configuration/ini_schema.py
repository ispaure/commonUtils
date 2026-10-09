"""Optional typed-key convention for INI configuration; INIFile stays string-valued."""
import csv
import json
import math
import re

TYPES = ('list-str', 'list-int', 'list-float', 'list-bool', 'float', 'bool', 'int', 'str', 'mode')


def key_type(key):
    for kind in TYPES:
        if key.endswith('_' + kind):
            return key[:-len(kind)-1], kind
    return key, 'str'


def string_list(value):
    try:
        result = json.loads(value)
    except json.JSONDecodeError:
        # Permit the compact [choiceA,choiceB] notation for string choices.
        if not value.strip().startswith('[') or not value.strip().endswith(']'):
            raise ValueError('Use a list such as ["one", "two"]') from None
        interior = value.strip()[1:-1]
        if any(c in interior for c in '[]{}'):
            raise ValueError('Nested lists are unsupported')
        result = next(csv.reader([interior], skipinitialspace=True)) if interior.strip() else []
        result = [item.strip() for item in result]
    if not isinstance(result, list) or not all(isinstance(item, str) for item in result):
        raise ValueError('Expected a list of strings')
    return result


def parse_value(kind, value, *, choices=None):
    if kind == 'str':
        return value
    if kind == 'mode':
        if choices is not None and value not in choices:
            raise ValueError('Choose one of the configured options')
        return value
    if kind == 'bool':
        if value.lower() not in ('true', 'false', 'yes', 'no', 'on', 'off', '1', '0'):
            raise ValueError('Expected true or false')
        return value.lower() in ('true', 'yes', 'on', '1')
    if kind == 'int':
        if not re.fullmatch(r'[+-]?\d+', value.strip()):
            raise ValueError('Expected a whole number')
        return int(value)
    if kind == 'float':
        result = float(value)
        if not math.isfinite(result):
            raise ValueError('Expected a finite number')
        return result
    if kind == 'list-str':
        return string_list(value)
    if kind.startswith('list-'):
        try:
            result = json.loads(value)
        except json.JSONDecodeError:
            raise ValueError('Expected a JSON list') from None
        scalar = kind[5:]
        if not isinstance(result, list) or any(
                type(item) not in {'int': (int,), 'float': (int, float), 'bool': (bool,)}[scalar]
                for item in result):
            raise ValueError('Expected a list of ' + scalar + ' values')
        if scalar == 'float' and not all(math.isfinite(item) for item in result):
            raise ValueError('Expected finite numbers')
        return result
    raise ValueError('Unsupported setting type: ' + kind)


def mode_choices(key, values):
    base, kind = key_type(key)
    companion = base + '_choices_list-str'
    return string_list(values[companion]) if kind == 'mode' and companion in values else None


def validate_values(parser):
    sections = (['DEFAULT'] if parser.defaults() else []) + parser.sections()
    for section in sections:
        values = dict(parser[section])
        for key, value in values.items():
            try:
                parse_value(key_type(key)[1], value, choices=mode_choices(key, values))
            except (ValueError, OverflowError) as error:
                raise ValueError(f'[{section}] {key}: {error}') from error
