"""Virtual identifiers are slash-delimited names, independent of local paths."""

def resource_path(value):
    value = str(value)
    if value in {'', '.'}:
        return ''
    if (value.startswith('/') or '\\' in value or ':' in value
            or any(ord(c) < 32 for c in value)
            or any(p in {'', '.', '..'} for p in value.split('/'))):
        raise ValueError('Choose a relative path without empty, dot or parent components.')
    return value


def resource_name(value):
    """Validate one child identifier returned by a provider listing."""
    name = resource_path(value)
    if not name or "/" in name:
        raise ValueError("Invalid child name.")
    return name
