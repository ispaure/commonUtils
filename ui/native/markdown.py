"""Offline Markdown wiki: inline browse/search, phone page switching and tablet split."""
from pathlib import Path
from uuid import uuid4
from urllib.parse import quote, unquote, urlsplit, parse_qs
from html import unescape
import json
import re

import toga
from commonUtils.ui.native.event_loop import DebouncedCallback
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from ...formats.markdown.wiki import MarkdownWiki, resolve_document_path, documentation_root
from .markdown_preview import markdown_preview
from .inline_html import set_inline_html
from ...formats.markdown.image_sources import local_image_source
from .adaptive import AdaptiveSidebar, allocated_width
from .presentation import hierarchy_row, navigation_button


class MarkdownWikiView:
    def __init__(self, directory, path=None, *, width=390, font_size=16, render=None, open_file=None, image_source_factory=None):
        self.open_file = open_file
        self.font_size = font_size
        self.render = render or markdown_preview
        self.image_source_factory = image_source_factory or (local_image_source if render is None else None)
        self.catalog = MarkdownWiki(directory)
        self.history = []
        self.history_index = -1
        self.path = None
        self.url_prefix = '/wiki/' + uuid4().hex + '/'
        self.base = 'https://markdown.invalid' + self.url_prefix
        self.expanded = set()
        self.reading = False
        self.pending_fragment = ''
        self.wide = None
        self.search = toga.TextInput(placeholder='Search documentation', on_change=DebouncedCallback(self.filter),
                                     style=Pack(height=48))
        self.mode = toga.Selection(items=['File names & titles', 'Page text'],
                                   on_change=self.filter, style=Pack(height=48))
        self.rows = toga.Box(style=Pack(direction=COLUMN))
        self.notice = toga.Label('')
        self.browse = toga.Box(children=[toga.Label('Documentation Library'), self.search,
            toga.ScrollContainer(content=self.rows, horizontal=False, style=Pack(flex=1))],
            style=Pack(direction=COLUMN, flex=1))
        self.web = toga.WebView(on_navigation_starting=self.follow_link,
                                on_webview_load=self.page_loaded, style=Pack(flex=1))
        self.title = toga.Label('Documentation', style=Pack(margin_bottom=8))
        self.article = toga.Box(children=[self.title, self.web], style=Pack(direction=COLUMN, flex=1))
        from .markdown_search import MarkdownPageSearch
        self.page_search = MarkdownPageSearch(self.web, self.article, insertion_index=1)
        self.page_search.button.on_press = self.show_page_search

        self.sidebar = AdaptiveSidebar(self.browse, self.article, width=max(0, width - 24),
                                       label='Documentation folders and search')
        self.browse_button = self.sidebar.menu_button
        self.browse_button.on_press = self.toggle_browse
        self.content = self.sidebar.view
        self.back_button = navigation_button('back', 'Back', on_press=self.back, enabled=False)
        self.forward_button = navigation_button('forward', 'Forward', on_press=self.forward, enabled=False)
        self.up_button = navigation_button('up', 'Up to parent folder page', on_press=self.up, enabled=False)
        self.navigation = navigation = toga.Box(children=[self.browse_button, self.page_search.button, self.back_button, self.forward_button, self.up_button],
                              style=Pack(direction=ROW))
        self.view = toga.Box(children=[navigation, self.content], style=Pack(direction=COLUMN, flex=1, margin=12))
        self.reflow(width)
        self.filter()
        initial = Path(path).resolve() if path is not None else self.catalog.first_page
        if initial:
            self.open_page(initial)
        else:
            self.show_browse()

    def reflow(self, width):
        # The root owns twelve-point margins on each side. Its parent allocation
        # already accounts for native safe areas, rails and any enclosing pane.
        available = max(0, allocated_width(self.view, width) - 24)
        self.sidebar.reflow(available)
        self.wide = self.sidebar.expanded
        # A hidden scroll subtree can retain its intrinsic minimum on iOS when
        # reparented into the phone browse view. Bind content to the viewport.
        self.rows.style.width = self.sidebar.policy.sidebar_width if self.wide else available
        if self.wide and self.browse_button in self.navigation.children:
            self.navigation.remove(self.browse_button)
        elif not self.wide and self.browse_button not in self.navigation.children:
            self.navigation.insert(0, self.browse_button)

    def layout(self):
        self._sync_notice()
        if self.reading:
            self.sidebar.show_detail()
        else:
            self.sidebar.show_sidebar()

    def toggle_browse(self, widget=None, **kwargs):
        self.sidebar.toggle()
        self.reading = not self.sidebar.sidebar_open

    def show_browse(self, widget=None, **kwargs):
        self._sync_notice()
        self.reading = False
        self.sidebar.show_sidebar()

    def filter(self, widget=None, **kwargs):
        if not hasattr(self, 'rows'):
            return
        self.rows.clear()
        query = self.search.value or ''
        searching = bool(query.strip())
        if searching and self.mode not in self.browse.children:
            self.browse.insert(2, self.mode)
        elif not searching and self.mode in self.browse.children:
            self.browse.remove(self.mode)
        if hasattr(self, 'page_search'):
            self.page_search.set_library_query(query)
        mode = 'content' if self.mode.value == 'Page text' else 'filename'
        entries = self.catalog.search(query, mode)
        self.notice.text = ('No matching pages.' if not entries else
            (f'{len(self.catalog.errors)} pages or folders could not be read.' if self.catalog.errors else ''))
        self._sync_notice()
        def add(entries, depth=0):
            for entry in entries:
                toggle = None
                if entry.children:
                    def toggle(widget, entry=entry, **kwargs):
                        if entry.location in self.expanded:
                            self.expanded.remove(entry.location)
                        else:
                            self.expanded.add(entry.location)
                        self.filter()
                def choose(widget, entry=entry, **kwargs):
                    if entry.page:
                        self.open_page(entry.page)
                    elif entry.location in self.expanded:
                        self.expanded.remove(entry.location)
                        self.filter()
                    else:
                        self.expanded.add(entry.location)
                        self.filter()
                row = hierarchy_row(('✓ ' if entry.page == self.path else '') + entry.title,
                    depth=depth, expanded=bool(query or entry.location in self.expanded) if entry.children else None,
                    on_toggle=toggle, on_activate=choose, selected=entry.page == self.path)
                self.rows.add(row)
                if query or entry.location in self.expanded:
                    add(entry.children, depth + 1)
        add(entries)

    def _sync_notice(self):
        if self.notice.text and self.notice not in self.browse.children:
            self.browse.insert(len(self.browse.children) - 1, self.notice)
        elif not self.notice.text and self.notice in self.browse.children:
            self.browse.remove(self.notice)

    def show_page_search(self, widget=None, **kwargs):
        if self.path is not None:
            self.reading = True
            self.layout()
            self.page_search.show()

    def open_page(self, path, *, remember=True, linked=False, fragment=''):
        path = Path(path).resolve()
        if path not in self.catalog.pages and not (linked and path.suffix.lower() in ('.md', '.markdown')):
            self.notice.text = 'That page is outside this documentation folder or unavailable.'
            self.reading = False
            self.layout()
            return False
        try:
            from ...filesystem.local_access import check_local_path
            check_local_path(path)
            text = path.read_text(encoding='utf-8-sig')
            options = dict(local_links=True)
            if self.image_source_factory is not None:
                root = documentation_root(path, self.catalog.root)
                options['image_source'] = self.image_source_factory(path, root)
            html = self.render(text, self.font_size, **options)
        except (OSError, UnicodeError, ValueError) as error:
            self.notice.text = str(error)
            self.reading = False
            self.layout()
            return False
        root = documentation_root(path, self.catalog.root)
        if root != self.catalog.root:
            self.catalog = MarkdownWiki(root)
            self.expanded.clear()
            self.search.value = ''
        if remember and path != self.path:
            del self.history[self.history_index + 1:]
            self.history.append(path)
            self.history_index = len(self.history) - 1
        self.path = path
        self.expanded.update(folder for folder in path.parents if folder == self.catalog.root or self.catalog.root in folder.parents)
        self.update_navigation()
        self.url_prefix = '/wiki/' + uuid4().hex + '/'
        self.base = 'https://markdown.invalid' + self.url_prefix + quote(path.name)
        # Encode destinations rather than letting WebView normalize ../ past
        # the synthetic render URL. The source page remains the resolution base.
        html = re.sub(r'href="([^"]*)"', lambda match:
                      'href="' + self.base + '?target=' + quote(unescape(match[1]), safe='') + '"', html)
        self.pending_fragment = fragment
        self.page_search.loading()
        set_inline_html(self.web, self.base, html)
        self.title.text = self.catalog.title(text, path.stem)
        self.reading = True
        self.filter()
        self.layout()
        return True

    def scroll_fragment(self, fragment):
        # Host-evaluated code only; fragment text is serialized as data. Android
        # ignores set_content's base URL, so native # navigation is not portable.
        self.web.evaluate_javascript('(function(){const heading=document.getElementById('
            + json.dumps(unquote(fragment)) + ');if(heading)heading.scrollIntoView();})()')

    def page_loaded(self, widget=None, **kwargs):
        self.page_search.loaded(reveal=not bool(self.pending_fragment))
        if self.pending_fragment:
            fragment, self.pending_fragment = self.pending_fragment, ''
            self.scroll_fragment(fragment)

    def update_navigation(self):
        self.page_search.button.enabled = self.path is not None
        self.back_button.enabled = self.history_index > 0
        self.forward_button.enabled = 0 <= self.history_index < len(self.history) - 1
        self.up_button.enabled = self.catalog.parent_page(self.path) is not None

    def navigate_history(self, offset):
        index = self.history_index + offset
        if not 0 <= index < len(self.history):
            return False
        if not self.open_page(self.history[index], remember=False, linked=True):
            return False
        self.history_index = index
        self.update_navigation()
        return True

    def back(self, widget=None, **kwargs):
        return self.navigate_history(-1)

    def forward(self, widget=None, **kwargs):
        return self.navigate_history(1)

    def up(self, widget=None, **kwargs):
        target = self.catalog.parent_page(self.path)
        return self.open_page(target) if target is not None else False

    def follow_link(self, widget, url, **kwargs):
        parsed = urlsplit(url)
        if not parsed.scheme and not parsed.netloc:
            target = url
        elif (parsed.scheme == 'https' and parsed.netloc == 'markdown.invalid'
              and parsed.path.startswith(self.url_prefix)):
            target = parse_qs(parsed.query).get('target', [None])[0]
            if target is None:
                if parsed.fragment and url.split('#')[0] == self.base:
                    self.scroll_fragment(parsed.fragment)
                return False
        else:
            return False
        relative = urlsplit(target)
        if relative.scheme or relative.netloc or relative.path.startswith('/') or self.path is None:
            return False
        if not relative.path:
            if relative.fragment:
                self.scroll_fragment(relative.fragment)
            return False
        try:
            from ...filesystem.local_access import check_local_path
            candidate = (self.path.parent / unquote(relative.path)).resolve()
            check_local_path(candidate)
            path = resolve_document_path(candidate)
            check_local_path(path)
            if path.suffix.lower() in ('.md', '.markdown'):
                self.open_page(path, linked=True, fragment=relative.fragment)
            elif self.open_file is not None:
                from ...persistence.text import is_text_path
                if not is_text_path(path):
                    raise ValueError('The linked file is not a text file.')
                self.open_file(path)
            else:
                raise ValueError('This host has no text editor for linked files.')
        except (OSError, ValueError) as error:
            self.notice.text = str(error)
            self.show_browse()
        return False
