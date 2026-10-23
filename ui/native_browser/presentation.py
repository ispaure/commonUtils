"""Native list/tile browser over the portable browse tree; no Qt or disk probes."""
import asyncio
import inspect
from threading import Event

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .lifecycle import BrowserLifecycle
from ...runtime.browsing import BrowseEntry, BrowseTree, BrowseHistory, provider_entries, query_entries


def clear_box(box):
    for child in list(box.children):
        box.remove(child)


class NativeBrowser:
    """A bounded native presentation. Hosts own storage, navigation and rich data."""
    def __init__(self, *, selected=None, open_folder=None, navigate=None, thumbnail=None, details=None, preview=True,
                 resource_search=None):
        self.resource_search = resource_search
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
        self.work = BrowserLifecycle()
        from .paginated import PaginatedRenderer
        self.renderer = PaginatedRenderer()
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
        self.closed = self.work.closed = False
        # Only retain covers that this snapshot certifies as unchanged.
        valid = {(entry.identity, entry.revision) for entry in tree.entries.values() if entry.revision is not None}
        self.work.prune(valid)
        self.tree = tree
        self.page = 0
        self.selected = None
        clear_box(self.info)
        if self.on_selected:
            result = self.on_selected(None)
            if inspect.isawaitable(result):
                self._spawn(result)
        self.render()

    @property
    def epoch(self):
        return self.work.epoch

    @property
    def cancelled(self):
        return self.work.cancelled

    @property
    def tasks(self):
        return self.work.tasks

    @property
    def icons(self):
        return self.work.encoded

    def _cancel(self):
        self.work.invalidate()

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
        from ...search.providers import search_resources
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
            if len(result.rows) != published or finished:
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
            result = await asyncio.to_thread(self.resource_search or search_resources, provider, directory, query,
                                            cancelled=cancelled.is_set, progress=progress)
            publish(result, finished=True)
        except asyncio.CancelledError:
            cancelled.set()
            raise
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
        return self.work.spawn(coroutine, loop=getattr(self, '_loop', None))

    @property
    def page_size(self):
        """Maximum widgets per page; hosts can choose a larger scrolling list."""
        return 16 if self.mode == 'Tiles' else 24

    def render(self):
        self.renderer.render(self)

    async def _load_thumbnail(self, entry, image, epoch, cancelled):
        await self.work.thumbnail(entry, self.thumbnail,
                                  lambda data: setattr(image, 'image', toga.Image(src=data)),
                                  epoch=epoch, cancelled=cancelled)

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
        self.work.stop()
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
        await self.work.close()
