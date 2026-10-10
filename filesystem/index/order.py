"""Stable natural path keys, shared by index migration and scanning."""
from ..traversal import natural_path_key


def _sort_key(path):
    return _encode_sort_parts(natural_path_key(path))


def _encode_sort_parts(parts):
    result = bytearray()
    for part in parts:
        if isinstance(part, int):
            number = str(part).encode('ascii')
            result.extend(b'\x01' + len(number).to_bytes(4, 'big') + number + b'\0')
        else:
            result.extend(b'\x02' + part.encode('utf-8', 'surrogatepass') + b'\0')
    return bytes(result)


