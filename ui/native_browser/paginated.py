"""Explicit bounded widget renderer for supported simple native-browser callers."""
from functools import partial
import toga
from toga.style import Pack
from toga.style.pack import ROW, COLUMN
from . import clear_box


class PaginatedRenderer:
    def render(self, browser):
        if browser.closed:
            return
        browser._cancel()
        clear_box(browser.items)
        browser.buttons.clear()
        count = browser.page_size
        entries = browser.entries
        pages = max(1, (len(entries) + count - 1) // count)
        browser.page = min(browser.page, pages - 1)
        browser.page_label.text = f'{len(entries)} items · {browser.page + 1}/{pages}'
        browser.previous.enabled, browser.next.enabled = browser.page > 0, browser.page + 1 < pages
        visible = entries[browser.page * count:(browser.page + 1) * count]
        row = None
        for index, entry in enumerate(visible):
            key = entry.identity, entry.revision
            # Generic folders use the platform's text glyph. Do not allocate
            # an empty native image widget when no preview can be displayed.
            image = (toga.ImageView(style=Pack(width=96 if browser.mode == 'Tiles' else 36,
                                             height=96 if browser.mode == 'Tiles' else 36))
                     if not entry.container and (browser.thumbnail or key in browser.icons) else None)
            if image is not None and key in browser.icons:
                image.image = toga.Image(src=browser.icons[key])
                browser.icons.move_to_end(key)
            button = toga.Button(('📁 ' if entry.container else '') + entry.label,
                on_press=partial(browser._select_pressed, entry), style=Pack(height=44, flex=1))
            browser.buttons[entry.identity] = button
            if entry.identity == browser.selected:
                button.text = '✓ ' + button.text
            if browser.mode == 'Tiles':
                if index % 2 == 0:
                    row = toga.Box(style=Pack(direction=ROW))
                    browser.items.add(row)
                row.add(toga.Box(children=([image] if image is not None else []) + [button], style=Pack(direction=COLUMN, flex=1, margin=4)))
            else:
                browser.items.add(toga.Box(children=([image] if image is not None else []) + [button], style=Pack(direction=ROW, margin_bottom=3)))
            if browser.thumbnail and not entry.container and key not in browser.icons:
                browser._spawn(browser._load_thumbnail(entry, image, browser.epoch, browser.cancelled))
        if not visible:
            browser.items.add(toga.Label('No matching items.' if browser.search.value else 'This folder is empty.'))

