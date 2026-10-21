"""Recycled mobile rows: UITableView on iOS and a ListView adapter on Android.

Toga 0.5.7's Android DetailedList eagerly creates every row in a ScrollView.
Keep its public data contract, but supply an actual recycling backend there.
"""
import toga
from dataclasses import dataclass
from .appearance import default_palette, default_apple_color


def thumbnail_image(image, *, size=28):
    """UITableView uses image point size to reserve label space."""
    if not type(image._impl).__module__.startswith('toga_iOS.'):
        return image
    from rubicon.objc import Block, objc_id, CGRect, ObjCClass
    from toga_iOS.libs import UIGraphicsImageRenderer, CGSize
    from toga_iOS.images import nsdata_to_bytes
    native = image._impl.native
    renderer = UIGraphicsImageRenderer.alloc().initWithSize(CGSize(size, size))
    def draw(context):
        ratio = min(size / float(native.size.width), size / float(native.size.height))
        width, height = float(native.size.width) * ratio, float(native.size.height) * ratio
        native.drawInRect(CGRect(((size - width) / 2, (size - height) / 2), (width, height)))
    result = toga.Image(src=nsdata_to_bytes(renderer.PNGDataWithActions(Block(draw, None, objc_id))))
    # PNG data does not retain UIImage's point scale. Restore the renderer's
    # scale so Retina pixels do not become a 56/84-point table image slot.
    result._impl.native = ObjCClass('UIImage').imageWithCGImage(result._impl.native.CGImage,
        scale=renderer.format.scale, orientation=0)
    return result


@dataclass(frozen=True)
class ListAppearance:
    """Host-supplied colors, icons and native pt/dp/sp row dimensions."""
    palette: object = default_palette
    apple_color: object = default_apple_color
    high_contrast: object = lambda: False
    icon: object = lambda folder: None
    row_height: int = 48
    body_text: int = 17
    caption_text: int = 13
    icon_size: int = 28

    def __post_init__(self):
        for name in ('row_height', 'body_text', 'caption_text', 'icon_size'):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(name + ' must be a positive integer')


class RecycledList(toga.DetailedList):
    @property
    def enabled(self):
        return getattr(self, '_enabled', True)

    @enabled.setter
    def enabled(self, value):
        self._enabled = bool(value)
        setter = getattr(getattr(self, '_impl', None), 'set_enabled', None)
        if setter is not None:
            setter(self._enabled)

    def __init__(self, *, on_visible=None, primary_action='Select', row_kind='Item', appearance=None, **kwargs):
        self.on_visible = on_visible
        self.updating = False
        self.row_kind = row_kind
        self.appearance = appearance or ListAppearance()
        self.icon_size = self.appearance.icon_size
        super().__init__(primary_action=primary_action, secondary_action=None, **kwargs)

    def refresh_palette(self):
        refresh = getattr(self._impl, 'refresh_palette', None)
        if refresh is not None:
            refresh()

    def _create(self):
        backend = self.factory.DetailedList.__module__
        if backend.startswith('toga_android.'):
            from .recycled_list_android import AndroidFileList
            return AndroidFileList(self)
        if backend.startswith('toga_iOS.'):
            from .recycled_list_ios import IOSFileList
            return IOSFileList(self)
        return super()._create()

    def row_visible(self, index):
        if not self.updating and self.on_visible is not None and 0 <= index < len(self.data):
            self.on_visible(self.data[index])

    @property
    def data(self):
        return toga.DetailedList.data.fget(self)

    @data.setter
    def data(self, source):
        prepare = getattr(self._impl, 'prepare_source_change', None)
        if prepare is not None:
            prepare()
        toga.DetailedList.data.fset(self, source)

    def select_index(self, index):
        """Selection changes from contextual actions must not activate a file."""
        backend = self.factory.DetailedList.__module__
        if backend.startswith('toga_android.'):
            self._impl.native.selectRow(-1 if index is None else index)
        elif backend.startswith('toga_iOS.'):
            from toga_iOS.libs import NSIndexPath
            if index is None:
                selected = self._impl.native.indexPathForSelectedRow
                if selected is not None:
                    self._impl.native.deselectRowAtIndexPath(selected, animated=False)
            else:
                path = NSIndexPath.indexPathForRow(index, inSection=0)
                self._impl.native.selectRowAtIndexPath(path, animated=False, scrollPosition=0)
        else:
            self._impl._set_value('selection', index)

    def clear(self):
        self.updating = True
        try:
            self.data = []
            self.select_index(None)
        finally:
            self.updating = False
