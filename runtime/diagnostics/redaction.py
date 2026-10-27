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


class LineRedactor:
    """Filter complete ordered lines, retaining private-key block state per stream.

    Secrets are explicit; no environment inspection or output buffering occurs.
    This is best-effort filtering, not protection for arbitrary split chunks.
    """
    def __init__(self, secrets=()):
        self.secrets = tuple(dict.fromkeys(value for value in secrets if value))
        self.private_key = False

    def __call__(self, line):
        if '-----BEGIN ' in line and 'PRIVATE KEY-----' in line:
            self.private_key = True
            return '[private key redacted]\n'
        if self.private_key:
            if '-----END ' in line and 'PRIVATE KEY-----' in line:
                self.private_key = False
            return ''
        for secret in self.secrets:
            line = line.replace(secret, '[redacted]')
        line = re.sub(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AIza[A-Za-z0-9_-]{30,})', '[redacted]', line)
        line = re.sub(r'(?i)(authorization\s*:\s*bearer\s+|(?:api[_-]?key|token|password|secret)\s*[=:]\s*)[^\s,;]+', r'\1[redacted]', line)
        return re.sub(r'(https?://)[^/\s:@]+:[^/\s@]+@', r'\1[redacted]@', line)
