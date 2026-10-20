"""Native list/tile browser over the portable browse tree; no Qt or disk probes."""
import asyncio
from collections import OrderedDict
import inspect
from functools import partial
from threading import Event

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from ...runtime.browsing import BrowseEntry, BrowseTree, BrowseHistory, provider_entries, query_entries


def clear_box(box):
    for child in list(box.children):
        box.remove(child)


class NativeBrowser:
    """A bounded native presentation. Hosts own storage, navigation and rich data."""
    def __init__(self, *, selected=None, open_folder=None, navigate=None, thumbnail=None, details=None, preview=True):
        self.on_selected = selected
        self.on_open_folder, self.on_navigate = open_folder, navigate
        self.history = BrowseHistory()
        self.location = None
        self.search_provider = None
        self.search_directory = ''
        self.folder_tree = None
        self.search_epoch = 0
        self.searching = False
        self.search_cancelled = Event()
        self.navigation_busy = False
        self.back_button = toga.Button('Back', on_press=self.go_back, enabled=False, style=Pack(height=44))
        self.search = toga.TextInput(placeholder='Search this folder and its subfolders', on_change=self.query_changed, style=Pack(height=44, flex=1))
        self.sort = toga.Selection(items=['Name A–Z', 'Name Z–A', 'Size smallest', 'Size largest', 'Modified oldest', 'Modified newest'],
                                   on_change=self.query_changed, style=Pack(height=44, flex=1))
        self.thumbnail, self.details = thumbnail, details
        self.preview_enabled = preview
        self.mode, self.page = 'List', 0
        self.selected = None
        self.tree = None
        self.closed = False
        self.epoch = 0
        self.cancelled = Event()
        self.tasks = set()
        self.icons = OrderedDict()
        self.buttons = {}
        self.list_button = toga.Button('List', on_press=self.show_list, style=Pack(height=44))
        self.tile_button = toga.Button('Tiles', on_press=self.show_tiles, style=Pack(height=44))
        self.previous = toga.Button('Previous', on_press=self.previous_page, style=Pack(height=44))
        self.next = toga.Button('Next', on_press=self.next_page, style=Pack(height=44))
        self.page_label = toga.Label('')
        self.items = toga.Box(style=Pack(direction=COLUMN))
        self.info = toga.Box(style=Pack(direction=COLUMN, margin_top=8))
        self.search_button = toga.Button('Search', on_press=self.toggle_search, style=Pack(height=44))
        self.close_search_button = toga.Button('×', on_press=self.close_search, style=Pack(width=44, height=44))
        self.search_panel = toga.Box(children=[self.search, self.close_search_button], style=Pack(direction=ROW, margin_bottom=5))
        self.widget = toga.Box(children=[
            toga.Box(children=[self.back_button, self.search_button, self.page_label], style=Pack(direction=ROW, margin_bottom=5)),
            toga.Box(children=[self.list_button, self.tile_button, toga.Label('Sort', style=Pack(margin=6)), self.sort], style=Pack(direction=ROW, margin_bottom=5)),
            self.items, toga.Box(children=[self.previous, self.next], style=Pack(direction=ROW)), self.info], style=Pack(direction=COLUMN))

    def open_search(self, widget=None, **kwargs):
        if self.search_panel not in self.widget.children:
            self.widget.insert(2, self.search_panel)
        self.search.focus()

    def close_search(self, widget=None, **kwargs):
        self.search.value = ''
        if self.search_panel in self.widget.children:
            self.widget.remove(self.search_panel)

    def toggle_search(self, widget=None, **kwargs):
        if self.search_panel in self.widget.children:
            self.close_search()
        else:
            self.open_search()


    def set_entries(self, provider, directory, rows, *, location=None):
        rows = tuple(rows)
        root = provider.root / provider.relative(directory)
        tree = BrowseTree(BrowseEntry(root, root.name, True), max_entries=len(rows) + 1)
        tree.set_children(root, provider_entries(provider, rows))
        if location is not None and location != self.location:
            self.search.value = ''
        self.search_cancelled.set()
        self.search_epoch += 1
        self.searching = False
        self.search_provider, self.search_directory = provider, directory
        self.folder_tree = tree
        self.set_tree(tree)
        self.location = location
        if location is not None:
            self.history.visit(location)
        self.back_button.enabled = self.on_navigate is not None and self.history.previous() is not None

    def set_tree(self, tree):
        """Publish a prepared portable snapshot, including non-filesystem identities."""
        self._cancel()
        self.closed = False
        # Only retain covers that this snapshot certifies as unchanged.
        valid = {(entry.identity, entry.revision) for entry in tree.entries.values() if entry.revision is not None}
        self.icons = OrderedDict((key, data) for key, data in self.icons.items() if key in valid)
        self.tree = tree
        self.page = 0
        self.selected = None
        clear_box(self.info)
        if self.on_selected:
            result = self.on_selected(None)
            if inspect.isawaitable(result):
                self._spawn(result)
        self.render()

    def _cancel(self):
        self.epoch += 1
        self.cancelled.set()
        self.cancelled = Event()

    @property
    def entries(self):
        rows = [self.tree.entries[key] for key in self.tree.children.get(self.tree.root, ())] if self.tree else []
        choice = self.sort.value or 'Name A–Z'
        field = 'size' if choice.startswith('Size') else 'modified' if choice.startswith('Modified') else 'name'
        return query_entries(rows, self.search.value or '', sort=field, descending=choice in {'Name Z–A', 'Size largest', 'Modified newest'})

    def query_changed(self, widget=None, **kwargs):
        if not hasattr(self, 'items'):
            return
        if widget is self.sort:
            self.page = 0
            self.render()
            return
        self.search_cancelled.set()
        self.search_cancelled = Event()
        self.search_epoch += 1
        self.searching = False
        self._spawn(self._apply_query(self.search_epoch, self.search_cancelled))

    async def _apply_query(self, epoch, cancelled):
        await asyncio.sleep(.4)
        if self.closed or epoch != self.search_epoch or cancelled.is_set():
            return
        if self.folder_tree is not None:
            self.tree = self.folder_tree
        self.page = 0
        if self.selected is not None and not any(entry.identity == self.selected for entry in self.entries):
            self.selected = None
            clear_box(self.info)
            if self.on_selected:
                result = self.on_selected(None)
                if inspect.isawaitable(result):
                    self._spawn(result)
        self.render()
        if self.search.value and self.search_provider is not None and hasattr(self.search_provider, 'list'):
            self._spawn(self._search_subfolders(self.search_epoch, self.search_cancelled))

    async def _search_subfolders(self, epoch, cancelled):
        from ...runtime.resource_search import search_resources
        provider, directory, query = self.search_provider, self.search_directory, self.search.value
        def current():
            return not self.closed and epoch == self.search_epoch and not cancelled.is_set()
        if not current():
            return
        loop = asyncio.get_running_loop()
        published = -1
        self.searching = True
        self.render()
        self.page_label.text = 'Searching subfolders…'
        def publish(result, *, finished=False):
            nonlocal published
            if not current():
                return
            self.searching = not finished
            if len(result.rows) != published:
                root = provider.root / provider.relative(directory)
                tree = BrowseTree(BrowseEntry(root, root.name, True), max_entries=len(result.rows) + 1)
                tree.set_children(root, provider_entries(provider, result.rows))
                self.set_tree(tree)
                published = len(result.rows)
            elif finished and not result.rows:
                self.render()
            if finished:
                self.page_label.text = f'{len(result.rows)} matches'
                if not result.complete:
                    self.page_label.text += ' · Partial results'
            else:
                self.page_label.text = f'Searching… {len(result.rows)} found · {result.scanned} checked'
        def progress(result):
            loop.call_soon_threadsafe(publish, result)
        try:
            result = await asyncio.to_thread(search_resources, provider, directory, query,
                                            cancelled=cancelled.is_set, progress=progress)
            publish(result, finished=True)
        except Exception as error:
            if current():
                self.searching = False
                self.render()
                self.page_label.text = 'Search failed: ' + str(error)[:80]
        finally:
            if current():
                self.searching = False

    async def go_back(self, widget=None, **kwargs):
        if self.closed or self.navigation_busy or not self.on_navigate or self.history.previous() is None:
            return
        original = list(self.history.locations)
        self.history.locations.pop()
        self.navigation_busy = True
        self.back_button.enabled = False
        try:
            result = self.on_navigate(self.history.current)
            if inspect.isawaitable(result):
                result = await result
            if result is False:
                self.history.locations[:] = original
        except Exception:
            self.history.locations[:] = original
            raise
        finally:
            self.navigation_busy = False
            self.back_button.enabled = not self.closed and self.history.previous() is not None

    def show_list(self, widget=None, **kwargs):
        self.mode, self.page = 'List', 0
        self.render()

    def show_tiles(self, widget=None, **kwargs):
        self.mode, self.page = 'Tiles', 0
        self.render()

    def previous_page(self, widget=None, **kwargs):
        self.page = max(0, self.page - 1)
        self.render()

    def next_page(self, widget=None, **kwargs):
        self.page += 1
        self.render()

    def _spawn(self, coroutine):
        try:
            task = asyncio.get_running_loop().create_task(coroutine)
        except RuntimeError:
            coroutine.close()
            return
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    @property
    def page_size(self):
        """Maximum widgets per page; hosts can choose a larger scrolling list."""
        return 16 if self.mode == 'Tiles' else 24

    def render(self):
        if self.closed:
            return
        self._cancel()
        clear_box(self.items)
        self.buttons.clear()
        count = self.page_size
        entries = self.entries
        pages = max(1, (len(entries) + count - 1) // count)
        self.page = min(self.page, pages - 1)
        self.page_label.text = f'{len(entries)} items · {self.page + 1}/{pages}'
        self.previous.enabled, self.next.enabled = self.page > 0, self.page + 1 < pages
        visible = entries[self.page * count:(self.page + 1) * count]
        row = None
        for index, entry in enumerate(visible):
            key = entry.identity, entry.revision
            # Generic folders use the platform's text glyph. Do not allocate
            # an empty native image widget when no preview can be displayed.
            image = (toga.ImageView(style=Pack(width=96 if self.mode == 'Tiles' else 36,
                                             height=96 if self.mode == 'Tiles' else 36))
                     if not entry.container and (self.thumbnail or key in self.icons) else None)
            if image is not None and key in self.icons:
                image.image = toga.Image(src=self.icons[key])
                self.icons.move_to_end(key)
            button = toga.Button(('📁 ' if entry.container else '') + entry.label,
                on_press=partial(self._select_pressed, entry), style=Pack(height=44, flex=1))
            self.buttons[entry.identity] = button
            if entry.identity == self.selected:
                button.text = '✓ ' + button.text
            if self.mode == 'Tiles':
                if index % 2 == 0:
                    row = toga.Box(style=Pack(direction=ROW))
                    self.items.add(row)
                row.add(toga.Box(children=([image] if image is not None else []) + [button], style=Pack(direction=COLUMN, flex=1, margin=4)))
            else:
                self.items.add(toga.Box(children=([image] if image is not None else []) + [button], style=Pack(direction=ROW, margin_bottom=3)))
            if self.thumbnail and not entry.container and key not in self.icons:
                self._spawn(self._load_thumbnail(entry, image, self.epoch, self.cancelled))
        if not visible:
            self.items.add(toga.Label('No matching items.' if self.search.value else 'This folder is empty.'))

    async def _load_thumbnail(self, entry, image, epoch, cancelled):
        if not hasattr(self, '_slots'):
            self._slots = asyncio.Semaphore(2)
        async with self._slots:
            if self.closed or cancelled.is_set():
                return
            try:
                data = await asyncio.to_thread(self.thumbnail, entry.payload, (160, 160), cancelled.is_set)
                if data and not self.closed and epoch == self.epoch:
                    self.icons[entry.identity, entry.revision] = data
                    while len(self.icons) > 64:
                        self.icons.popitem(last=False)
                    while sum(map(len, self.icons.values())) > 8 * 1024 * 1024:
                        self.icons.popitem(last=False)
                    image.image = toga.Image(src=data)
            except Exception:
                pass  # Missing/locked covers leave the file name usable.

    async def _select_pressed(self, entry, widget, **kwargs):
        if self.closed or self.navigation_busy or not self.tree or entry.identity not in self.tree.entries:
            return
        await self.select(entry)
        if entry.container and self.on_open_folder:
            self.navigation_busy = True
            try:
                result = self.on_open_folder(entry.payload)
                if inspect.isawaitable(result):
                    await result
            finally:
                self.navigation_busy = False

    async def select(self, entry):
        if self.closed:
            return
        self.selected = entry.identity
        for identity, button in self.buttons.items():
            button.text = ('✓ ' if identity == entry.identity else '') + button.text.removeprefix('✓ ')
        clear_box(self.info)
        if self.on_selected:
            result = self.on_selected(entry.payload)
            if inspect.isawaitable(result):
                await result
        if not self.preview_enabled:
            return
        fields = [('Name', entry.label), ('Type', 'Folder' if entry.container else 'File')]
        size = entry.properties.get('size')
        if size is not None:
            from ...filesystem import format_size
            fields.append(('Size', format_size(size)))
        if entry.properties.get('modified'):
            fields.append(('Modified', entry.properties['modified']))
        self._fields(fields)
        if self.details and not entry.container:
            epoch, cancelled = self.epoch, self.cancelled
            task = asyncio.create_task(asyncio.to_thread(self.details, entry.payload, cancelled.is_set))
            self.tasks.add(task)
            try:
                extra = await task
                if not self.closed and epoch == self.epoch and self.selected == entry.identity:
                    self._fields(extra)
            except Exception as error:
                if not self.closed and self.selected == entry.identity:
                    self.info.add(toga.Label('Information unavailable: ' + str(error)[:160]))
            finally:
                self.tasks.discard(task)

    def _fields(self, fields):
        for label, value in fields:
            text = f'{label}: {value}'
            self.info.add(toga.MultilineTextInput(value=text, readonly=True, style=Pack(height=85)) if len(text) > 100
                          else toga.Label(text, style=Pack(margin_bottom=3)))

    def stop(self):
        self.closed = True
        self._cancel()
        self.icons.clear()
        self.history.clear()
        self.location = None
        self.search_cancelled.set()
        self.search_epoch += 1
        self.search_provider = None
        self.folder_tree = None
        self.back_button.enabled = False
        self.close_search()
        self.tree = None
        self.selected = None
        self.buttons.clear()
        clear_box(self.items)
        clear_box(self.info)

    async def close(self):
        self.stop()
        if self.tasks:
            await asyncio.gather(*tuple(self.tasks), return_exceptions=True)
