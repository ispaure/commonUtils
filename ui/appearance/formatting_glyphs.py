"""Backend-independent formatting vectors on one 24-point grid.

Qt painters and native WebView editors consume the same paths; no font or
platform symbol substitution changes their shape.
"""
from html import escape

FORMATTING_PATHS = {
    'bold': ('M6 4 L12 4 C20 4 20 12 12 12 L6 12 Z', 'M6 12 L13 12 C21 12 21 20 13 20 L6 20 Z'),
    'italic': ('M10 4 L20 4 M4 20 L14 20 M15 4 L9 20',),
    'strike': ('M18 6 C15 2 6 3 6 8 C6 11 10 12 13 12 M6 18 C9 22 18 21 18 16 C18 14 16 13 14 13 M3 12 L21 12',),
    'undo': ('M8 4 L3 9 L8 14 M3 9 L14 9 C23 9 23 20 14 20 L10 20',),
    'redo': ('M16 4 L21 9 L16 14 M21 9 L10 9 C1 9 1 20 10 20 L14 20',),
    'format': ('M3 17 L8 4 L13 17 M5 12 L11 12 M2 21 L15 21 M17 5 L22 5 M17 10 L22 10 M17 15 L22 15',),
    'heading': ('M4 5 L4 19 M14 5 L14 19 M4 12 L14 12 M18 14 L20 12 L20 20',),
    'paragraph': ('M13 4 L13 21 M18 4 L18 21 M21 4 L9 4 C1 4 1 13 9 13 L13 13',),
    'bullets': ('M4 6 L4.1 6 M4 12 L4.1 12 M4 18 L4.1 18 M9 6 L21 6 M9 12 L21 12 M9 18 L21 18',),
    'numbered': ('M3 4 L5 3 L5 9 M3 9 L7 9 M3 15 C3 12 7 12 7 15 L3 20 L7 20 M11 6 L21 6 M11 12 L21 12 M11 18 L21 18',),
    'quote': ('M4 5 L10 5 L10 12 C10 17 8 19 5 20 M4 5 L4 12 L10 12 M15 5 L21 5 L21 12 C21 17 19 19 16 20 M15 5 L15 12 L21 12',),
    'code': ('M8 6 L2 12 L8 18 M16 6 L22 12 L16 18 M14 3 L10 21',),
    'link': ('M9 15 L15 9 M8 17 L6 19 C2 23 -1 16 3 13 L7 9 C10 6 13 8 14 10 M16 7 L18 5 C22 1 25 8 21 11 L17 15 C14 18 11 16 10 14',),
    'unlink': ('M8 17 L6 19 C2 23 -1 16 3 13 L6 10 M16 7 L18 5 C22 1 25 8 21 11 L18 14 M3 3 L21 21',),
    'table': ('M3 4 L21 4 L21 20 L3 20 Z M3 9 L21 9 M3 14 L21 14 M9 4 L9 20 M15 4 L15 20',),
    'row_add': ('M3 3 L21 3 L21 15 L3 15 Z M3 9 L21 9 M10 3 L10 15 M8 21 L16 21 M12 17 L12 23',),
    'column_add': ('M3 3 L15 3 L15 21 L3 21 Z M9 3 L9 21 M3 10 L15 10 M21 8 L21 16 M17 12 L23 12',),
    'row_delete': ('M3 3 L21 3 L21 15 L3 15 Z M3 9 L21 9 M10 3 L10 15 M8 21 L16 21',),
    'column_delete': ('M3 3 L15 3 L15 21 L3 21 Z M9 3 L9 21 M3 10 L15 10 M18 12 L23 12',),
    'table_delete': ('M3 3 L21 3 L21 20 L3 20 Z M3 9 L21 9 M9 3 L9 20 M13 12 L18 17 M18 12 L13 17',),
}


def formatting_svg(name, *, size=20):
    """Inline, current-color SVG; the containing control supplies its label."""
    paths = ''.join(f'<path d="{escape(path, quote=True)}"/>' for path in FORMATTING_PATHS[name])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="{int(size)}" height="{int(size)}" '
            'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
            'stroke-linejoin="round" aria-hidden="true" focusable="false">' + paths + '</svg>')
