"""Portable local Markdown documentation catalog, without GUI dependencies."""
from dataclasses import dataclass
from pathlib import Path
import re

from .properties import split_frontmatter
from ...search.text import contains_text


@dataclass(frozen=True)
class WikiEntry:
    location: Path
    title: str
    page: Path | None
    children: tuple = ()


class MarkdownWiki:
    """Accept a filesystem Directory (or path); never traverse symbolic links."""
    def __init__(self, directory):
        self.root = Path(getattr(directory, 'path', directory)).expanduser().resolve()
        if not self.root.is_dir():
            raise ValueError('Documentation directory does not exist: ' + str(self.root))
        self.errors = []
        self.pages = {}
        self.entries = self._folder(self.root)
        landing = self.folder_page(self.root)
        if landing is not None and landing.stem == self.root.name:
            children = tuple(entry for entry in self.entries if entry.page != landing)
            self.entries = (WikiEntry(self.root, self.title(self.pages[landing], self.root.name), landing, children),)

    def _read(self, path):
        try:
            if path.stat().st_size > 1024 * 1024:
                raise ValueError('Page exceeds 1 MiB')
            return path.read_text(encoding='utf-8-sig')
        except (OSError, UnicodeError, ValueError) as error:
            self.errors.append(f'{path.name}: {error}')
            return ''

    @staticmethod
    def title(text, fallback):
        # A title may follow Obsidian/YAML properties and separating blank
        # lines, but never scan past introductory body text or into YAML.
        parts = split_frontmatter(text.lstrip('\ufeff'))
        lines = parts.body.splitlines()
        first = next((index for index, line in enumerate(lines) if line.strip()), len(lines))
        lines = lines[first:]
        if lines:
            match = re.fullmatch(r'#{1,6}\s+(.+?)(?:\s+#+)?\s*', lines[0])
            if match:
                return match[1]
            if len(lines) > 1 and lines[0].strip() and re.fullmatch(r'(?:=+|-+)\s*', lines[1]):
                return lines[0].strip()
        return fallback

    def _folder(self, folder):
        try:
            children = sorted((p for p in folder.iterdir() if not p.is_symlink() and not p.is_junction() and not p.name.startswith('.')),
                              key=lambda p: (not p.is_dir(), p.name.casefold()))
        except OSError as error:
            self.errors.append(str(error))
            return ()
        result = []
        for path in children:
            if path.is_dir():
                nested = self._folder(path)
                landing = next((p for p in children_for(nested)
                                if p.parent == path and p.stem == path.name), None)
                title = self.title(self.pages[landing], path.name) if landing else path.name
                nested = tuple(e for e in nested if e.page != landing or e.children)
                if nested or landing:
                    result.append(WikiEntry(path, title, landing, nested))
            elif path.suffix.lower() in ('.md', '.markdown'):
                text = self._read(path)
                self.pages[path] = text
                result.append(WikiEntry(path, self.title(text, path.stem), path))
        return tuple(result)

    def search(self, query='', mode='filename'):
        """Return a pruned hierarchy, retaining ancestors of matching pages."""
        query = query.casefold().strip()
        def prune(entries):
            result = []
            for entry in entries:
                nested = prune(entry.children)
                value = (self.pages.get(entry.page, '') if mode == 'content' else
                         ' '.join((entry.location.name, entry.title, entry.page.name if entry.page else '')))
                if not query or contains_text(value, query) or nested:
                    result.append(WikiEntry(entry.location, entry.title, entry.page, nested))
            return tuple(result)
        return prune(self.entries)

    def folder_page(self, folder):
        """Return a same-named landing page; root also accepts README/index."""
        folder = Path(folder).resolve()
        if folder != self.root and self.root not in folder.parents:
            return None
        named = sorted((path for path in self.pages if path.parent == folder and path.stem == folder.name),
                       key=lambda path: (path.suffix.lower() != '.md', path.name))
        if named:
            return named[0]
        names = []
        if folder == self.root:
            names.extend(('README.md', 'index.md'))
        return next((folder / name for name in names if folder / name in self.pages), None)

    def parent_page(self, path):
        """Up from an article opens its folder; Up from a landing opens its parent."""
        if path is None:
            return None
        path = Path(path).resolve()
        if path not in self.pages:
            return None
        folder = path.parent
        if path == self.folder_page(folder):
            folder = folder.parent
        return self.folder_page(folder)

    @property
    def first_page(self):
        return self.folder_page(self.root) or next(iter(self.pages), None)


def children_for(entries):
    for entry in entries:
        if entry.page:
            yield entry.page


def resolve_document_path(path):
    """Resolve an explicit local link, including extensionless Markdown/folders."""
    path = Path(path).resolve()
    if path.is_dir():
        candidates = (path / (path.name + '.md'), path / (path.name + '.markdown'),
                      path / 'README.md', path / 'index.md')
    elif not path.exists() and not path.suffix:
        candidates = (path.with_suffix('.md'), path.with_suffix('.markdown'))
    else:
        candidates = (path,)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f'Linked document does not exist: {path}')


def documentation_root(path, fallback=None):
    """Find an explicit docs/docs.md wiki scope; retain custom roots within it.

    Following a link into another conventional wiki switches its file tree. Pages
    in custom catalogs keep their supplied root; a linked standalone document
    outside that root falls back to its containing directory. No links are walked.
    """
    path = Path(path).resolve()
    for folder in path.parents:
        if folder.name == 'docs' and (folder / 'docs.md').is_file():
            return folder
    sibling_scope = path.parent / 'docs'
    if (sibling_scope / 'docs.md').is_file():
        return sibling_scope
    if fallback is not None:
        fallback = Path(fallback).resolve()
        if path == fallback or fallback in path.parents:
            return fallback
    return path.parent
