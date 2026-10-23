"""Bounded PCRE matching with UTF-16 offsets; QtCore only, no UI objects."""

from dataclasses import dataclass
import re
from PySide6 import QtCore as qt

MATCH_LIMIT = 50000


@dataclass(frozen=True)
class Match:
    start: int
    length: int
    replacement: str


def expanded_replacement(value, match):
    def expand(token):
        group = token[1] or token[2] or token[3] or token[4]
        if group is not None:
            key = int(group) if group.isdigit() else group
            if isinstance(key, int) and key > match.lastCapturedIndex():
                raise ValueError("Replacement references a missing capture group.")
            if (
                isinstance(key, str)
                and key not in match.regularExpression().namedCaptureGroups()
            ):
                raise ValueError("Replacement references a missing named group.")
            return match.captured(key)
        return {"n": "\n", "t": "\t", "r": "\n", "\\": "\\"}.get(token[5], token[5])

    return re.sub(
        r"\\g<([^>]+)>|\\([0-9]+)|\$\{([^}]+)\}|\$([0-9]+)|\\(.)", expand, value
    )


def find_matches(
    text,
    query,
    replacement="",
    *,
    case=False,
    whole=False,
    regex=False,
    scope=None,
    cancelled=lambda: False,
):
    if not query:
        return [], False
    if len(query) > 2048:
        raise ValueError("Search pattern exceeds 2,048 characters.")
    pattern = query if regex else qt.QRegularExpression.escape(query)
    if whole:
        pattern = r"\b(?:" + pattern + r")\b"
    expression = qt.QRegularExpression(
        "(*LIMIT_MATCH=100000)(*LIMIT_DEPTH=1000)" + pattern
    )
    options = (
        qt.QRegularExpression.PatternOption.UseUnicodePropertiesOption
        | qt.QRegularExpression.PatternOption.MultilineOption
    )
    if not case:
        options |= qt.QRegularExpression.PatternOption.CaseInsensitiveOption
    expression.setPatternOptions(options)
    if not expression.isValid():
        raise ValueError(expression.errorString())
    iterator = expression.globalMatch(text, scope[0] if scope else 0)
    result = []
    while iterator.hasNext():
        if cancelled():
            return [], False
        match = iterator.next()
        start = match.capturedStart()
        length = match.capturedLength()
        if scope and start + length > scope[1]:
            if start > scope[1]:
                break
            continue
        result.append(
            Match(
                start,
                length,
                expanded_replacement(replacement, match) if regex else replacement,
            )
        )
        if len(result) >= MATCH_LIMIT:
            return result, True
    return result, False
