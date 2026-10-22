"""Viewport-bounded native browser; hosts supply appearance and workflow callbacks."""
import inspect
from functools import partial
from contextlib import contextmanager
from collections import OrderedDict
from threading import Event
from pathlib import PurePosixPath
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER
from . import NativeBrowser
from ..native.recycled_list import RecycledList, thumbnail_image
from ..native.presentation import list_button


def hidden_entry(entry):
    return bool(entry.payload.get('hidden', False) or PurePosixPath(entry.label).name.startswith('.'))


class BrowserPresentation:
    """Optional presentation hooks; no storage or application state is inspected."""
    def command(self, button, kind, label):
        button.text = {'back': '‹', 'forward': '›', 'find': 'Search', 'close': '×'}.get(kind, label)

    def command_style(self, button):
        pass

    def file_icon(self, folder):
        return None

    def entry_icon(self, folder):
        return toga.Label('📁' if folder else '📄')

    def style_button(self, button):
        list_button(button)

    def middle_filename(self, button):
        pass

    def highlight(self, widget, selected):
        widget.style.background_color = '#dce9ff' if selected else 'transparent'
        if isinstance(widget, toga.Button) and getattr(widget, 'browser_hidden', False):
            widget.style.color = '#808080'

    def bind_keyboard(self, browser):
        from ..native.keyboard import SearchDismissal
        binding = getattr(browser, '_search_dismissal', None)
        if binding is None:
            binding = browser._search_dismissal = SearchDismissal(browser.search)
        binding.bind((browser.widget,))


class RecycledBrowser(NativeBrowser):
    """Continuous recycled lists and windowed tiles over NativeBrowser snapshots."""
    @property
    def page_size(self):
        # The shared renderer also uses this for Tiles and rich previews.
        # Mobile folders and search results form one scrolling list.
        return max(1, len(self.entries))

    def __init__(self, *, open_file=None, item_actions=None, presentation=None, list_factory=None, bounded_pages=True,
                 contextual_selection=True, inline_details=True,
                 **kwargs):
        self._app = toga.App.app
        self._loop = self._app.loop
        self.bounded_pages = bounded_pages
        self._render_entries = None
        self._rendering = False
        self._list_entries = ()
        self._list_rows = {}
        self._list_indices = {}
        self._list_query = None
        self._list_thumbnail_rows = OrderedDict()
        self._tile_cards = {}
        self._tile_row_views = {}
        self._tile_range = None
        self._population_epoch = 0
        self._thumbnail_requested = set()
        self._thumbnail_pending = set()
        self._scroll = None
        self.presentation = presentation or BrowserPresentation()
        self.list_factory = list_factory or RecycledList
        self.on_open_file = open_file
        self.on_item_actions = item_actions
        super().__init__(**kwargs)
        # Keep the listing unobstructed until search is requested.
        for child in list(self.widget.children):
            self.widget.remove(child)
        self.search.placeholder = 'Search files and folders'
        self.search_panel.style.update(margin=0, align_items=CENTER)
        for control in (self.search, self.sort, self.list_button, self.tile_button, self.previous, self.next):
            control.style.height = 48
        self.presentation.command(self.back_button, 'back', 'Go back')
        self.presentation.command(self.previous, 'back', 'Previous results')
        self.presentation.command(self.next, 'forward', 'Next results')
        self.presentation.command(self.search_button, 'find', 'Search this folder')
        self.presentation.command(self.close_search_button, 'close', 'Close search')
        for control in (self.back_button, self.previous, self.next,
                        self.search_button, self.close_search_button):
            self.presentation.command_style(control)
        self.page_label.parent.remove(self.page_label)
        self.paging = toga.Box(children=[self.previous, self.next], style=Pack(direction=ROW))
        self.widget.add(toga.Box(children=[self.back_button, toga.Box(style=Pack(flex=1)),
                                          self.search_button],
                                 style=Pack(direction=ROW, margin_top=4, margin_bottom=8)))
        self.navigation_controls = self.widget.children[-1]
        self.page_label.style.update(flex=0, font_size=12, margin_bottom=6)
        self.page_label.style.font_size = 12
        self.native_list = self.list_factory(on_select=self._list_selected,
            primary_action='Select' if contextual_selection else None,
            on_primary_action=self._list_context if contextual_selection else None, on_visible=self._row_visible,
            style=Pack(flex=1))
        self.native_list.menu_provider = None
        self.empty_label = toga.Label('', style=Pack(margin=12))
        self._tile_scroll = toga.ScrollContainer(horizontal=False, content=self.items,
                                                style=Pack(flex=1))
        self._tile_scroll.on_scroll = self._tile_scrolled
        self.widget.style.flex = 1
        self.widget.add(self.native_list)
        if inline_details and self.preview_enabled:
            self.widget.add(self.info)

    def set_entries(self, provider, directory, rows, *, location=None):
        rows = tuple(rows)
        super().set_entries(provider, directory, rows, location=location)

    def set_tree(self, tree):
        self.dismiss_item_menu()
        self._population_epoch += 1
        return super().set_tree(tree)

    @property
    def entries(self):
        return self._render_entries if self._render_entries is not None else super().entries

    def render(self):
        # Resolve sorting/filtering once; list rows are lightweight source data.
        self._render_entries = self.entries
        self._rendering = True
        try:
            if self.mode == 'List':
                self._render_list()
            else:
                self.native_list.clear()
                self._mount_listing(self._tile_scroll)
                self._render_tiles()
        finally:
            self._render_entries = None
            self._rendering = False

    def scroll_container(self):
        """Return a bounded viewport; never put a native list in a ScrollContainer."""
        self._scroll = self
        return self.widget

    @property
    def vertical_position(self):
        if self.mode != 'List':
            return self._tile_scroll.vertical_position
        getter = getattr(self.native_list._impl, 'get_vertical_position', None)
        return getter() if getter is not None else 0

    @vertical_position.setter
    def vertical_position(self, value):
        if self.mode != 'List':
            self._tile_scroll.vertical_position = value
        else:
            setter = getattr(self.native_list._impl, 'set_vertical_position', None)
            if setter is not None:
                setter(value)

    @property
    def max_vertical_position(self):
        if self.mode != 'List':
            return self._tile_scroll.max_vertical_position
        getter = getattr(self.native_list._impl, 'get_max_vertical_position', None)
        return getter() if getter is not None else 0

    @contextmanager
    def population_paused(self):
        # Provider/navigation callers retain this scope; native lists have no
        # background population work to pause while an async listing runs.
        yield

    def _mount_listing(self, view):
        for child in (self.native_list, self._tile_scroll, self.empty_label):
            if child is not view and child in self.widget.children:
                self.widget.remove(child)
        if view not in self.widget.children:
            if self.info in self.widget.children:
                self.widget.insert(self.widget.children.index(self.info), view)
            else:
                self.widget.add(view)

    def _render_list(self):
        self._clear_tiles()
        self._cancel()
        self.page = 0
        self.previous.enabled = self.next.enabled = False
        if not self.search.value:
            self.page_label.text = ''
        self.buttons.clear()
        self.entry_rows = {}
        self._list_entries = tuple(self.entries) if not self.closed else ()
        self._list_query = (self.search.value, self.sort.value)
        self._list_thumbnail_rows.clear()
        self._thumbnail_requested.clear()
        self._thumbnail_pending.clear()
        self.native_list.observe_rows = bool(self.thumbnail)
        self.native_list.updating = True
        try:
            # Each row carries the entry object, not an index into mutable state.
            # Delayed native callbacks cannot activate a replaced folder/query.
            records = []
            for index, entry in enumerate(self._list_entries):
                records.append(dict(
                    title=entry.payload.get('display_name') or PurePosixPath(entry.label).name,
                    subtitle='', icon=self.presentation.file_icon(entry.container), folder=entry.container, entry=entry,
                    epoch=self.epoch, thumbnail=False, index=index, hidden=hidden_entry(entry)))
            # Publish lightweight rows once. Only visible cells decode images.
            self.native_list.data = records
            self._list_rows = {row.entry.identity: row for row in self.native_list.data}
            self._list_indices = {row.entry.identity: row.index for row in self.native_list.data}
            self._list_thumbnail_rows.update((row.entry.identity, row)
                for row in self.native_list.data if row.thumbnail)
            self.highlight_selection()
        finally:
            self.native_list.updating = False
        if self._list_entries:
            self._mount_listing(self.native_list)
        else:
            self.empty_label.text = ('Searching subfolders…' if getattr(self, 'searching', False)
                                     else 'No matching items.' if self.search.value else 'This folder is empty.')
            self._mount_listing(self.empty_label)
        self.presentation.bind_keyboard(self)

    def _list_selected(self, widget, **kwargs):
        if self._rendering or widget.updating:
            return
        row = widget.selection
        if row is not None and row.epoch == self.epoch:
            # Capture synchronously: an async Toga handler would read selection
            # only after another tap/source replacement could have changed it.
            self._spawn(self._activate_row(row))

    def _list_context(self, widget, row, **kwargs):
        if not self._rendering and row.epoch == self.epoch:
            self._spawn(self._select_row(row))

    async def _select_row(self, row):
        if (not self.closed and not self.navigation_busy and row.epoch == self.epoch
                and self._list_rows.get(row.entry.identity) is row and self._entry_current(row.entry)):
            await self.select(row.entry)
            if (self.on_item_actions is not None and row.epoch == self.epoch
                    and self._entry_current(row.entry) and self.selected == row.entry.identity):
                result = self.on_item_actions(row.entry.payload)
                if inspect.isawaitable(result):
                    await result

    async def _activate_row(self, row):
        if row.epoch == self.epoch and self._list_rows.get(row.entry.identity) is row:
            await self._select_pressed(row.entry, self.native_list)

    async def activate_entry(self, entry):
        """Activate a current entry through the same guarded path as a native tap."""
        await self._select_pressed(entry, self.native_list)

    def _entry_current(self, entry):
        if self.tree is None or self.tree.entries.get(entry.identity) is not entry:
            return False
        if self.mode == 'List':
            return (self._list_query == (self.search.value, self.sort.value)
                    and entry.identity in self._list_rows)
        return entry.identity in self.buttons

    def _set_row_thumbnail(self, row, image):
        key = row.entry.identity, row.entry.revision
        decoded = self.work.decoded.get(key)
        if decoded is None:
            decoded = thumbnail_image(image, size=self.native_list.icon_size)
            self.work.decoded[key] = decoded
        self.work.decoded.move_to_end(key)
        while len(self.work.decoded) > 64:
            self.work.decoded.popitem(last=False)
        row.thumbnail = True
        row.icon = decoded
        self._list_thumbnail_rows[row.entry.identity] = row
        self._list_thumbnail_rows.move_to_end(row.entry.identity)
        while len(self._list_thumbnail_rows) > 64:
            identity, previous = self._list_thumbnail_rows.popitem(last=False)
            previous.thumbnail = False
            previous.icon = self.presentation.file_icon(previous.folder)
            self._thumbnail_requested.discard(identity)

    def _row_visible(self, row):
        if (self.closed or self.mode != 'List' or row.epoch != self.epoch
                or row.folder or not self.thumbnail or row.thumbnail
                or row.entry.identity in self._thumbnail_requested
                or len(self._thumbnail_pending) >= 24):
            return
        self._thumbnail_requested.add(row.entry.identity)
        decoded = self.work.decoded.get((row.entry.identity, row.entry.revision))
        if decoded is not None:
            self._set_row_thumbnail(row, decoded)
            return
        cached = self.icons.get((row.entry.identity, row.entry.revision))
        if cached:
            self._set_row_thumbnail(row, toga.Image(src=cached))
            return
        token = (row.epoch, row.entry.identity)
        self._thumbnail_pending.add(token)
        self._spawn(self._load_list_thumbnail(row, token))

    async def _load_list_thumbnail(self, row, token):
        browser = self
        class Target:
            @property
            def image(self):
                return row.icon
            @image.setter
            def image(self, image):
                if (not browser.closed and row.epoch == browser.epoch and browser.mode == 'List'
                        and browser._list_rows.get(row.entry.identity) is row):
                    browser._set_row_thumbnail(row, image)
        try:
            await self._load_thumbnail(row.entry, Target(), row.epoch, self.cancelled)
        finally:
            self._thumbnail_pending.discard(token)

    def stop(self):
        self.dismiss_item_menu()
        self._clear_tiles()
        self.work.decoded.clear()
        self.native_list.clear()
        self._list_entries = ()
        self._list_rows.clear()
        self._list_indices.clear()
        self._list_thumbnail_rows.clear()
        self._thumbnail_requested.clear()
        self._thumbnail_pending.clear()
        super().stop()
        binding = getattr(self, '_search_dismissal', None)
        if binding is not None:
            binding.dispose()
            self._search_dismissal = None
        self.entry_rows = {}

    def dismiss_item_menu(self):
        menu = getattr(self, '_item_menu', None)
        if menu is not None:
            menu.dispose()
            self._item_menu = None

    TILE_ROW_HEIGHT = 164

    def _clear_tiles(self):
        restore = getattr(self, '_tile_restore', None)
        if restore is not None:
            restore.cancel()
        self._tile_entries = ()
        for identity in tuple(self._tile_cards):
            self._retire_tile(identity)
        self._tile_row_views.clear()
        rows = getattr(self, '_tile_rows', None)
        if rows is not None:
            for child in list(rows.children):
                rows.remove(child)
        self._tile_rows = None
        self._tile_range = None
        if hasattr(self, 'items'):
            for child in list(self.items.children):
                self.items.remove(child)

    def _render_tiles(self):
        if self.closed:
            return
        self._cancel()
        self._clear_tiles()
        self.buttons.clear()
        self.entry_rows = {}
        self._tile_entries = tuple(self.entries)
        self._tile_top = toga.Box(style=Pack(height=0))
        self._tile_rows = toga.Box(style=Pack(direction=COLUMN))
        self._tile_bottom = toga.Box(style=Pack(height=0))
        self.items.add(self._tile_top, self._tile_rows, self._tile_bottom)
        if not self._tile_entries:
            self._tile_rows.add(toga.Label('No matching items.' if self.search.value else 'This folder is empty.'))
        else:
            self._update_tile_window(0)
        self.page_label.text = ''

    def _tile_scrolled(self, widget, **kwargs):
        if not self.closed and self.mode == 'Tiles' and not getattr(self, '_tile_updating', False):
            self._tile_scroll_serial = getattr(self, '_tile_scroll_serial', 0) + 1
            self._update_tile_window(widget.vertical_position)

    def _update_tile_window(self, position):
        entries = self._tile_entries
        total = (len(entries) + 1) // 2
        if not total:
            return
        height = self._tile_scroll.layout.content_height or self._app.main_window.size.height or 640
        count = min(40, max(6, int(height / self.TILE_ROW_HEIGHT) + 5))
        start = min(max(0, total - count), max(0, int(position / self.TILE_ROW_HEIGHT) - 2))
        end = min(total, start + count)
        if self._tile_range == (start, end):
            return
        self._tile_range = start, end
        self._tile_updating = True
        try:
            for row_index in set(self._tile_row_views) - set(range(start, end)):
                self._tile_rows.remove(self._tile_row_views.pop(row_index))
                for entry in entries[row_index * 2:row_index * 2 + 2]:
                    self._retire_tile(entry.identity)
            self._tile_top.style.height = start * self.TILE_ROW_HEIGHT
            self._tile_bottom.style.height = (total - end) * self.TILE_ROW_HEIGHT
            for offset, row_index in enumerate(range(start, end)):
                if row_index in self._tile_row_views:
                    continue
                row = toga.Box(style=Pack(direction=ROW, height=self.TILE_ROW_HEIGHT))
                for entry in entries[row_index * 2:row_index * 2 + 2]:
                    row.add(self._tile_card(entry))
                if len(row.children) == 1:
                    row.add(toga.Box(style=Pack(flex=1)))
                self._tile_row_views[row_index] = row
                self._tile_rows.insert(offset, row)
            self.highlight_selection()
            self.presentation.bind_keyboard(self)
        finally:
            self._tile_updating = False
        epoch, serial = self.epoch, getattr(self, '_tile_scroll_serial', 0)
        def restore():
            if (not self.closed and self.mode == 'Tiles' and self.epoch == epoch
                    and self._tile_range == (start, end)
                    and getattr(self, '_tile_scroll_serial', 0) == serial):
                # The total extent is unchanged. Avoid clamping to a stale
                # native maximum while the recycled rows are being laid out.
                self._tile_scroll._impl.set_position(0, int(position))
        self._tile_restore = self._loop.call_soon(restore)

    def _retire_tile(self, identity):
        _, card, button, cancelled, _ = self._tile_cards.pop(identity)
        # Cancelling the awaiter cannot stop its to_thread storage read. Keep
        # lifecycle ownership and its concurrency slot until that read retires.
        cancelled.set()
        button.text = ''
        for view in card.children[0].children:
            if isinstance(view, toga.ImageView):
                view.image = None
        self.buttons.pop(identity, None)
        self.entry_rows.pop(identity, None)

    def _tile_card(self, entry):
        preview = toga.ImageView(style=Pack(width=96, height=96)) if self.thumbnail and not entry.container else self.presentation.entry_icon(entry.container)
        image_box = toga.Box(children=[preview], style=Pack(height=96, align_items='center', justify_content='center'))
        button = toga.Button(entry.payload.get('display_name') or PurePosixPath(entry.label).name,
            on_press=partial(self._select_pressed, entry), style=Pack(height=44))
        button.browser_hidden = hidden_entry(entry)
        self.presentation.style_button(button)
        self.presentation.middle_filename(button)
        card = toga.Box(children=[image_box, button], style=Pack(direction=COLUMN, flex=1, margin=4))
        cancelled = Event()
        task = None
        cached = self.icons.get((entry.identity, entry.revision))
        if cached and self.thumbnail and not entry.container:
            preview.image = toga.Image(src=cached)
        elif self.thumbnail and not entry.container:
            browser, epoch = self, self.epoch
            class Target:
                @property
                def image(self):
                    return preview.image
                @image.setter
                def image(self, image):
                    if (not cancelled.is_set() and not browser.closed and browser.epoch == epoch
                            and entry.identity in browser._tile_cards):
                        preview.image = image
            task = self.work.spawn(self._load_thumbnail(entry, Target(), epoch, cancelled), loop=self._loop)
        self._tile_cards[entry.identity] = entry, card, button, cancelled, task
        self.buttons[entry.identity] = button
        self.entry_rows[entry.identity] = card
        return card

    async def _select_pressed(self, entry, widget, **kwargs):
        with self.population_paused():
            if self.closed or self.navigation_busy or not self._entry_current(entry):
                return
            if entry.container and self.on_open_folder:
                self.navigation_busy = True
                try:
                    result = self.on_open_folder(entry.payload)
                    if inspect.isawaitable(result):
                        await result
                finally:
                    self.navigation_busy = False
                return
            if not entry.container and self.on_open_file and not self.closed:
                tree = self.tree
                self.navigation_busy = True
                try:
                    # A file tap opens the document. Do not first read its archive
                    # metadata (or queue behind thumbnail workers) for the browser's
                    # information panel, which is about to leave the screen.
                    self.selected = entry.identity
                    for child in list(self.info.children):
                        self.info.remove(child)
                    self.highlight_selection()
                    if self.on_selected:
                        selected = self.on_selected(entry.payload)
                        if inspect.isawaitable(selected):
                            await selected
                    if (self.closed or self.tree is not tree or self.selected != entry.identity
                            or not self._entry_current(entry)):
                        return
                    result = self.on_open_file(entry.payload)
                    if inspect.isawaitable(result):
                        await result
                finally:
                    self.navigation_busy = False
                return
            await super()._select_pressed(entry, widget, **kwargs)

    def highlight_selection(self):
        if self.mode == 'List':
            index = self._list_indices.get(self.selected)
            self.native_list.select_index(index)
            return
        for identity, row in getattr(self, 'entry_rows', {}).items():
            selected = identity == self.selected
            button = self.buttons[identity]
            if getattr(row, '_browser_selected', None) != selected:
                self.presentation.highlight(row, selected)
                self.presentation.highlight(button, selected)
                row._browser_selected = selected
            # The shared selection handler marks only the current button.
            # Avoid native text reads and restyling every other visible row.
            if selected:
                text = button.text
                if text.startswith('✓ '):
                    button.text = text.removeprefix('✓ ')

    async def select(self, entry):
        try:
            await super().select(entry)
        finally:
            # Selection is for contextual actions, never a multi-select checkbox.
            self.highlight_selection()
