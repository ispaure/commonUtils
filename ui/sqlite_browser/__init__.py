"""Qt SQLite inspection and explicit editing of local database resources."""

__all__ = ['SQLiteBrowser']


def __getattr__(name):
    if name == 'SQLiteBrowser':
        from .window import SQLiteBrowser
        return SQLiteBrowser
    raise AttributeError(name)
