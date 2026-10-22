"""Best-effort redaction of complete diagnostic text; not a secret detector.

Callers choose when to redact. Arbitrary streaming chunks can split credentials,
so sensitive operations should discard output rather than rely on this filter.
"""

import re


def redact(text: str) -> str:
    def url(match):
        scheme, remainder = match.group().split("://", 1)
        authority, separator, path = remainder.partition("/")
        if "@" in authority:
            authority = "[credentials]@" + authority.rsplit("@", 1)[1]
        value = scheme + "://" + authority + separator + path
        head, query, _ = value.partition("?")
        return head + "?[redacted]" if query else value

    # Consume each complete URL once. An unbounded scheme followed by a required
    # suffix can backtrack quadratically over long non-URL hook output.
    text = re.sub(r"[a-z][a-z0-9+.-]{0,31}://[^\s]+", url, text)
    text = re.sub(
        r"(?i)(authorization\s*[=:]\s*)(?:bearer|basic)\s+[^\s]+", r"\1[redacted]", text
    )
    return re.sub(
        r"(?i)((?:password|access_token|token|authorization)\s*[=:]\s*)[^\s]+",
        r"\1[redacted]",
        text,
    )
