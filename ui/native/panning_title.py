"""Single-line titles that pan once on overflow and respect motion preferences."""
from functools import lru_cache

import toga


def apple_title_class():
    """Return the shared UIKit label class compiled from ios/ScrollingTitle.m."""
    from rubicon.objc import ObjCClass
    return ObjCClass('CommonUtilsPanningTitle')


def configure_android_title(label):
    """Bind a native TextView, including one that later detaches or changes size."""
    from java import jclass
    jclass('io.github.ispaure.commonutils.TitleMotion').bind(label)


def set_android_title_motion_suppressed(suppressed):
    """Apply a host-wide motion override, in addition to Android accessibility settings."""
    from java import jclass
    jclass('io.github.ispaure.commonutils.TitleMotion').setSuppressed(bool(suppressed))


@lru_cache(maxsize=None)
def _apple_label_backend(base):
    class PanningLabel(base):
        __module__ = base.__module__

        def create(self):
            self.native = apple_title_class().new()
            self.native.lineBreakMode = 5  # Middle ellipsis when motion is suppressed.
            self.add_constraints()
    return PanningLabel


class PanningTitleLabel(toga.Label):
    """Toga title label. Other backends retain their ordinary label behavior."""
    def _create(self):
        backend = self.factory.Label
        if backend.__module__.startswith('toga_iOS.'):
            return _apple_label_backend(backend)(interface=self)
        return super()._create()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .presentation import allow_label_to_shrink
        allow_label_to_shrink(self)
        if self.factory.Label.__module__.startswith('toga_android.'):
            configure_android_title(self._impl.native)

    def restart_pan(self):
        """Replay for a different item with the same caption, subject to motion settings."""
        backend = self.factory.Label.__module__
        if backend.startswith('toga_iOS.'):
            self._impl.native.restartPan()
        elif backend.startswith('toga_android.') and self._impl.native.isSelected():
            self._impl.native.setSelected(False)
            self._impl.native.setSelected(True)
